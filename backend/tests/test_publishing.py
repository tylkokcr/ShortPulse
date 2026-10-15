"""The parts of publishing that decide what goes out.

Deliberately not a test of the YouTube client — that is HTTP against
somebody else's service, and mocking it would only assert that the mock
was written to match the code. What is tested here is everything that
would still be wrong if the platform call worked perfectly:

  * the licence credit that automatic publishing would otherwise drop
  * the post copy that has to exist before an unattended render can post
  * the encryption around tokens that are not ours to lose
"""

from __future__ import annotations

import pytest

from app.engines.script_engine import _to_post_copy
from app.schemas.project import (
    Project,
    ProjectConfig,
    Scene,
    SceneAudio,
    SceneVisual,
    ScriptOutput,
    StockAttribution,
    VisualMode,
)
from app.services.publish_manager import compose_description
from app.services.social_tokens import TokenCipher, TokenDecryptionError


def _project(visual_mode: VisualMode, attributions: list[StockAttribution | None]) -> Project:
    scenes = [
        Scene(
            index=i,
            duration_s=4,
            visual=SceneVisual(prompt="x", attribution=a),
            audio=SceneAudio(voiceover_line="line"),
        )
        for i, a in enumerate(attributions)
    ]
    config = ProjectConfig(topic="honey", visual_mode=visual_mode)
    return Project(
        config=config,
        script=ScriptOutput(
            topic="honey", hook="Hook", scenes=scenes, total_duration_s=4 * len(scenes)
        ),
    )


def _credit(author: str) -> StockAttribution:
    return StockAttribution(provider="Pexels", provider_url="https://pexels.com", author=author)


# --------------------------------------------------------------------------
# Attribution
#
# StockAttribution.as_text() was written as "one line a user can paste into
# a post description", which was true while a human wrote every post. These
# tests are the whole reason compose_description exists: with automatic
# publishing there is no human doing the pasting, and the credit is a
# licence condition rather than a courtesy.
# --------------------------------------------------------------------------


def test_stock_credits_are_appended_to_the_description():
    project = _project(VisualMode.STOCK_MEDIA, [_credit("Ada"), _credit("Grace")])
    result = compose_description(project, "Why honey never spoils.")

    assert result.startswith("Why honey never spoils.")
    assert "Video by Ada on Pexels" in result
    assert "Video by Grace on Pexels" in result


def test_one_clip_used_twice_is_credited_once():
    project = _project(VisualMode.STOCK_MEDIA, [_credit("Ada"), _credit("Ada"), _credit("Ada")])
    assert compose_description(project, "d").count("Video by Ada on Pexels") == 1


def test_generated_visuals_have_nobody_to_credit():
    # Not merely "no attributions present": the whole branch is skipped, so
    # a fast_hybrid render never grows a credits block even if a scene
    # somehow carried one.
    project = _project(VisualMode.FAST_HYBRID, [_credit("Ada")])
    assert compose_description(project, "Just this.") == "Just this."


def test_stock_project_with_no_attributions_is_left_alone():
    project = _project(VisualMode.STOCK_MEDIA, [None, None])
    assert compose_description(project, "Just this.") == "Just this."


# --------------------------------------------------------------------------
# Post copy
#
# The automatic path runs when nobody is watching, so the guarantee that
# matters is that this never returns nothing — a publisher holding no
# title cannot post to YouTube at all.
# --------------------------------------------------------------------------


def test_written_copy_is_used_as_written():
    copy = _to_post_copy(
        {"post": {"title": "Why honey never spoils", "description": "Found in tombs.",
                  "hashtags": ["honey", "science"]}},
        "honey", "Hook", None,
    )
    assert copy.title == "Why honey never spoils"
    assert copy.description == "Found in tombs."
    assert copy.hashtags == ["honey", "science"]


def test_a_model_that_omitted_the_post_key_still_produces_copy():
    # The common local-model failure. It must degrade, not return empty.
    copy = _to_post_copy({}, "why honey never spoils", "Honey never goes bad.", "Follow")
    assert copy.title == "Honey never goes bad."
    assert "Follow" in copy.description


