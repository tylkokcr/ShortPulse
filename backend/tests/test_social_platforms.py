"""The three platforms added after YouTube, at the seams that can be tested.

Deliberately not a test of the Graph API or the Content Posting API —
those are HTTP against somebody else's service, and a mock of them would
assert only that the mock was written to match the code. What is tested
here is what would still be wrong if every remote call succeeded:

  * which platforms a deployment offers, given what it is configured for
  * that the authorize URLs carry what each platform demands, including
    the two places TikTok departs from everyone else
  * that an error the user will read is produced for the failures that
    are operator mistakes rather than user mistakes
  * that a revoked grant is told apart from a failed post, because the
    manager retires a connection on one and not the other
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.core.config import Settings
from app.services.social import PLATFORMS, build_publishers
from app.services.social.base import ConnectionRevoked, PublishError
from app.services.social.facebook import FacebookPublisher
from app.services.social.instagram import InstagramPublisher
from app.services.social.meta import graph_error
from app.services.social.tiktok import TikTokPublisher, _download_failure, _mapped_error


def _settings(**overrides) -> Settings:
    base = {
        "social_token_secret": "test-secret",
        "public_base_url": "https://shortpulse.app",
    }
    return Settings(**{**base, **overrides})


def _query(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


# --- what a deployment offers -------------------------------------------


def test_nothing_is_offered_without_the_encryption_key():
    """The precondition for all of them, not a per-platform setting."""
    publishers = build_publishers(
        _settings(social_token_secret=None, youtube_client_id="a", youtube_client_secret="b")
    )

    assert publishers == {}


def test_a_platform_with_no_credentials_is_absent_rather_than_broken():
    publishers = build_publishers(
        _settings(youtube_client_id="a", youtube_client_secret="b")
    )

    assert sorted(publishers) == ["youtube"]


def test_facebook_credentials_do_not_offer_instagram():
    """They used to, and that was the bug.

    Instagram Business Login issues its own app id and secret; the
    Facebook pair is refused by instagram.com's dialog. Offering the
    button anyway meant the connect flow died before the user reached a
    consent screen, with nothing on our side to explain it.
    """
    publishers = build_publishers(_settings(meta_app_id="a", meta_app_secret="b"))

    assert sorted(publishers) == ["facebook"]


def test_instagram_is_configured_on_its_own():
    publishers = build_publishers(
        _settings(instagram_app_id="a", instagram_app_secret="b")
    )

    assert sorted(publishers) == ["instagram"]


def test_tiktok_is_configured_on_its_own():
    publishers = build_publishers(
        _settings(tiktok_client_key="a", tiktok_client_secret="b")
    )

    assert sorted(publishers) == ["tiktok"]


def test_every_named_platform_can_actually_be_built():
    """PLATFORMS is what the UI orders by; a name with no publisher
    behind it would be a button that cannot work."""
    publishers = build_publishers(
        _settings(
            youtube_client_id="a",
            youtube_client_secret="b",
            meta_app_id="c",
            meta_app_secret="d",
            instagram_app_id="g",
            instagram_app_secret="h",
            tiktok_client_key="e",
            tiktok_client_secret="f",
        )
    )

    assert sorted(publishers) == sorted(PLATFORMS)


def test_each_publisher_answers_to_its_own_name():
    """The registry key and the publisher's own `platform` have to agree:
    the manager looks a publisher up by the connection's platform and
    stores results under the publisher's."""
    publishers = build_publishers(
        _settings(
            youtube_client_id="a",
            youtube_client_secret="b",
            meta_app_id="c",
            meta_app_secret="d",
            instagram_app_id="g",
            instagram_app_secret="h",
            tiktok_client_key="e",
            tiktok_client_secret="f",
        )
    )

    assert all(name == publisher.platform for name, publisher in publishers.items())


# --- the authorize URLs -------------------------------------------------


def test_tiktok_sends_client_key_rather_than_client_id():
    """TikTok is alone in this, and getting it wrong produces a generic
    invalid-request page that names no parameter."""
    url = TikTokPublisher("KEY", "secret", "https://shortpulse.app/cb").authorize_url("nonce")

    query = _query(url)
    assert query["client_key"] == "KEY"
    assert "client_id" not in query


def test_tiktok_separates_scopes_with_commas():
    """Spaces are what the other three want and what TikTok rejects."""
    url = TikTokPublisher("KEY", "secret", "https://shortpulse.app/cb").authorize_url("nonce")

    assert _query(url)["scope"] == "user.info.basic,video.upload"


def test_tiktok_does_not_ask_to_post_directly():
    """`video.publish` is a second review, and posting without the user
    seeing it first is not the product."""
    url = TikTokPublisher("KEY", "secret", "https://shortpulse.app/cb").authorize_url("nonce")

    assert "video.publish" not in _query(url)["scope"]


