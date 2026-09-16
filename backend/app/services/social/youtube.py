"""Publishing to YouTube, via the Data API v3.

The first of the three, and deliberately so. It shares a Google Cloud
project with the sign-in client, so the console work was already half
done; its audit asks less than TikTok's; and unlike Instagram it puts no
requirement on the *user's* account — no business profile, no linked page,
just a channel.

Two things about this API are worth knowing before reading the code,
because both look like bugs otherwise:

  * **Uploads may be forced to private, and may not be.** The documented
    rule is that a project which has not passed Google's audit uploads
    private whatever `privacyStatus` asks for, with nothing in the
    response complaining. Observed on 2026-09-17, from this project
    before its audit: the video arrived *public*. The difference appears
    to be the OAuth client's publishing status — Testing forces private,
    Production does not — but that is inference from one case, not
    something Google states.

    Which is why nothing here trusts either answer. The outcome reports
    the privacy the API read back rather than the one that was asked
    for, so whichever rule is in force, the UI shows what actually
    happened to the user's own video.
  * **Uploads bill to their own quota bucket**, separate from the
    10,000-unit daily pool, at roughly 100 uploads a day. Running out
    reads as a 403 with a quota reason and has nothing to do with the
    units everything else spends.
"""

from __future__ import annotations

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

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"

# Only what is needed to upload, plus enough to know whose account this is.
#
# `youtube.upload` is write-only by design: it cannot read the channel, its
# videos, or its analytics. `youtube.readonly` would give a real channel id
# and title for the UI, but it is a second sensitive scope to justify in
# the audit in exchange for a nicer label, so the account is identified by
# the Google user instead — see the brand-account note in exchange_code.
_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
_SCOPES = [
    _UPLOAD_SCOPE,
    "openid",
    "email",
    "profile",
]

# "People & Blogs". Required by the API — an insert with no categoryId is
# rejected — and there is nothing in a ShortPulse project that says which
# category it belongs to. This is the least wrong default for short-form
# talking-point video; a user who cares can change it on YouTube.
_CATEGORY_ID = "22"

# An upload is the one call here that moves real bytes. The default 5s
# would abort a perfectly healthy transfer of a 30MB file on a slow link.
_UPLOAD_TIMEOUT = httpx.Timeout(connect=30.0, read=600.0, write=600.0, pool=30.0)
_API_TIMEOUT = httpx.Timeout(30.0)


def _sanitise(text: str) -> str:
    """Strip the characters YouTube rejects outright.

    Angle brackets in a title or description come back as `invalidTitle` /
    `invalidDescription` with no indication of which character was at
    fault. They arrive here from an LLM writing about markup or maths, so
    it is worth removing them rather than failing the post.
    """
    return text.replace("<", "").replace(">", "")


