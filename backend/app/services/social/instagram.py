"""Publishing Reels to Instagram, via the Graph API.

The one platform that puts a requirement on the *user's* account rather
than only on ours. Posting through the API needs an Instagram
Business or Creator account linked to a Facebook Page — a personal
account cannot be published to at all, by anyone, and there is no
permission that changes that. The failure is therefore worth catching at
connect time with a sentence that says what to go and do, because at
publish time it is far too late and reads as our bug.

Publishing is three calls, not one, and the middle one is a wait:

  1. Open a container for the video URL. This returns immediately with an
     id and nothing useful — Instagram has not fetched anything yet.
  2. Poll the container until `status_code` is FINISHED. IN_PROGRESS is
     the normal state for most of a minute; ERROR is terminal.
  3. Publish the container. Only now does a Reel exist.

Publishing a container that is not FINISHED fails, so step two is not
optional politeness — it is load-bearing, and it is why this publisher
holds a connection open for a minute where YouTube's returns in seconds.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.services.social import meta
from app.services.social.base import (
    OAuthTokens,
    PlatformAccount,
    PublishError,
    PublishOutcome,
    PublishTarget,
)

logger = logging.getLogger(__name__)

# `instagram_content_publish` is the one that posts. The rest are what it
# takes to find out where: the Reel goes to an Instagram account reached
# through the Page that owns it, so the Page has to be listed and read
# before the Instagram account behind it can be named.
_SCOPES = [
    "instagram_basic",
    "instagram_content_publish",
    "pages_show_list",
    "pages_read_engagement",
]

# Instagram transcodes before it will publish, and a short-form render
# takes tens of seconds. Two minutes is comfortably past the observed
# case without holding a worker forever on a container that has quietly
# died — and a container that is still IN_PROGRESS after two minutes is
# reported as a failure the user can retry, because unlike TikTok's
# inbox, an unpublished container never becomes a post on its own.
_POLL_ATTEMPTS = 24
_POLL_INTERVAL_S = 5.0


class InstagramPublisher:
    platform = "instagram"

    def __init__(self, app_id: str, app_secret: str, redirect_uri: str) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._redirect_uri = redirect_uri

    # -- OAuth ---------------------------------------------------------

    def authorize_url(self, state: str) -> str:
        return meta.authorize_url(self._app_id, self._redirect_uri, _SCOPES, state)

    async def exchange_code(self, code: str) -> tuple[OAuthTokens, PlatformAccount]:
        async with httpx.AsyncClient(timeout=meta.API_TIMEOUT) as client:
            tokens = await meta.exchange_code_for_user_token(
                client,
                client_id=self._app_id,
                client_secret=self._app_secret,
                redirect_uri=self._redirect_uri,
                code=code,
            )

            account = await self._find_account(client, tokens.access_token)

        return tokens, account

    async def _find_account(
        self, client: httpx.AsyncClient, user_token: str
    ) -> PlatformAccount:
        """Which Instagram account this grant can actually post to.

        Resolved now rather than at publish time so that the three ways
        this goes wrong — no Page, a Page with no Instagram account, a
        personal account that was never converted — are all answered
        while the user is still looking at the screen that caused them.
        """
        page_list = await meta.pages(client, user_token)
        if not page_list:
            raise PublishError(
                "This Facebook account doesn't manage any Pages. Instagram posting needs a "
                "Page linked to your Instagram account."
            )

        for page in page_list:
            response = await client.get(
                f"{meta.GRAPH}/{page['id']}",
                params={
                    "fields": "instagram_business_account{id,username}",
                    "access_token": user_token,
                },
            )
            if response.status_code != 200:
                continue

            linked = response.json().get("instagram_business_account")
            if linked and linked.get("id"):
                username = linked.get("username")
                return PlatformAccount(
                    external_id=str(linked["id"]),
                    display_name=f"@{username}" if username else page.get("name"),
                )

        raise PublishError(
            "None of your Facebook Pages has an Instagram account linked to it. Link one, and "
            "make sure it's a Business or Creator account — Instagram doesn't allow posting to "
            "personal accounts from any app."
        )

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        async with httpx.AsyncClient(timeout=meta.API_TIMEOUT) as client:
            return await meta.extend(
                client,
                client_id=self._app_id,
                client_secret=self._app_secret,
                token=refresh_token,
            )

    # -- Publishing ----------------------------------------------------

    async def publish(self, tokens: OAuthTokens, target: PublishTarget) -> PublishOutcome:
        if not target.video_url:
            raise PublishError("There is no link for Instagram to fetch the video from.")

        ig_user_id = target.account_id
        if not ig_user_id:
            raise PublishError("This connection doesn't say which Instagram account to post to.")

        caption = _caption(target)

        async with httpx.AsyncClient(timeout=meta.API_TIMEOUT) as client:
            created = await client.post(
                f"{meta.GRAPH}/{ig_user_id}/media",
                data={
                    "media_type": "REELS",
                    "video_url": target.video_url,
                    "caption": caption,
                    "access_token": tokens.access_token,
                },
            )
            if created.status_code != 200:
                raise meta.graph_error(created, action="Reel")

            container_id = created.json().get("id")
            if not container_id:
                raise PublishError("Instagram didn't return anything to publish.", retryable=True)

            await self._await_container(client, container_id, tokens.access_token)

            published = await client.post(
                f"{meta.GRAPH}/{ig_user_id}/media_publish",
                data={"creation_id": container_id, "access_token": tokens.access_token},
            )
            if published.status_code != 200:
                raise meta.graph_error(published, action="Reel")

            media_id = published.json().get("id")

        if not media_id:
            raise PublishError("Instagram accepted the Reel but returned no id.", retryable=True)

        return PublishOutcome(
            platform_post_id=str(media_id),
            url=f"https://www.instagram.com/reel/{media_id}/",
            # Instagram has no per-post visibility in this API: a Reel is
            # as visible as the account that owns it. Saying "public"
            # would be a guess about a private account, so the honest
            # answer is the account's, not ours.
            privacy="account",
        )

    async def _await_container(
        self, client: httpx.AsyncClient, container_id: str, access_token: str
    ) -> None:
        for _ in range(_POLL_ATTEMPTS):
            await asyncio.sleep(_POLL_INTERVAL_S)
            response = await client.get(
                f"{meta.GRAPH}/{container_id}",
                params={"fields": "status_code,status", "access_token": access_token},
            )
            if response.status_code != 200:
                raise meta.graph_error(response, action="Reel")

            body = response.json()
            status = body.get("status_code")
            if status == "FINISHED":
                return
            if status == "ERROR":
                # `status` carries the human-readable reason; status_code
                # is only ever the word ERROR.
                detail = body.get("status", "")
                logger.warning("Instagram container %s failed: %s", container_id, detail[:300])
                raise PublishError("Instagram couldn't process the video.")
            if status == "EXPIRED":
                raise PublishError("Instagram took too long and the upload expired.", retryable=True)

        raise PublishError("Instagram is still processing the video. Try publishing again.", retryable=True)


def _caption(target: PublishTarget) -> str:
    """One field for everything Instagram shows.

    There is no title on a Reel, so the title has to lead the caption or
    be lost. Hashtags go at the end, where they read as tags rather than
    as part of the sentence.
    """
    parts = [p for p in (target.title.strip(), target.description.strip()) if p]
    caption = "\n\n".join(parts)
    if target.hashtags:
        caption = f"{caption}\n\n" + " ".join(f"#{t}" for t in target.hashtags)
    return caption[:2200]