def test_instagram_asks_for_the_permission_that_posts():
    """The business-login name, not the Facebook-login one. Without this
    scope the account connects and every publish afterwards is refused."""
    url = InstagramPublisher("ID", "secret", "https://shortpulse.app/cb").authorize_url("nonce")

    assert "instagram_business_content_publish" in _query(url)["scope"]


def test_instagram_logs_in_through_instagram_not_facebook():
    """The whole reason this publisher was rewritten.

    The app declares the "Manage messaging & content on Instagram" use
    case, which is Instagram Business Login. Sending the user to
    facebook.com with an app id that route never granted fails before any
    consent screen, so nothing on our side would say why.
    """
    url = InstagramPublisher("ID", "secret", "https://shortpulse.app/cb").authorize_url("nonce")

    assert url.startswith("https://www.instagram.com/oauth/authorize")
    assert "facebook.com" not in url


def test_facebook_does_not_ask_for_the_deprecated_publish_permission():
    url = FacebookPublisher("ID", "secret", "https://shortpulse.app/cb").authorize_url("nonce")

    scope = _query(url)["scope"]
    assert "pages_manage_posts" in scope
    assert "publish_video" not in scope


@pytest.mark.parametrize(
    "publisher",
    [
        TikTokPublisher("k", "s", "https://shortpulse.app/cb"),
        InstagramPublisher("k", "s", "https://shortpulse.app/cb"),
        FacebookPublisher("k", "s", "https://shortpulse.app/cb"),
    ],
    ids=["tiktok", "instagram", "facebook"],
)
def test_the_state_nonce_survives_into_the_url(publisher):
    """It is what stops a third party finishing somebody else's connect."""
    assert _query(publisher.authorize_url("the-nonce"))["state"] == "the-nonce"


# --- errors the user has to be able to act on ---------------------------


def test_an_unverified_domain_is_reported_as_an_operator_problem():
    """The user can do nothing about it, so the message must not suggest
    retrying. It means nobody verified the domain in TikTok's portal."""
    error = _download_failure("url_ownership_unverified")

    assert not error.retryable
    assert "isn't set up" in str(error)


def test_the_unapproved_app_cap_says_when_to_come_back():
    """Otherwise a user retries all evening against a daily limit."""
    error = _mapped_error({"code": "spam_risk_too_many_posts", "message": ""})

    assert "tomorrow" in str(error)


def test_a_dead_tiktok_grant_is_not_a_failed_post():
    """The manager retires the connection on one and retries the other."""
    assert isinstance(
        _mapped_error({"code": "access_token_invalid", "message": ""}), ConnectionRevoked
    )


def test_a_dead_meta_grant_is_not_a_failed_post():
    response = httpx.Response(400, json={"error": {"code": 190, "message": "expired"}})

    assert isinstance(graph_error(response, action="video"), ConnectionRevoked)


def test_meta_rate_limiting_is_worth_retrying():
    response = httpx.Response(400, json={"error": {"code": 4, "message": "too many calls"}})

    error = graph_error(response, action="video")
    assert error.retryable
    assert not isinstance(error, ConnectionRevoked)


def test_an_unrecognised_meta_error_still_reaches_the_user():
    """Passed through rather than swallowed: an unmapped message is worth
    more to somebody reading it than 'something went wrong'."""
    response = httpx.Response(
        400, json={"error": {"code": 100, "message": "Invalid parameter: file_url"}}
    )

    error = graph_error(response, action="video")
    assert isinstance(error, PublishError)
    assert "file_url" in str(error)


# --- the one that cost a demo recording ---------------------------------


def test_an_account_with_no_channel_is_not_a_revoked_grant():
    """A fresh Google account has no YouTube channel, and uploading to one
    answers 401. Read as a dead grant it retires a perfectly good
    connection and tells the user to do the one thing that cannot help."""
    from app.services.social.youtube import _upload_error

    response = httpx.Response(
        401,
        json={
            "error": {
                "errors": [{"reason": "youtubeSignupRequired"}],
                "message": "Unauthorized",
            }
        },
    )

    error = _upload_error(response)
    assert not isinstance(error, ConnectionRevoked)
    assert "youtube.com" in str(error)


def test_an_actually_dead_youtube_grant_is_still_reported_as_one():
    """The narrower case must not have swallowed the general one."""
    from app.services.social.youtube import _upload_error

    response = httpx.Response(
        401, json={"error": {"errors": [{"reason": "authError"}], "message": "Invalid"}}
    )

    assert isinstance(_upload_error(response), ConnectionRevoked)


