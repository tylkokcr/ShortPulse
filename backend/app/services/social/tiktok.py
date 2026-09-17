"""Publishing to TikTok, via the Content Posting API.

Left until last on purpose. Its review is the most capricious of the
three, and until it clears, an unaudited client is boxed in hard:
`SELF_ONLY` visibility, five users in any 24 hours, and nothing a viewer
could reach. None of that is an error to handle — it is the state the
integration lives in until the paperwork lands.

Three things about this API look like bugs and are not:

  * **The post is a draft, not a post.** This uses the *inbox* endpoint,
    which drops the video into the user's TikTok notifications for them
    to caption, set privacy on, and publish themselves. Direct posting
    is a separate scope with a separate review, and it is the wrong
    default for a tool that generates video: the honest shape is that
    ShortPulse hands the user something to look at, and TikTok is where
    they decide. `PublishOutcome.url` therefore points at the inbox, not
    at a video, because there is no video yet.
  * **TikTok fetches the file itself.** `PULL_FROM_URL` means the bytes
    never leave this machine on our schedule — TikTok queues the download
    and takes as long as it takes. That is what `social_media_url_ttl_s`
    is an hour for. It also means the domain must be verified in the
    developer portal under URL properties; an unverified one fails with
    `url_ownership_unverified` and no amount of retrying fixes it.
  * **`publish_id` is not a video id.** It identifies the upload job.
    Polling it reports how the transfer went, not whether anything was
    published, and once the video is in the inbox the job is done from
    the API's point of view.

The token shape differs from Google's in a way that matters: TikTok
returns a refresh token on *every* refresh and the old one stops working,
so unlike YouTube the new one must be stored or the connection dies at
the next renewal.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.services.social.base import (
    ConnectionRevoked,
    OAuthTokens,
    PlatformAccount,
    PublishError,
    PublishOutcome,
    PublishTarget,
)

logger = logging.getLogger(__name__)

_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
_USERINFO_URL = "https://open.tiktokapis.com/v2/user/info/"
_INBOX_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

# `video.upload` is the inbox scope — the one that hands a draft to the
# user. `video.publish` is what direct posting needs and is deliberately
# not asked for: it is a second review to justify, and a tool that posts
# to somebody's account without them seeing it first is not the product.
# `user.info.basic` is the smallest thing that answers "whose account is
# this", which is half the connection's primary key.
_UPLOAD_SCOPE = "video.upload"
_SCOPES = ["user.info.basic", _UPLOAD_SCOPE]

# The inbox transfer is TikTok pulling from us, so nothing here waits on
# bytes — these are ordinary API calls.
_API_TIMEOUT = httpx.Timeout(30.0)

# How long to watch the upload job before leaving it alone.
#
# The job is TikTok downloading a file over its own queue, and a slow one
# is not a failed one. Reporting "it is still going" as a failure would
# mark a post failed that then appears in the user's inbox ten minutes
# later — worse than saying nothing. So this poll is a courtesy: it turns
# a *fast* failure into a real error message, and anything slower is
# reported as accepted, which is what it is.
_POLL_ATTEMPTS = 10
_POLL_INTERVAL_S = 3.0


class TikTokPublisher:
    platform = "tiktok"

    def __init__(self, client_key: str, client_secret: str, redirect_uri: str) -> None:
        self._client_key = client_key
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    # -- OAuth ---------------------------------------------------------

    def authorize_url(self, state: str) -> str:
        return f"{_AUTH_URL}?" + urlencode(
            {
                # `client_key`, not `client_id`. TikTok is alone in this
                # among the three, and the error for getting it wrong is
                # a generic invalid-request page with nothing naming the
                # parameter.
                "client_key": self._client_key,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": ",".join(_SCOPES),
                "state": state,
            }
        )

    async def exchange_code(self, code: str) -> tuple[OAuthTokens, PlatformAccount]:
        async with httpx.AsyncClient(timeout=_API_TIMEOUT) as client:
            response = await client.post(
                _TOKEN_URL,
                data={
                    "client_key": self._client_key,
                    "client_secret": self._client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": self._redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if response.status_code != 200:
                raise PublishError(
                    "TikTok refused to complete the connection. Try connecting again."
                )
            payload = response.json()
            if payload.get("error"):
                raise PublishError(
                    "TikTok refused to complete the connection. Try connecting again."
                )

            tokens = _tokens_from(payload)
            open_id = payload.get("open_id")
            if not open_id:
                raise PublishError("TikTok connected but didn't say which account it was.")

            if _UPLOAD_SCOPE not in tokens.scopes:
                # The same failure YouTube produced, for the same reason
                # and with a worse ending: the grant completes, signs the
                # account in, and cannot upload. The first post then fails
                # with a permission error that this code reads as a dead
                # grant — so the connection is retired and the user watches
                # the account they just added disappear.
                #
                # Most often this is the app, not the user: `video.upload`
                # has to be enabled under Scopes in TikTok's developer
                # portal, and a client without it authorises fine.
                logger.error(
                    "TikTok granted %s but not %s — check the app's Scopes in the "
                    "developer portal",
                    tokens.scopes,
                    _UPLOAD_SCOPE,
                )
                raise PublishError(
                    "TikTok didn't give ShortPulse permission to upload videos. Connect again "
                    "and allow video uploads — if it keeps happening, this app's TikTok "
                    "configuration is missing the upload scope."
                )

            # Best effort: the display name is decoration, and a account
            # that grants upload but not profile reading is still a
            # perfectly usable connection. The open_id is the part that
            # has to be there, and it comes from the token response.
            display_name = None
            try:
                info = await client.get(
                    _USERINFO_URL,
                    params={"fields": "display_name"},
                    headers={"Authorization": f"Bearer {tokens.access_token}"},
                )
                if info.status_code == 200:
                    display_name = (
                        info.json().get("data", {}).get("user", {}).get("display_name")
                    )
            except httpx.HTTPError:
                logger.info("TikTok connected but the profile lookup failed")

        return tokens, PlatformAccount(external_id=str(open_id), display_name=display_name)

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        async with httpx.AsyncClient(timeout=_API_TIMEOUT) as client:
            response = await client.post(
                _TOKEN_URL,
                data={
                    "client_key": self._client_key,
                    "client_secret": self._client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if response.status_code != 200:
            raise PublishError("Couldn't renew access to TikTok.", retryable=True)

        payload = response.json()
        error = payload.get("error")
        if error in ("invalid_grant", "access_denied"):
            raise ConnectionRevoked(
                "Your TikTok account no longer allows ShortPulse to upload. "
                "Reconnect it to publish again."
            )
        if error:
            raise PublishError("Couldn't renew access to TikTok.", retryable=True)

        # Unlike Google, TikTok rotates the refresh token and retires the
        # one just used. Falling back to the old one on a response that
        # omitted it would store a token that is already dead.
        refreshed = _tokens_from(payload)
        if not refreshed.refresh_token:
            raise ConnectionRevoked(
                "TikTok ended this connection. Reconnect it to publish again."
            )
        return refreshed

    # -- Publishing ----------------------------------------------------

    async def publish(self, tokens: OAuthTokens, target: PublishTarget) -> PublishOutcome:
        if not target.video_url:
            raise PublishError("There is no link for TikTok to fetch the video from.")

        async with httpx.AsyncClient(timeout=_API_TIMEOUT) as client:
            init = await client.post(
                _INBOX_INIT_URL,
                headers={
                    "Authorization": f"Bearer {tokens.access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                },
                json={
                    "source_info": {
                        "source": "PULL_FROM_URL",
                        "video_url": target.video_url,
                    }
                },
            )

            if init.status_code != 200:
                raise _api_error(init)

            body = init.json()
            if body.get("error", {}).get("code") not in (None, "ok"):
                raise _mapped_error(body["error"])

            publish_id = body.get("data", {}).get("publish_id")
            if not publish_id:
                raise PublishError("TikTok accepted the upload but returned no id.", retryable=True)

            failure = await self._watch(client, tokens.access_token, publish_id)

        if failure is not None:
            raise failure

        return PublishOutcome(
            platform_post_id=publish_id,
            # There is no video to link to: it is sitting in the user's
            # notifications waiting for them to finish it. Sending them to
            # the inbox is the only honest destination.
            url="https://www.tiktok.com/notifications",
            # Nothing was published, so nothing has a visibility yet. The
            # user chooses it when they post from the draft, and claiming
            # the requested privacy here would be a lie the UI repeats.
            privacy="draft",
        )

    async def _watch(
        self, client: httpx.AsyncClient, access_token: str, publish_id: str
    ) -> PublishError | None:
        """Give a fast failure a chance to be a real error message.

        Returns the error to raise, or None for "accepted" — which covers
        both a finished transfer and one still running. See _POLL_ATTEMPTS
        for why a slow job is not reported as a failure.
        """
        for _ in range(_POLL_ATTEMPTS):
            await asyncio.sleep(_POLL_INTERVAL_S)
            try:
                response = await client.post(
                    _STATUS_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json; charset=UTF-8",
                    },
                    json={"publish_id": publish_id},
                )
            except httpx.HTTPError:
                # The upload was accepted; losing sight of it is not the
                # same as it failing.
                return None

            if response.status_code != 200:
                return None

            data = response.json().get("data", {})
            status = data.get("status")
            if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
                return None
            if status == "FAILED":
                return _download_failure(data.get("fail_reason", ""))

        return None


def _tokens_from(payload: dict) -> OAuthTokens:
    expires_in = payload.get("expires_in")
    return OAuthTokens(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=(
            datetime.now(UTC) + timedelta(seconds=int(expires_in)) if expires_in else None
        ),
        # A comma-separated list here, where Google sends spaces.
        scopes=[s for s in str(payload.get("scope", "")).replace(" ", "").split(",") if s],
    )


def _download_failure(reason: str) -> PublishError:
    """Why TikTok could not fetch the file.

    Worth mapping rather than passing through: these arrive minutes after
    the user pressed publish, and `url_ownership_unverified` in
    particular is an operator problem the user can do nothing about — it
    means this deployment's domain was never verified in TikTok's portal,
    so every post will fail the same way until somebody does that.
    """
    if reason == "url_ownership_unverified":
        logger.error(
            "TikTok refused the download: this deployment's domain is not verified "
            "under URL properties in the TikTok developer portal"
        )
        return PublishError("This site isn't set up for TikTok uploads yet.")
    if reason in ("file_format_check_failed", "video_pull_failed"):
        return PublishError("TikTok couldn't read the video file.", retryable=True)
    if reason == "duration_check_failed":
        return PublishError("TikTok rejected the video's length.")
    if reason == "frame_rate_check_failed":
        return PublishError("TikTok rejected the video's frame rate.")
    if reason == "picture_size_check_failed":
        return PublishError("TikTok rejected the video's dimensions.")
    logger.warning("Unmapped TikTok failure reason: %s", reason)
    return PublishError("TikTok couldn't accept the video.", retryable=True)


def _api_error(response: httpx.Response) -> PublishError:
    if response.status_code in (401, 403):
        # Logged because this answer retires the connection: the account
        # vanishes from the user's list, and without the body there is
        # nothing to say whether the grant really died or the app was
        # simply never allowed to upload.
        logger.warning(
            "TikTok refused the upload (%s): %s", response.status_code, response.text[:300]
        )
        return ConnectionRevoked(
            "TikTok refused the upload for this account. Reconnect it and try again."
        )
    if response.status_code == 429:
        return PublishError(
            "TikTok is rate-limiting uploads from this app. Try again later.", retryable=True
        )
    if response.status_code >= 500:
        return PublishError("TikTok had a problem accepting the upload.", retryable=True)
    try:
        return _mapped_error(response.json().get("error", {}))
    except ValueError:
        return PublishError("TikTok rejected the upload.")


def _mapped_error(error: dict) -> PublishError:
    code = error.get("code", "")
    message = error.get("message", "")

    if code in ("access_token_invalid", "scope_not_authorized", "scope_permission_missed"):
        return ConnectionRevoked(
            "TikTok no longer allows ShortPulse to upload to this account. Reconnect it."
        )
    if code == "spam_risk_too_many_posts":
        # The unaudited cap. Naming it is the difference between a user
        # retrying all evening and a user waiting until tomorrow.
        return PublishError(
            "TikTok's daily upload limit for this app has been reached. Try again tomorrow.",
            retryable=True,
        )
    if code == "spam_risk_user_banned_from_posting":
        return PublishError("TikTok has blocked this account from posting.")
    if code == "reached_active_user_cap":
        return PublishError(
            "TikTok limits how many people can use an unapproved app. Try again tomorrow.",
            retryable=True,
        )
    if code == "url_ownership_unverified":
        logger.error(
            "TikTok refused the upload: this deployment's domain is not verified "
            "under URL properties in the TikTok developer portal"
        )
        return PublishError("This site isn't set up for TikTok uploads yet.")

    logger.warning("Unmapped TikTok error %s: %s", code, message[:300])
    return PublishError(message or "TikTok rejected the upload.")