def test_hashtags_are_normalised():
    copy = _to_post_copy(
        {"post": {"title": "t", "description": "d",
                  "hashtags": ["#honey", "food science", "HONEY", "", "🍯"]}},
        "t", "h", None,
    )
    # '#' stripped (each platform adds its own), spaces removed, empties and
    # emoji-only tags dropped, case-insensitive duplicates collapsed.
    assert copy.hashtags == ["honey", "foodscience"]


def test_hashtags_given_as_one_string_are_split():
    copy = _to_post_copy(
        {"post": {"title": "t", "description": "d", "hashtags": "#a #b #c"}}, "t", "h", None
    )
    assert copy.hashtags == ["a", "b", "c"]


def test_garbage_in_the_post_key_falls_back_to_the_script():
    copy = _to_post_copy({"post": "nope"}, "topic here", "the hook", None)
    assert copy.title == "the hook"


def test_overlong_copy_is_truncated_rather_than_rejected():
    # A model that wrote 300 characters of title produced usable copy and
    # one unusable field. Losing the post over it would be the wrong trade.
    copy = _to_post_copy(
        {"post": {"title": "x" * 300, "description": "y" * 5000}}, "t", "h", None
    )
    assert len(copy.title) == 100
    assert len(copy.description) == 2200


# --------------------------------------------------------------------------
# Token encryption
# --------------------------------------------------------------------------


def test_tokens_survive_a_round_trip():
    cipher = TokenCipher("a-long-random-secret")
    assert cipher.decrypt(cipher.encrypt("ya29.the-token")) == "ya29.the-token"


def test_ciphertext_does_not_contain_the_token():
    # The point of the column being bytea: a database copy leaking is not
    # the same as the accounts leaking.
    cipher = TokenCipher("a-long-random-secret")
    assert b"ya29.the-token" not in cipher.encrypt("ya29.the-token")


def test_no_refresh_token_is_not_an_error():
    # Normal on platforms that don't issue one.
    assert TokenCipher("s").decrypt(None) is None


def test_a_rotated_secret_is_reported_rather_than_returning_rubbish():
    blob = TokenCipher("original-secret").encrypt("ya29.the-token")
    with pytest.raises(TokenDecryptionError):
        TokenCipher("rotated-secret").decrypt(blob)


def test_tampered_ciphertext_is_rejected():
    # Fernet authenticates, so a modified blob is an error rather than a
    # decrypted lie.
    blob = bytearray(TokenCipher("s").encrypt("ya29.the-token"))
    blob[-1] ^= 0xFF
    with pytest.raises(TokenDecryptionError):
        TokenCipher("s").decrypt(bytes(blob))


# --- the callback has to survive the front door --------------------------
#
# Found in a screen recording of the real flow: the grant succeeded, and
# what came back was {"detail": "Not authenticated"} on a blank page. A
# redirect from Google carries no Authorization header, so with
# REQUIRE_AUTH on the middleware refused it before the route could store
# the tokens — and because the nonce is single-use, reloading could not
# recover it. Publishing was unreachable in production while every unit
# test here passed.


def _callback_app():
    from fastapi import FastAPI

    from app.api.middleware import SupabaseAuthMiddleware
    from app.api.routes import social as social_route

    app = FastAPI()
    app.include_router(social_route.router)
    app.add_middleware(SupabaseAuthMiddleware, verifier=None, require_auth=True, signup_grant=0)
    return app


async def _get(app, path: str):
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, follow_redirects=False)


async def test_the_oauth_callback_is_reachable_without_a_bearer_token():
    """It answers the browser rather than the API client that never called."""
    response = await _get(_callback_app(), "/api/social/callback/youtube?error=access_denied")

    assert response.status_code == 303
    assert "/connections" in response.headers["location"]


async def test_the_rest_of_publishing_still_needs_a_token():
    """The exemption is the callback path, not the feature."""
    response = await _get(_callback_app(), "/api/social/connections")

    assert response.status_code == 401


# --- reading a post back after writing it --------------------------------
#
# Both publish and approve write a row, queue it, then read it back to
# answer with. The read returns `Post | None`, and the None branch went
# straight into the response builder — so a row deleted in that window
# came back as an AttributeError on a 500 rather than the 404 it is.
# Found by the type checker, not by a failure in production.