def test_a_grant_without_the_upload_scope_is_refused_at_connect_time():
    """The consent screen's permissions are checkboxes and unticking the
    YouTube one still completes the flow. Stored, that grant fails much
    later as a 403 that reads as a revoked account."""
    import asyncio

    import httpx as _httpx

    from app.services.social.youtube import YouTubePublisher

    def handler(request: _httpx.Request) -> _httpx.Response:
        return _httpx.Response(
            200,
            json={
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": 3600,
                # Signed in, but never granted the upload permission.
                "scope": "openid email profile",
            },
        )

    publisher = YouTubePublisher("id", "secret", "https://shortpulse.app/cb")
    transport = _httpx.MockTransport(handler)

    async def run():
        import app.services.social.youtube as mod

        original = _httpx.AsyncClient

        def patched(*args, **kwargs):
            kwargs["transport"] = transport
            return original(*args, **kwargs)

        mod.httpx.AsyncClient = patched
        try:
            await publisher.exchange_code("code")
        finally:
            mod.httpx.AsyncClient = original

    with pytest.raises(PublishError) as caught:
        asyncio.run(run())

    assert "permission to upload" in str(caught.value)


def test_a_tiktok_grant_without_the_upload_scope_is_refused_at_connect_time():
    """Same shape as the YouTube case, with a worse ending: the first post
    fails with a permission error that reads as a dead grant, so the
    account the user just connected disappears from their list."""
    import asyncio

    import httpx as _httpx

    from app.services.social import tiktok as mod

    def handler(request: _httpx.Request) -> _httpx.Response:
        return _httpx.Response(
            200,
            json={
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": 3600,
                "open_id": "oid",
                # Signed in; never allowed to upload.
                "scope": "user.info.basic",
            },
        )

    publisher = mod.TikTokPublisher("key", "secret", "https://shortpulse.app/cb")
    transport = _httpx.MockTransport(handler)
    original = _httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    mod.httpx.AsyncClient = patched
    try:
        with pytest.raises(PublishError) as caught:
            asyncio.run(publisher.exchange_code("code"))
    finally:
        mod.httpx.AsyncClient = original

    assert "permission to upload" in str(caught.value)


def test_an_unverified_domain_does_not_retire_the_connection():
    """Observed in production: TikTok answers the upload 403 with
    url_ownership_unverified, _api_error read the status before the body,
    and the account the user had just connected was deleted with a note
    telling them to reconnect it — which cannot fix a domain nobody
    verified, so they would do it again."""
    from app.services.social.tiktok import _api_error

    response = httpx.Response(
        403,
        json={
            "error": {
                "code": "url_ownership_unverified",
                "message": "Please review our URL ownership verification rules",
            }
        },
    )

    error = _api_error(response)
    assert not isinstance(error, ConnectionRevoked)
    assert "isn't set up" in str(error)


def test_a_403_with_no_code_is_still_treated_as_a_dead_grant():
    """Reading the body first must not have lost the fallback."""
    from app.services.social.tiktok import _api_error

    assert isinstance(_api_error(httpx.Response(403, text="nope")), ConnectionRevoked)


# --- the Instagram business-login flow ----------------------------------
#
# The publisher was rewritten from Facebook Login to Instagram Business
# Login, which changes every call in it: a different dialog, a different
# token host, a different graph, and a refresh that is a real refresh
# rather than a second exchange. A scope assertion alone would not have
# noticed any of that, so these follow the flow to the hosts it uses.


class _FakeInstagram:
    """Enough of Instagram's three hosts to complete a connection."""

    def __init__(self, *, token_shape: str = "flat") -> None:
        self.token_shape = token_shape
        self.seen: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.seen.append(url)

        if url.startswith("https://api.instagram.com/oauth/access_token"):
            body = {
                "access_token": "short-lived",
                "user_id": 17841400000000000,
                "permissions": "instagram_business_basic,instagram_business_content_publish",
            }
            if self.token_shape == "wrapped":
                body = {"data": [body]}
            return httpx.Response(200, json=body)

        if url.startswith("https://graph.instagram.com/access_token"):
            return httpx.Response(
                200, json={"access_token": "long-lived", "expires_in": 5184000}
            )

        if url.startswith("https://graph.instagram.com/refresh_access_token"):
            return httpx.Response(
                200, json={"access_token": "refreshed", "expires_in": 5184000}
            )

        if url.startswith("https://graph.instagram.com/me"):
            return httpx.Response(
                200, json={"user_id": "17841400000000000", "username": "shortpulse"}
            )

        raise AssertionError(f"unexpected request: {url}")


def _serve_instagram(monkeypatch, fake: _FakeInstagram) -> _FakeInstagram:
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(fake))
    )
    return fake


def _instagram() -> InstagramPublisher:
    return InstagramPublisher("IG_ID", "ig-secret", "https://shortpulse.app/cb")