class YouTubePublisher:
    platform = "youtube"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    # -- OAuth ---------------------------------------------------------

    def authorize_url(self, state: str) -> str:
        return f"{_AUTH_URL}?" + urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "response_type": "code",
                "scope": " ".join(_SCOPES),
                # Both are needed to get a refresh token at all. `offline`
                # asks for one; `consent` forces the screen even on a
                # re-authorisation, because Google issues a refresh token
                # only on the grant that creates it — so a user who
                # reconnects after we lost theirs would otherwise get an
                # access token, no refresh token, and a connection that
                # silently dies in an hour.
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
                "state": state,
            }
        )

    async def exchange_code(self, code: str) -> tuple[OAuthTokens, PlatformAccount]:
        async with httpx.AsyncClient(timeout=_API_TIMEOUT) as client:
            response = await client.post(
                _TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": self._redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if response.status_code != 200:
                raise PublishError(
                    "Google refused to complete the connection. Try connecting again."
                )
            payload = response.json()

            tokens = _tokens_from(payload)
            if not tokens.refresh_token:
                # Without one the connection lasts an hour. Better to
                # refuse it now than to store something that will stop
                # working during the night with no explanation.
                raise PublishError(
                    "Google didn't return a long-lived token. Remove ShortPulse from your "
                    "Google account's third-party access list, then connect again."
                )

            if _UPLOAD_SCOPE not in tokens.scopes:
                # The consent screen's permissions are checkboxes, and on
                # an unverified project the user reaches them through a
                # warning that encourages granting as little as possible.
                # Unticking this one still completes the flow: the grant
                # is real, it signs them in, and it cannot upload. Stored,
                # it fails much later as a 403 that reads as a revoked
                # account — which is a lie, and sends them to reconnect
                # exactly as they did the first time.
                raise PublishError(
                    "ShortPulse wasn't given permission to upload to YouTube. Connect again "
                    "and leave the YouTube box ticked on Google's permission screen."
                )

            # Identified by the Google account rather than the channel,
            # because reading the channel needs a scope we deliberately do
            # not ask for. The consequence is worth stating: a Google
            # account with several brand channels picks one during the
            # consent flow, and this id does not record which. Uploads go
            # to whichever was chosen, and a user connecting two channels
            # from one Google account would collide on the unique key.
            info = await client.get(
                _USERINFO_URL, headers={"Authorization": f"Bearer {tokens.access_token}"}
            )
            if info.status_code != 200:
                raise PublishError("Connected, but Google wouldn't say which account it was.")
            profile = info.json()

        return tokens, PlatformAccount(
            external_id=str(profile["sub"]),
            display_name=profile.get("name") or profile.get("email"),
        )

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        async with httpx.AsyncClient(timeout=_API_TIMEOUT) as client:
            response = await client.post(
                _TOKEN_URL,
                data={
                    "refresh_token": refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "refresh_token",
                },
            )

        if response.status_code == 400:
            # `invalid_grant` is Google's answer for a revoked, expired or
            # otherwise dead refresh token. It is not a transient failure
            # and retrying never fixes it.
            if response.json().get("error") == "invalid_grant":
                raise ConnectionRevoked(
                    "Your Google account no longer allows ShortPulse to upload. "
                    "Reconnect it to publish again."
                )
        if response.status_code != 200:
            raise PublishError("Couldn't renew access to YouTube.", retryable=True)

        # A refresh response carries no refresh token: the original stays
        # valid, and overwriting it with None would lose it.
        refreshed = _tokens_from(response.json())
        return OAuthTokens(
            access_token=refreshed.access_token,
            refresh_token=refresh_token,
            expires_at=refreshed.expires_at,
            scopes=refreshed.scopes,
        )

    # -- Publishing ----------------------------------------------------

    async def publish(self, tokens: OAuthTokens, target: PublishTarget) -> PublishOutcome:
        if not target.video_path.is_file():
            raise PublishError("The rendered video is missing from storage.")

        size = target.video_path.stat().st_size
        title = _sanitise(target.title).strip()[:100]
        if not title:
            # The API rejects an empty title, and an upload that fails at
            # the last step has already spent the bytes.
            raise PublishError("A YouTube upload needs a title.")

        # Hashtags go in the description as well as in tags: YouTube
        # surfaces the first few from the description above the title,
        # which is where viewers actually see them. `tags` alone are
        # metadata nobody reads.
        description = _sanitise(target.description).strip()
        if target.hashtags:
            description = f"{description}\n\n" + " ".join(f"#{t}" for t in target.hashtags)

        metadata = {
            "snippet": {
                "title": title,
                "description": description[:5000],
                "tags": target.hashtags[:15],
                "categoryId": _CATEGORY_ID,
            },
            "status": {
                "privacyStatus": target.privacy,
                # Required: YouTube will not accept an upload that does not
                # declare this, and declaring "not for kids" is the honest
                # answer for content the uploader wrote for a general
                # audience. It is theirs to change on the video afterwards.
                "selfDeclaredMadeForKids": False,
            },
        }

        async with httpx.AsyncClient(timeout=_UPLOAD_TIMEOUT) as client:
            # Step one: hand over the metadata, get back somewhere to put
            # the bytes. Resumable rather than a single multipart POST
            # because a failed multipart upload of 30MB has to start over
            # and gives no way to ask how far it got.
            init = await client.post(
                _UPLOAD_URL,
                params={"uploadType": "resumable", "part": "snippet,status"},
                headers={
                    "Authorization": f"Bearer {tokens.access_token}",
                    "X-Upload-Content-Type": "video/mp4",
                    "X-Upload-Content-Length": str(size),
                },
                json=metadata,
            )
            if init.status_code not in (200, 201):
                raise _upload_error(init)

            session_url = init.headers.get("Location")
            if not session_url:
                raise PublishError("YouTube didn't say where to send the video.", retryable=True)

            # Step two: the bytes, in one PUT. A finished ShortPulse render
            # is tens of megabytes, so chunking would add resume logic for
            # a transfer that takes seconds — the resumable session is here
            # for the error reporting, not for the chunking.
            with target.video_path.open("rb") as handle:
                upload = await client.put(
                    session_url,
                    content=handle.read(),
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Length": str(size),
                    },
                )

        if upload.status_code not in (200, 201):
            raise _upload_error(upload)

        body = upload.json()
        video_id = body.get("id")
        if not video_id:
            raise PublishError("YouTube accepted the video but returned no id.", retryable=True)

        return PublishOutcome(
            platform_post_id=video_id,
            url=f"https://youtube.com/watch?v={video_id}",
            # What the API *reports*, which on an unaudited project is
            # "private" however the request was written. Reading it back
            # rather than echoing the request is what lets the UI tell the
            # user the truth about their own video.
            privacy=body.get("status", {}).get("privacyStatus", target.privacy),
        )