async def test_a_post_that_vanished_between_write_and_read_is_a_404(monkeypatch):
    from fastapi import HTTPException

    from app.api.routes import social as social_route

    async def gone(pool, post_id):
        return None

    monkeypatch.setattr(social_route.social_store, "get_post", gone)

    with pytest.raises(HTTPException) as exc:
        await social_route._reload_out(pool=None, post_id="post-1")

    assert exc.value.status_code == 404


# --- direct posting to TikTok ----------------------------------------------


def _direct_post_setup(monkeypatch, *, scopes=("user.info.basic", "video.upload", "video.publish"),
                       source="generated"):
    from types import SimpleNamespace

    from app.api.routes import social as social_route
    from app.schemas.project import Project, ProjectConfig, ProjectSource
    from app.services.social.base import OAuthTokens
    from app.services.social.tiktok import TikTokPublisher

    created: list[dict] = []
    project = Project(config=ProjectConfig(topic="t", source=ProjectSource(source)), output_path="/v.mp4")

    async def owner_of(pid):
        return "u1"

    async def get_project(pid):
        return project

    async def load_for_publish(pool, cid, cipher):
        return SimpleNamespace(
            id="c1", platform="tiktok", user_id="u1", external_account_id="open1",
            tokens=OAuthTokens(access_token="at", scopes=list(scopes)),
        )

    async def create_post(pool, **kw):
        created.append(kw)
        return "post-1"

    async def reload_out(pool, post_id):
        return post_id

    class Queue:
        enabled = True

        async def submit(self, post_id):
            pass

    monkeypatch.setattr(social_route, "_require_pool", lambda request: object())
    monkeypatch.setattr(social_route.project_store, "owner_of", owner_of)
    monkeypatch.setattr(social_route.project_store, "get_project", get_project)
    monkeypatch.setattr(social_route.social_store, "load_for_publish", load_for_publish)
    monkeypatch.setattr(social_route.social_store, "create_post", create_post)
    monkeypatch.setattr(social_route, "_reload_out", reload_out)
    publisher = TikTokPublisher("k", "s", "https://x/cb", direct_post=True)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                publishers={"tiktok": publisher}, publish_queue=Queue(), token_cipher=None
            )
        )
    )
    return social_route, request, created


async def test_a_direct_tiktok_post_is_queued_with_the_choices_made(monkeypatch):
    social_route, request, created = _direct_post_setup(monkeypatch)
    body = social_route.PublishRequest(
        project_id="p", connection_id="c1", title="Başlık",
        tiktok=social_route.TikTokChoices(privacy_level="SELF_ONLY", allow_comment=True),
    )
    await social_route.publish_now(body, request, user_id="u1")
    options = created[0]["options"]
    assert options["mode"] == "direct" and options["privacy_level"] == "SELF_ONLY"
    assert options["allow_comment"] is True and options["allow_duet"] is False
    # A video the pipeline wrote, voiced and illustrated is labelled as AI content.
    assert options["is_aigc"] is True
    assert created[0]["privacy"] == "private"


async def test_branded_content_cannot_be_private_and_a_level_must_be_known(monkeypatch):
    from fastapi import HTTPException

    social_route, request, created = _direct_post_setup(monkeypatch)
    for choice in (
        social_route.TikTokChoices(privacy_level="SELF_ONLY", brand_content=True),
        social_route.TikTokChoices(privacy_level="EVERYONE_PLEASE"),
    ):
        body = social_route.PublishRequest(project_id="p", connection_id="c1", title="t", tiktok=choice)
        with pytest.raises(HTTPException) as exc:
            await social_route.publish_now(body, request, user_id="u1")
        assert exc.value.status_code == 422
    assert created == []


async def test_direct_posting_needs_the_scope_and_own_footage_is_not_ai(monkeypatch):
    from fastapi import HTTPException

    social_route, request, created = _direct_post_setup(
        monkeypatch, scopes=("user.info.basic", "video.upload")
    )
    body = social_route.PublishRequest(
        project_id="p", connection_id="c1", title="t",
        tiktok=social_route.TikTokChoices(privacy_level="PUBLIC_TO_EVERYONE"),
    )
    with pytest.raises(HTTPException) as exc:
        await social_route.publish_now(body, request, user_id="u1")
    assert exc.value.status_code == 409

    social_route, request, created = _direct_post_setup(monkeypatch, source="beat_edit")
    await social_route.publish_now(body, request, user_id="u1")
    assert created[0]["options"]["is_aigc"] is False
