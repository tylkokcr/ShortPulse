"""Publishing to a Facebook Page, via the Graph API.

The simplest of the four, and the only one that takes the video in a
single call: no container to poll like Instagram, no job id to watch like
TikTok, no resumable session like YouTube. Post the URL, get a video id.

What it does share with Instagram is everything before that — the same
Meta app, the same login dialog, the same sixty-day token, the same
business verification standing between this code and anybody but the
developer using it. See meta.py, which holds all of it.

One asymmetry worth stating: a Page, not a profile. There is no API for
posting to a personal Facebook timeline and has not been for years, so a
user with no Page cannot be connected at all. That is refused at connect
time with a sentence saying so, rather than at publish time when the
render has already been paid for.
"""

from __future__ import annotations

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

# `pages_manage_posts` is the one that posts; the other two are what it
# takes to find the Page and prove we may act for it. Note that
# `publish_video` — the older permission these replaced — is not asked
# for: it is deprecated and asking would add a scope the review has to
# justify for nothing.
_SCOPES = [
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
]


class FacebookPublisher:
    platform = "facebook"

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

            page_list = await meta.pages(client, tokens.access_token)

        if not page_list:
            raise PublishError(
                "This Facebook account doesn't manage any Pages. Facebook only allows apps to "
                "post to Pages, not to personal profiles."
            )

        # The first Page, and the id is recorded so every later publish
        # goes to this one specifically — see meta.page_token. Choosing
        # among several belongs in the UI, and until that exists picking
        # deterministically and showing the name is better than asking a
        # question the interface cannot yet accept an answer to.
        page = page_list[0]
        if len(page_list) > 1:
            logger.info(
                "Facebook account manages %d Pages; connected %s", len(page_list), page.get("id")
            )

        return tokens, PlatformAccount(
            external_id=str(page["id"]), display_name=page.get("name")
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
            raise PublishError("There is no link for Facebook to fetch the video from.")

        page_id = target.account_id
        if not page_id:
            raise PublishError("This connection doesn't say which Facebook Page to post to.")

        async with httpx.AsyncClient(timeout=meta.API_TIMEOUT) as client:
            # Derived per publish rather than stored: a Page token from a
            # live user token does not expire, so the fresh one is always
            # at least as good as a saved one and cannot outlive the
            # permission behind it.
            posting_token = await meta.page_token(client, tokens.access_token, page_id)

            response = await client.post(
                f"{meta.GRAPH}/{page_id}/videos",
                data={
                    # Facebook fetches it, the same as Instagram and
                    # TikTok — `file_url` rather than a multipart body.
                    "file_url": target.video_url,
                    "title": target.title.strip()[:255],
                    "description": _description(target),
                    "access_token": posting_token,
                },
            )

        if response.status_code != 200:
            raise meta.graph_error(response, action="video")

        video_id = response.json().get("id")
        if not video_id:
            raise PublishError("Facebook accepted the video but returned no id.", retryable=True)

        return PublishOutcome(
            platform_post_id=str(video_id),
            url=f"https://www.facebook.com/{video_id}",
            # A Page post is as public as the Page. There is no per-video
            # visibility in this call, so reporting the requested privacy
            # would be inventing one.
            privacy="page",
        )


def _description(target: PublishTarget) -> str:
    description = target.description.strip()
    if target.hashtags:
        description = f"{description}\n\n" + " ".join(f"#{t}" for t in target.hashtags)
    return description
