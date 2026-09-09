"""Deciding what gets posted, and putting it through a worker.

The publishers in services/social know how to talk to one platform each.
This is everything else: whose account, which caption, whether a human
approved it, what to do when the token expired, and what the user is told
when it fails.

Three things here are load-bearing and none of them belong in a publisher:

  * **Attribution.** Pexels and Pixabay licence their footage on condition
    the photographer is credited, and `StockAttribution.as_text` was
    written as "one line a user can paste into a post description" — which
    worked while a human wrote every post. Automatic publishing removes
    the human who was doing the pasting, so the credit has to be appended
    here or the feature quietly turns a compliant workflow into a
    non-compliant one at scale.
  * **The first-post rule.** A connection that has never published holds
    its first automatic post for review, however the toggle is set. One
    click, once per account, against a bad render landing on somebody's
    real audience.
  * **Token refresh.** Every platform expires access tokens and every one
    of them would otherwise reimplement the same "is it stale, renew it,
    store it, carry on" dance.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import Settings
from app.schemas.project import Project, ProjectStatus, VisualMode
from app.services import db, project_store, social_store
from app.services.social.base import (
    ConnectionRevoked,
    PublishError,
    PublishTarget,
    SocialPublisher,
)
from app.services.social_tokens import TokenCipher, TokenDecryptionError

logger = logging.getLogger(__name__)

# Renew a token that is close to expiring rather than one that already
# has. An upload takes minutes, and a token with thirty seconds left is a
# 401 halfway through the bytes.
_REFRESH_MARGIN = timedelta(minutes=5)


def compose_description(project: Project, description: str) -> str:
    """The post description, plus anything the licence requires.

    Only stock_media projects carry attributions — AI-generated visuals
    have nobody to credit — and the same clip used in three scenes is one
    credit, not three, so the lines are deduplicated in the order they
    first appear.
    """
    if project.config.visual_mode != VisualMode.STOCK_MEDIA:
        return description

    credits: list[str] = []
    for scene in project.script.scenes if project.script else []:
        attribution = scene.visual.attribution
        if attribution is None:
            continue
        line = attribution.as_text()
        if line not in credits:
            credits.append(line)

    if not credits:
        return description
    return f"{description}\n\n" + "\n".join(credits)


class PublishQueue:
    """Bounded workers for publish jobs.

    Separate from RenderTaskQueue because the two are bound by different
    things: a render is CPU and GPU, a publish is somebody else's network.
    Sharing the pool would let three slow uploads block the machine's
    ability to render anything, which is what people actually paid for.

    The queue itself is in memory; the truth is in social_posts. A restart
    reloads what was queued and fails what was mid-upload — see
    social_store.reclaim_interrupted for why those are treated differently.
    """

    def __init__(
        self,
        settings: Settings,
        publishers: dict[str, SocialPublisher],
        cipher: TokenCipher | None,
    ) -> None:
        self._settings = settings
        self._publishers = publishers
        self._cipher = cipher
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []

    @property
    def enabled(self) -> bool:
        return bool(self._publishers) and self._cipher is not None

    def start(self) -> None:
        if not self.enabled:
            return
        for _ in range(max(1, self._settings.max_concurrent_publishes)):
            self._workers.append(asyncio.create_task(self._worker_loop()))

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        self._workers.clear()

    async def submit(self, post_id: str) -> None:
        await self._queue.put(post_id)

    async def resume_after_restart(self) -> None:
        """Reload anything that was queued when the process last stopped.

        Runs after reclaim_interrupted, so a post that was mid-upload has
        already been failed and is not picked up here.
        """
        pool = db.optional_pool()
        if pool is None or not self.enabled:
            return

        failed = await social_store.reclaim_interrupted(pool)
        if failed:
            logger.warning("Failed %d publish job(s) interrupted by a restart", len(failed))

        for post_id in await social_store.queued_post_ids(pool):
            await self._queue.put(post_id)

    async def _worker_loop(self) -> None:
        while True:
            post_id = await self._queue.get()
            try:
                await self._publish(post_id)
            except Exception:  # pragma: no cover - a worker must not die
                logger.exception("Publish job %s crashed", post_id)
            finally:
                self._queue.task_done()

    async def _publish(self, post_id: str) -> None:
        pool = db.optional_pool()
        if pool is None or self._cipher is None:
            return

        post = await social_store.get_post(pool, post_id)
        if post is None or post.status != "queued":
            # Cancelled, already done, or claimed by another process.
            return

        try:
            connection = await social_store.load_for_publish(
                pool, post.connection_id, self._cipher
            )
        except TokenDecryptionError:
            logger.exception("Cannot decrypt tokens for connection %s", post.connection_id)
            await social_store.mark_failed(
                pool, post_id, "This account needs to be reconnected before it can publish."
            )
            return

        if connection is None:
            await social_store.mark_failed(pool, post_id, "That account is no longer connected.")
            return

        publisher = self._publishers.get(connection.platform)
        if publisher is None:
            await social_store.mark_failed(
                pool, post_id, f"Publishing to {connection.platform} is not available."
            )
            return

        project = await project_store.get_project(post.project_id)
        if project is None or not project.output_path:
            await social_store.mark_failed(pool, post_id, "The video is no longer available.")
            return

        await social_store.mark_uploading(pool, post_id)

        try:
            tokens = connection.tokens
            expires_at = tokens.expires_at
            if expires_at is not None:
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                if expires_at - _REFRESH_MARGIN <= datetime.now(UTC):
                    if not tokens.refresh_token:
                        raise ConnectionRevoked(
                            "Access to this account expired. Reconnect it to publish again."
                        )
                    tokens = await publisher.refresh(tokens.refresh_token)
                    await social_store.store_refreshed_tokens(
                        pool, connection.id, tokens, self._cipher
                    )

            outcome = await publisher.publish(tokens, self._build_target(project, post))
        except ConnectionRevoked as exc:
            # The grant is gone, not just this post. Retiring the
            # connection stops every later automatic post from queueing
            # against a dead account and failing one by one.
            await social_store.revoke_connection(pool, connection.id, connection.user_id)
            await social_store.mark_failed(pool, post_id, str(exc))
            return
        except PublishError as exc:
            await social_store.mark_failed(pool, post_id, str(exc))
            return
        except Exception:
            logger.exception("Unexpected failure publishing %s", post_id)
            await social_store.mark_failed(
                pool, post_id, "Something went wrong publishing this video."
            )
            return

        await social_store.mark_published(
            pool,
            post_id,
            platform_post_id=outcome.platform_post_id,
            url=outcome.url,
            privacy=outcome.privacy,
        )
        await social_store.mark_first_post(pool, connection.id)
        logger.info("Published %s to %s as %s", post.project_id, connection.platform, outcome.url)

    def _build_target(self, project: Project, post: social_store.Post) -> PublishTarget:
        """Everything a publisher needs, in the form it needs it.

        Both the file and a URL, because which one is dead weight depends
        on the platform. The URL is signed and long-lived by publishing
        standards (an hour, against fifteen minutes for playback) because
        the platform fetching it is behind its own queue and nobody is
        watching the clock on this end.
        """
        signer = _media_signer()
        token, _ = signer.sign(project.config.id, ttl_s=self._settings.social_media_url_ttl_s)
        base = self._settings.public_base_url.rstrip("/")

        return PublishTarget(
            video_path=Path(project.output_path or ""),
            video_url=f"{base}/api/projects/{project.config.id}/download?token={token}",
            title=post.title or "",
            description=post.description or "",
            hashtags=post.hashtags,
            privacy=post.privacy,
        )


# Process-wide, set from main at startup.
#
# Singletons rather than arguments because of who the caller is: the
# render pipeline finishes a project deep inside a worker task that holds
# settings and nothing else — no request, no app, no way to reach
# app.state. Threading either of these down through run_pipeline to reach
# the one line that needs them would put publishing into the signature of
# every render function on the way.
_signer = None
_queue: PublishQueue | None = None


def _media_signer():
    if _signer is None:  # pragma: no cover - configuration error
        raise RuntimeError("Media signer is not configured")
    return _signer


def configure_signer(signer) -> None:
    global _signer
    _signer = signer


def configure_queue(queue: PublishQueue) -> None:
    global _queue
    _queue = queue


async def queue_automatic_posts(project: Project) -> None:
    """Post a finished render to every connection set to do that by itself.

    Called from the render pipeline the moment a project completes. Does
    nothing at all unless the user has both connected an account and
    turned the toggle on for it — the default is off and stays off until
    somebody deliberately changes it.

    Never raises: it runs at the end of a successful render, and a failure
    to publish must not turn a finished video into a failed project. The
    worst case here is a post that does not happen, which the user can
    make happen with a button.
    """
    if _queue is None or not _queue.enabled or project.status != ProjectStatus.COMPLETE:
        return

    # Checked before touching the database: an upload project can never
    # have post copy, and this runs at the end of every single render.
    copy = project.script.post if project.script else None
    if copy is None or not copy.title.strip():
        return

    pool = db.optional_pool()
    if pool is None:
        return

    user_id = await project_store.owner_of(project.config.id)
    if user_id is None:
        # No owner means a self-hosted install: nobody to publish as, and
        # no connections row could exist anyway.
        return

    connections = await social_store.list_connections(pool, user_id)
    for connection in connections:
        if not connection.auto_publish:
            continue

        # The first post through a new connection is held even with the
        # toggle on. See 0008.
        status = "queued" if connection.first_post_at else "awaiting_review"

        post_id = await social_store.create_post(
            pool,
            project_id=project.config.id,
            connection_id=connection.id,
            user_id=user_id,
            title=copy.title,
            description=compose_description(project, copy.description),
            hashtags=copy.hashtags,
            privacy="public",
            status=status,
        )
        if post_id and status == "queued":
            await _queue.submit(post_id)