async def test_connecting_ends_on_a_long_lived_token(monkeypatch):
    """The short-lived one would die before the first scheduled post, and
    it cannot be lengthened after it expires."""
    fake = _serve_instagram(monkeypatch, _FakeInstagram())

    tokens, account = await _instagram().exchange_code("the-code")

    assert tokens.access_token == "long-lived"
    assert account.external_id == "17841400000000000"
    assert account.display_name == "@shortpulse"
    assert any("ig_exchange_token" in url for url in fake.seen)


async def test_the_token_response_may_be_wrapped_in_data(monkeypatch):
    """Documented as {"data": [...]} and returned flat by some app
    configurations. Reading only one shape fails with nothing in the
    response to explain it."""
    _serve_instagram(monkeypatch, _FakeInstagram(token_shape="wrapped"))

    tokens, account = await _instagram().exchange_code("the-code")

    assert tokens.access_token == "long-lived"
    assert account.external_id == "17841400000000000"


async def test_the_refresh_token_is_the_access_token(monkeypatch):
    """ig_refresh_token presents the token itself — there is no second
    credential, and storing None would make the connection unrenewable."""
    _serve_instagram(monkeypatch, _FakeInstagram())

    tokens, _ = await _instagram().exchange_code("the-code")

    assert tokens.refresh_token == tokens.access_token


async def test_nothing_in_the_connect_flow_touches_facebook(monkeypatch):
    """The bug this rewrite fixes. Every host here is Instagram's."""
    fake = _serve_instagram(monkeypatch, _FakeInstagram())

    await _instagram().exchange_code("the-code")

    assert fake.seen
    assert not any("facebook.com" in url for url in fake.seen)


async def test_refreshing_asks_instagram_to_extend_the_token(monkeypatch):
    fake = _serve_instagram(monkeypatch, _FakeInstagram())

    tokens = await _instagram().refresh("long-lived")

    assert tokens.access_token == "refreshed"
    assert any("ig_refresh_token" in url for url in fake.seen)


async def test_a_dead_grant_is_reported_as_revoked_rather_than_retried(monkeypatch):
    """A token past its window cannot be refreshed at all, so retrying is
    how a queue fills with posts that can never succeed."""

    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "expired"}})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(refuse))
    )

    with pytest.raises(ConnectionRevoked):
        await _instagram().refresh("long-dead")


# --- saying why a platform is missing ------------------------------------
#
# Absence is this feature's failure mode. A platform that is not
# configured is simply not on the Connections page — no error, nothing in
# the API to tell "this deployment doesn't offer it" apart from "you
# spelled the variable wrong". That cost a deploy cycle: the Instagram
# credentials were set as INSTAGRAM_CLIENT_ID/SECRET, which is what Meta's
# OAuth dialog calls them, while this reads INSTAGRAM_APP_ID/SECRET, which
# is what Meta's console labels them.


def test_the_other_true_name_is_called_out(monkeypatch, caplog):
    """Not a typo — both spellings are Meta's, for the same pair. So the
    message has to name the one in use and the one expected."""
    monkeypatch.setenv("INSTAGRAM_CLIENT_ID", "4465462800339235")
    monkeypatch.setenv("INSTAGRAM_CLIENT_SECRET", "secret")
    monkeypatch.delenv("INSTAGRAM_APP_ID", raising=False)
    monkeypatch.delenv("INSTAGRAM_APP_SECRET", raising=False)

    with caplog.at_level("WARNING"):
        build_publishers(_settings(meta_app_id="a", meta_app_secret="b"))

    warning = "\n".join(caplog.messages)
    assert "INSTAGRAM_CLIENT_ID" in warning
    assert "INSTAGRAM_APP_ID" in warning


def test_half_a_pair_is_called_out(monkeypatch, caplog):
    """An id with no secret builds nothing, and looked identical to no
    configuration at all."""
    monkeypatch.setenv("INSTAGRAM_APP_ID", "4465462800339235")
    monkeypatch.delenv("INSTAGRAM_APP_SECRET", raising=False)
    monkeypatch.delenv("INSTAGRAM_CLIENT_ID", raising=False)
    monkeypatch.delenv("INSTAGRAM_CLIENT_SECRET", raising=False)

    with caplog.at_level("WARNING"):
        build_publishers(_settings(instagram_app_id="4465462800339235"))

    warning = "\n".join(caplog.messages)
    assert "INSTAGRAM_APP_SECRET" in warning
    assert "needs both" in warning


def test_a_platform_nobody_configured_says_nothing(monkeypatch, caplog):
    """A self-hosted install that publishes nowhere is not misconfigured,
    and a warning per platform per boot would train the operator to skip
    the log that matters."""
    for name in (
        "INSTAGRAM_APP_ID", "INSTAGRAM_APP_SECRET",
        "INSTAGRAM_CLIENT_ID", "INSTAGRAM_CLIENT_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)

    with caplog.at_level("WARNING"):
        build_publishers(_settings(meta_app_id="a", meta_app_secret="b"))

    assert not caplog.messages
