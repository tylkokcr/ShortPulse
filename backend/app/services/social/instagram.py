"""Publishing Reels to Instagram, via Instagram Business Login.

Not through Facebook. This used to share `meta.py`'s OAuth with the
Facebook publisher, on the theory that one Meta app served both — and
that is one of the two ways Meta lets you reach Instagram, but it is not
the one this deployment is set up for. The app declares the "Manage
messaging & content on Instagram" use case, which is Instagram Business
Login: its own app id, its own login dialog on instagram.com, its own
host at graph.instagram.com, and permission names that are *not* the
Facebook-flavoured ones. Asking facebook.com for `instagram_basic` with
the Facebook app id, as this file did, fails before the user sees a
consent screen, because that app was never granted those permissions.

So the two publishers now have nothing in common but an error parser, and
they are configured independently — one Meta app no longer implies the
other. `graph_error` is still shared because graph.instagram.com returns
the same error envelope, code 190 and all.

The thing this flavour is better at: the Instagram account does not have
to be linked to a Facebook Page. A Business or Creator account is enough,
which removes the failure the old `_find_account` existed to explain.

Publishing is still three calls, and the middle one is still a wait:

  1. Open a container for the video URL. Returns immediately with an id
     and nothing useful — Instagram has not fetched anything yet.
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
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.services.social import meta
from app.services.social.base import (
    ConnectionRevoked,
    OAuthTokens,
    PlatformAccount,
    PublishError,
    PublishOutcome,
    PublishTarget,
)

logger = logging.getLogger(__name__)

# Three different hosts, which is not a tidiness problem to solve: the
# dialog is on the consumer site, the code exchange is on api., and
# everything afterwards is on graph. Meta documents them this way and
# they are not interchangeable.
_AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
GRAPH = "https://graph.instagram.com"
# The media endpoints are documented against a version; the two token
# endpoints are documented without one and reject the prefix.
_GRAPH_VERSIONED = f"{GRAPH}/v23.0"

# `instagram_business_content_publish` is the one that posts. Without it
# the connection completes and every publish afterwards is refused, so a
# missing grant is worth noticing at connect time rather than at 2am on
# the first automatic post.
_SCOPES = [
    "instagram_business_basic",
    "instagram_business_content_publish",
]

# A long-lived token is good for 60 days and `ig_refresh_token` resets it
# to 60 more. 55 is the fallback when Meta omits expires_in — short
# enough that the refresh lands well inside the real window.
_LONG_LIVED_DAYS = 55

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
        return f"{_AUTHORIZE_URL}?" + urlencode(
            {
                "client_id": self._app_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": ",".join(_SCOPES),
                "state": state,
            }
        )

    async def exchange_code(self, code: str) -> tuple[OAuthTokens, PlatformAccount]:
        async with httpx.AsyncClient(timeout=meta.API_TIMEOUT) as client:
            short = await client.post(
                _TOKEN_URL,
                data={
                    "client_id": self._app_id,
                    "client_secret": self._app_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": self._redirect_uri,
                    "code": code,
                },
            )
            if short.status_code != 200:
                logger.warning(
                    "Instagram refused the code exchange (%s): %s",
                    short.status_code,
                    short.text[:300],
                )
                raise PublishError(
                    "Instagram refused to complete the connection. Try connecting again."
                )

            payload = _token_payload(short.json())
            short_token = payload.get("access_token")
            if not short_token:
                raise PublishError(
                    "Instagram refused to complete the connection. Try connecting again."
                )
            granted = _granted_scopes(payload)

            tokens = await self._exchange_for_long_lived(client, short_token, granted)
            account = await self._account(client, tokens.access_token)

        return tokens, account

    async def _exchange_for_long_lived(
        self, client: httpx.AsyncClient, short_token: str, granted: list[str]
    ) -> OAuthTokens:
        """An hour becomes sixty days.

        Not optional: storing the short-lived token would give a
        connection that dies before the first scheduled post, and there is
        no way to lengthen it afterwards — the exchange only accepts a
        token that is still valid.
        """
        response = await client.get(
            f"{GRAPH}/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": self._app_secret,
                "access_token": short_token,
            },
        )
        if response.status_code != 200:
            logger.warning(
                "Instagram refused the long-lived exchange (%s): %s",
                response.status_code,
                response.text[:300],
            )
            raise PublishError(
                "Instagram refused to complete the connection. Try connecting again."
            )

        body = response.json()
        access_token = body.get("access_token")
        if not access_token:
            raise PublishError(
                "Instagram refused to complete the connection. Try connecting again."
            )

        return OAuthTokens(
            access_token=access_token,
            # The same string twice. `ig_refresh_token` presents the
            # access token itself, so this is not a second credential —
            # it is the only one there is, stored where the manager looks
            # for it.
            refresh_token=access_token,
            expires_at=_expiry(body.get("expires_in")),
            scopes=granted,
        )

    async def _account(self, client: httpx.AsyncClient, access_token: str) -> PlatformAccount:
        """Which account this grant posts to.

        `user_id` rather than `id`: the media endpoints are addressed by
        the Instagram professional account id, and on this login flavour
        `id` is the app-scoped one. Publishing to the wrong one of the two
        is a 400 an hour later with nothing to connect it back to here.
        """
        response = await client.get(
            f"{GRAPH}/me",
            params={"fields": "user_id,username", "access_token": access_token},
        )
        if response.status_code != 200:
            raise meta.graph_error(response, action="connection")

        body = response.json()
        account_id = body.get("user_id") or body.get("id")
        if not account_id:
            raise PublishError(
                "Instagram didn't say which account this is. Try connecting again."
            )

        username = body.get("username")
        return PlatformAccount(
            external_id=str(account_id),
            display_name=f"@{username}" if username else None,
        )

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        """Sixty more days, from a token that has not expired yet.

        `ig_refresh_token` refuses a token that is already dead, so there
        is no recovery here — a connection left alone past its window is
        reconnected by the user, not renewed by us.
        """
        async with httpx.AsyncClient(timeout=meta.API_TIMEOUT) as client:
            response = await client.get(
                f"{GRAPH}/refresh_access_token",
                params={
                    "grant_type": "ig_refresh_token",
                    "access_token": refresh_token,
                },
            )
            if response.status_code in (400, 401, 403):
                raise ConnectionRevoked(
                    "Your Instagram connection to ShortPulse has expired. "
                    "Reconnect it to publish again."
                )
            if response.status_code != 200:
                raise PublishError("Couldn't renew access to Instagram.", retryable=True)

            body = response.json()
            access_token = body.get("access_token")
            if not access_token:
                raise PublishError("Couldn't renew access to Instagram.", retryable=True)

            return OAuthTokens(
                access_token=access_token,
                refresh_token=access_token,
                expires_at=_expiry(body.get("expires_in")),
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
                f"{_GRAPH_VERSIONED}/{ig_user_id}/media",
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
                f"{_GRAPH_VERSIONED}/{ig_user_id}/media_publish",
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
                f"{_GRAPH_VERSIONED}/{container_id}",
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


def _token_payload(body: dict) -> dict:
    """The code exchange answers in two shapes.

    Instagram Business Login documents `{"data": [{...}]}`, and returns
    the flat object on some app configurations. Reading only the
    documented one would fail on a live app with nothing in the response
    to explain it, so both are accepted and neither is assumed.
    """
    data = body.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return body


def _granted_scopes(payload: dict) -> list[str]:
    """What the user actually ticked, which is not always what was asked.

    Comes back as a comma-joined string on this flow, and as a list on
    some responses.
    """
    permissions = payload.get("permissions")
    if isinstance(permissions, str):
        return [p.strip() for p in permissions.split(",") if p.strip()]
    if isinstance(permissions, list):
        return [str(p) for p in permissions]
    return []


def _expiry(expires_in: object) -> datetime:
    """Meta's own number when it sends one, a safe default when it
    doesn't. Documented as always present, and worth not relying on: a
    wrong expiry here is a connection that either refreshes forever or
    dies without warning."""
    if isinstance(expires_in, (int, str)):
        try:
            return datetime.now(UTC) + timedelta(seconds=int(expires_in))
        except ValueError:
            pass
    return datetime.now(UTC) + timedelta(days=_LONG_LIVED_DAYS)


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
