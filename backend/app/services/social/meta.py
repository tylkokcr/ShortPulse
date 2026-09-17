"""What Instagram and Facebook publishing share.

They are one app with one review, not two integrations that happen to be
owned by the same company: the same Meta app id, the same Facebook Login
dialog, the same business verification gate. Only the last step differs —
a Reel goes through a container, a Page video does not — so everything up
to "which account am I posting to" lives here and the two publishers are
thin.

Meta's token model is the reason this file exists at all, because it does
not fit the shape the other two platforms taught:

  * **There is no refresh token.** Facebook Login returns a short-lived
    user token, which is exchanged once for a long-lived one good for
    about sixty days. Extending it means exchanging the long-lived token
    *for another one* while it is still valid — there is no separate
    credential to do it with. So `refresh_token` here holds a copy of the
    user token, which reads oddly until you know that the thing being
    presented to renew the grant and the thing being renewed are the same
    string. The alternative was a second column for one platform.
  * **A user token cannot post.** Posting is done with a Page access
    token, derived from the user token via /me/accounts. Those do not
    expire while the user token is alive, but they are re-derived on
    every publish rather than stored: it costs one call, and it means a
    user who reconnects a different Page, or whose Page token is
    invalidated, self-heals instead of failing until somebody notices.
  * **Sixty days is the real lifetime.** When it lapses the user
    reconnects; nothing here can prevent that, and pretending otherwise
    would turn a predictable prompt into a silent dead connection.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.services.social.base import (
    ConnectionRevoked,
    OAuthTokens,
    PublishError,
)

logger = logging.getLogger(__name__)

# Pinned rather than floating. Meta retires versions on a published
# schedule and an unversioned call follows whatever is current, which is
# how an integration breaks on a morning nobody deployed anything.
API_VERSION = "v21.0"
GRAPH = f"https://graph.facebook.com/{API_VERSION}"
_DIALOG_URL = f"https://www.facebook.com/{API_VERSION}/dialog/oauth"

API_TIMEOUT = httpx.Timeout(30.0)

# Long-lived tokens last ~60 days. Recorded as 55 so the connection asks
# to be renewed while renewing is still possible: an expiry read as "now"
# is a reconnect, and the margin is the difference between a background
# extension and a user finding a dead account.
_LONG_LIVED_DAYS = 55


def authorize_url(client_id: str, redirect_uri: str, scopes: list[str], state: str) -> str:
    return f"{_DIALOG_URL}?" + urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": ",".join(scopes),
            "state": state,
        }
    )


async def exchange_code_for_user_token(
    client: httpx.AsyncClient,
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
) -> OAuthTokens:
    """The redirect's code, turned into a token worth storing.

    Two calls rather than one: the code buys a short-lived token, and
    storing that would give a connection that dies in an hour or two. The
    exchange to long-lived is not optional and has no separate endpoint —
    it is the same endpoint with a different grant_type.
    """
    short = await client.get(
        f"{GRAPH}/oauth/access_token",
        params={
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )
    if short.status_code != 200:
        raise PublishError("Facebook refused to complete the connection. Try connecting again.")

    short_token = short.json().get("access_token")
    if not short_token:
        raise PublishError("Facebook refused to complete the connection. Try connecting again.")

    return await extend(
        client, client_id=client_id, client_secret=client_secret, token=short_token
    )


async def extend(
    client: httpx.AsyncClient, *, client_id: str, client_secret: str, token: str
) -> OAuthTokens:
    """Swap a token for one that lasts, or for a fresher copy of itself.

    Used both at connect time and at renewal, because Meta makes no
    distinction between them: `fb_exchange_token` on a short-lived token
    returns a long-lived one, and on a long-lived token returns another
    long-lived one.
    """
    response = await client.get(
        f"{GRAPH}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "fb_exchange_token": token,
        },
    )
    if response.status_code in (400, 401, 403):
        raise ConnectionRevoked(
            "Your Facebook login for ShortPulse has expired. Reconnect it to publish again."
        )
    if response.status_code != 200:
        raise PublishError("Couldn't renew access to Facebook.", retryable=True)

    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise PublishError("Couldn't renew access to Facebook.", retryable=True)

    expires_in = payload.get("expires_in")
    expires_at = (
        datetime.now(UTC) + timedelta(seconds=int(expires_in))
        if expires_in
        else datetime.now(UTC) + timedelta(days=_LONG_LIVED_DAYS)
    )

    return OAuthTokens(
        access_token=access_token,
        # The same string twice, deliberately — see the module docstring.
        # Renewal presents the user token itself, so this is not a second
        # credential but the only one there is.
        refresh_token=access_token,
        expires_at=expires_at,
    )


async def pages(client: httpx.AsyncClient, user_token: str) -> list[dict]:
    """The Pages this user administers, each with its own access token.

    A Page token from a long-lived user token does not expire on its own,
    which is why nothing here stores one: it is cheap to ask for and
    always current, and a stored one would outlive the permission that
    justified it.
    """
    response = await client.get(
        f"{GRAPH}/me/accounts",
        params={"fields": "id,name,access_token", "access_token": user_token},
    )
    if response.status_code in (401, 403):
        raise ConnectionRevoked(
            "Facebook no longer allows ShortPulse to use this account. Reconnect it."
        )
    if response.status_code != 200:
        raise PublishError("Couldn't read your Facebook Pages.", retryable=True)

    return response.json().get("data", [])


async def page_token(client: httpx.AsyncClient, user_token: str, page_id: str) -> str:
    """The posting credential for one specific Page.

    Resolved by id rather than by taking the first Page, because an
    account with several would otherwise publish to whichever one Meta
    happened to list first — and which one that is can change.
    """
    for page in await pages(client, user_token):
        if str(page.get("id")) == str(page_id):
            token = page.get("access_token")
            if token:
                return token
            break

    raise ConnectionRevoked(
        "ShortPulse no longer has access to that Facebook Page. Reconnect the account."
    )


def graph_error(response: httpx.Response, *, action: str) -> PublishError:
    """Meta's error body, turned into something a user can act on.

    The codes are the documented ones. 190 in particular has to be
    separated from the rest: it means the grant is gone, and retrying a
    dead token forever is how a queue fills up with posts that can never
    succeed.
    """
    try:
        error = response.json().get("error", {})
    except ValueError:
        error = {}

    code = error.get("code")
    subcode = error.get("error_subcode")
    message = error.get("message", "")

    if code == 190 or response.status_code in (401, 403):
        # Logged for the same reason as the other two: this answer retires
        # the connection, and a mislabelled permission problem then looks
        # like the user's account revoking itself.
        logger.warning(
            "Meta refused the %s (%s, code=%s/%s): %s",
            action,
            response.status_code,
            code,
            subcode,
            message[:300],
        )
        return ConnectionRevoked(
            "Facebook no longer allows ShortPulse to post for you. Reconnect the account."
        )
    if code in (4, 17, 32, 613):
        return PublishError(
            "Facebook is rate-limiting posts from this app. Try again later.", retryable=True
        )
    if code == 200 or subcode == 1363047:
        return PublishError(
            "This account is missing a permission ShortPulse needs to post. Reconnect it."
        )
    if code == 100:
        return PublishError(message or f"Facebook rejected the {action}.")
    if response.status_code >= 500:
        return PublishError(f"Facebook had a problem with the {action}.", retryable=True)

    logger.warning("Unmapped Meta error %s/%s: %s", code, subcode, message[:300])
    return PublishError(message or f"Facebook rejected the {action}.")