def _tokens_from(payload: dict) -> OAuthTokens:
    expires_in = payload.get("expires_in")
    return OAuthTokens(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=(
            datetime.now(UTC) + timedelta(seconds=int(expires_in))
            if expires_in
            else None
        ),
        scopes=str(payload.get("scope", "")).split(),
    )


def _upload_error(response: httpx.Response) -> PublishError:
    """Turn Google's error body into something a user can act on.

    The reason strings come from the documented error list for
    videos.insert. Anything unrecognised is passed through as retryable
    only when the status says so — guessing that an unknown 400 will
    succeed on a second attempt just burns the upload quota twice.
    """
    try:
        error = response.json().get("error", {})
        reason = (error.get("errors") or [{}])[0].get("reason", "")
        detail = error.get("message", "")
    except ValueError:
        reason, detail = "", response.text[:200]

    if reason in ("quotaExceeded", "uploadLimitExceeded", "rateLimitExceeded"):
        return PublishError(
            "YouTube's daily upload limit for this app has been reached. "
            "It resets at midnight Pacific time.",
            retryable=True,
        )
    if reason == "invalidTitle":
        return PublishError("YouTube rejected the title. Try a shorter, plainer one.")
    if reason == "invalidDescription":
        return PublishError("YouTube rejected the description. Try shortening it.")
    if reason == "invalidTags":
        return PublishError("YouTube rejected the hashtags. Remove any unusual characters.")
    if reason == "forbiddenPrivacySetting":
        return PublishError("This channel isn't allowed to publish with that visibility.")
    if reason == "youtubeSignupRequired":
        # A Google account is not a YouTube account. A fresh one has no
        # channel until somebody visits youtube.com and makes one, and
        # uploading to it answers 401 — which read as a dead grant and
        # sent the user to reconnect, retiring a connection that was
        # fine and suggesting the one thing that cannot help. Checked
        # before the status, because the status is the misleading part.
        return PublishError(
            "This Google account doesn't have a YouTube channel yet. Open youtube.com, "
            "create one, then try publishing again — there's no need to reconnect."
        )
    if response.status_code in (401, 403):
        # Logged because this is where an unrecognised reason ends up
        # looking like a revoked grant. Without the reason string there
        # is nothing to tell the difference from the outside.
        logger.warning(
            "YouTube refused the upload (%s, reason=%r): %s",
            response.status_code,
            reason,
            detail[:300],
        )
        return ConnectionRevoked(
            "YouTube refused the upload for this account. Reconnect it and try again."
        )
    if response.status_code >= 500:
        return PublishError("YouTube had a problem accepting the upload.", retryable=True)

    logger.warning("Unmapped YouTube error %s: %s", response.status_code, detail[:300])
    return PublishError(detail or "YouTube rejected the upload.")
