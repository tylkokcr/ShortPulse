"""Selling only what this install can actually render.

generate_scene_visual falls back to stock footage when a generation mode
fails, which is right on a self-hosted machine — a missing GPU shouldn't
mean no video. On a deployment that charges by mode it was something else:
`fast_hybrid` costs three credits, the shipped container has no diffusion
stack, and the fallback is invisible in the output because a stock-footage
video looks exactly like a finished video. Three credits taken, a
one-credit product delivered, no error anywhere.

So availability is decided before anything is charged, and the fallback —
if it still happens — re-prices the render.
"""

from __future__ import annotations

import pytest

from app.engines import visual_engine
from app.schemas.project import VisualMode


class Settings:
    def __init__(self, pexels="key", pixabay=None, replicate=None, provider="local"):
        self.pexels_api_key = pexels
        self.pixabay_api_key = pixabay
        self.replicate_api_token = replicate
        self.visual_provider = provider


def _no_hosted_images(monkeypatch):
    """Take the Replicate token off the real settings for one test.

    The API routes read get_settings(), which reads whatever .env the
    machine running the tests happens to have. Anything asserting that a
    generated mode is *unavailable* has to say so explicitly or it is
    really asserting that the developer has no token.
    """
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "replicate_api_token", None)


# --- what this install can do -------------------------------------------


def test_stock_media_needs_a_provider_key():
    assert visual_engine.unavailable_reason(VisualMode.STOCK_MEDIA, Settings()) is None
    reason = visual_engine.unavailable_reason(
        VisualMode.STOCK_MEDIA, Settings(pexels=None, pixabay=None)
    )
    assert reason is not None and "Pexels" in reason


def test_either_stock_provider_is_enough():
    """Providers fall through to one another, so one key is a working
    install rather than a half-configured one."""
    settings = Settings(pexels=None, pixabay="key")
    assert visual_engine.unavailable_reason(VisualMode.STOCK_MEDIA, settings) is None


@pytest.mark.parametrize("mode", [VisualMode.FAST_HYBRID, VisualMode.AI_VIDEO])
def test_generated_modes_report_the_dependency_they_are_missing(monkeypatch, mode):
    """The container ships without the diffusion stack on purpose — ~3GB
    and useless without a GPU — so this is the deployed case, not an edge
    case. The reason names the package so a self-hoster can act on it."""
    monkeypatch.setattr(
        visual_engine.importlib.util,
        "find_spec",
        lambda name: None if name in ("torch", "diffusers") else object(),
    )
    reason = visual_engine.unavailable_reason(mode, Settings())
    assert reason is not None
    assert "torch" in reason and "diffusers" in reason


def test_available_modes_is_what_is_left(monkeypatch):
    monkeypatch.setattr(
        visual_engine.importlib.util,
        "find_spec",
        lambda name: None if name in ("torch", "diffusers") else object(),
    )
    assert visual_engine.available_modes(Settings()) == [VisualMode.STOCK_MEDIA]


def _no_local_diffusion(monkeypatch):
    monkeypatch.setattr(
        visual_engine.importlib.util,
        "find_spec",
        lambda name: None if name in ("torch", "diffusers") else object(),
    )


def test_a_token_makes_fast_hybrid_available_without_torch(monkeypatch):
    """The deployed shape: a CPU container that cannot import diffusers
    still sells the mode, because the same checkpoint runs on Replicate."""
    _no_local_diffusion(monkeypatch)
    settings = Settings(replicate="r8_test", provider="replicate")
    assert visual_engine.unavailable_reason(VisualMode.FAST_HYBRID, settings) is None
    assert visual_engine.image_backend(settings) is visual_engine.ImageBackend.REPLICATE
    assert visual_engine.available_modes(settings) == [
        VisualMode.FAST_HYBRID,
        VisualMode.STOCK_MEDIA,
    ]


def test_ai_video_is_still_refused_without_torch(monkeypatch):
    """A deliberate product decision, pinned so nobody later 'fixes' it.

    ai_video is priced at 10 credits, about €0.90 on the cheapest pack.
    Hosted text-to-video runs about $0.04 a second, so the ~24 seconds of
    output a short produces costs roughly $0.96 to make. There is no API
    route behind this mode because every render sold would lose money.
    """
    _no_local_diffusion(monkeypatch)
    settings = Settings(replicate="r8_test", provider="replicate")
    reason = visual_engine.unavailable_reason(VisualMode.AI_VIDEO, settings)
    assert reason is not None
    assert VisualMode.AI_VIDEO not in visual_engine.available_modes(settings)


def test_the_fast_hybrid_reason_names_both_routes(monkeypatch):
    """A self-hoster reading this has two ways out, and the string has to
    name the one they'd prefer as well as the one we run."""
    _no_local_diffusion(monkeypatch)
    reason = visual_engine.unavailable_reason(VisualMode.FAST_HYBRID, Settings())
    assert reason is not None
    assert "torch" in reason and "diffusers" in reason
    assert "REPLICATE_API_TOKEN" in reason


def test_a_gpu_box_ignores_a_provider_setting_it_cannot_honour(monkeypatch):
    """visual_provider is a preference, not a requirement: an install with
    torch and no token must not be talked out of the GPU it has."""
    monkeypatch.setattr(visual_engine.importlib.util, "find_spec", lambda name: object())
    settings = Settings(provider="replicate", replicate=None)
    assert visual_engine.image_backend(settings) is visual_engine.ImageBackend.LOCAL


def test_scene_concurrency_follows_the_implementation_not_the_mode(monkeypatch):
    """A shared accelerator wants one at a time; a network API wants
    several. Same mode, opposite answers — which is the whole reason this
    stopped being a mode check in render_manager."""
    _no_local_diffusion(monkeypatch)
    hosted = Settings(replicate="r8_test", provider="replicate")
    assert visual_engine.scene_concurrency(VisualMode.FAST_HYBRID, hosted) > 1

    monkeypatch.setattr(visual_engine.importlib.util, "find_spec", lambda name: object())
    local = Settings()
    assert visual_engine.scene_concurrency(VisualMode.FAST_HYBRID, local) == 1
    assert visual_engine.scene_concurrency(VisualMode.AI_VIDEO, local) == 1
    assert visual_engine.scene_concurrency(VisualMode.STOCK_MEDIA, local) > 1


# --- the API refuses to sell what it can't make -------------------------


async def test_creating_a_project_in_an_unavailable_mode_is_refused(monkeypatch):
    """Before the charge, not after the render."""
    import httpx
    from fastapi import FastAPI

    from app.api.routes import projects as projects_route

    monkeypatch.setattr(
        visual_engine.importlib.util,
        "find_spec",
        lambda name: None if name in ("torch", "diffusers") else object(),
    )
    # fast_hybrid has two implementations, so an unavailable install is one
    # with neither. Patched on the real settings object rather than assumed:
    # this route reads get_settings(), which loads the developer's own .env,
    # and the test passed only until someone put a token in theirs.
    _no_hosted_images(monkeypatch)

    app = FastAPI()
    app.include_router(projects_route.router)
    app.state.db_pool = None

    class Queue:
        submitted: list = []

        async def submit(self, project):
            self.submitted.append(project)

    queue = Queue()
    app.state.render_queue = queue

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/projects", json={"topic": "roman aqueducts", "visual_mode": "fast_hybrid"}
        )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "visual_mode_unavailable"
    # The caller is told what it can have instead, so the UI can recover
    # rather than just reporting a failure.
    assert detail["available"] == ["stock_media"]
    assert queue.submitted == [], "nothing may be queued for a mode we can't render"


async def test_an_available_mode_still_goes_through(monkeypatch):
    """The refusal must not be a blanket one — this is the same request in
    a mode the install can serve."""
    import httpx
    from fastapi import FastAPI

    from app.api.routes import projects as projects_route

    app = FastAPI()
    app.include_router(projects_route.router)
    app.state.db_pool = None

    class Queue:
        def __init__(self):
            self.submitted = []

        async def submit(self, project):
            self.submitted.append(project)

    queue = Queue()
    app.state.render_queue = queue

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/projects", json={"topic": "roman aqueducts", "visual_mode": "stock_media"}
        )

    assert response.status_code == 201
    assert len(queue.submitted) == 1


# --- and if it downgrades anyway, it is re-priced -----------------------


def test_a_wholesale_downgrade_is_worth_the_difference():
    """What the pipeline pays back: the gap between what was bought and
    what the scenes actually came out as."""
    from app.schemas.project import ProjectConfig
    from app.services import credits

    asked = ProjectConfig(topic="t", visual_mode=VisualMode.FAST_HYBRID)
    delivered = asked.model_copy(update={"visual_mode": VisualMode.STOCK_MEDIA})

    assert credits.cost_for(asked) - credits.cost_for(delivered) == 2


def _scene(index: int, mode: VisualMode, *, outro: bool = False):
    from app.schemas.project import Scene, SceneAudio, SceneVisual

    return Scene(
        index=index,
        duration_s=4,
        is_outro=outro,
        visual=SceneVisual(prompt="p", mode=mode),
        audio=SceneAudio(voiceover_line="line"),
    )


async def _corrections_for(scenes, requested=VisualMode.FAST_HYBRID) -> list[int]:
    """Run the pipeline's re-pricing step and report what it paid out."""
    from app.schemas.project import ProjectConfig
    from app.services import render_manager

    paid: list[int] = []

    class Pool:
        pass

    async def fake_correct(pool, project_id, amount, *, note=None):
        paid.append(amount)
        return amount

    original_pool = render_manager.db.optional_pool
    original_correct = render_manager.credits.correct_charge
    render_manager.db.optional_pool = lambda: Pool()
    render_manager.credits.correct_charge = fake_correct
    try:
        await render_manager._refund_mode_downgrade(
            "p1", ProjectConfig(topic="t", visual_mode=requested), scenes
        )
    finally:
        render_manager.db.optional_pool = original_pool
        render_manager.credits.correct_charge = original_correct
    return paid


async def test_every_scene_falling_back_re_prices_the_render():
    scenes = [_scene(i, VisualMode.STOCK_MEDIA) for i in range(3)]
    assert await _corrections_for(scenes) == [2]


async def test_one_scene_in_six_falling_back_does_not():
    """The fallback doing its job on a video that is otherwise what was
    ordered. The share is real but rounds to nothing, which is the same
    outcome the old wholesale-only rule gave — deliberately, so the cheap
    end of the scale did not change."""
    scenes = [_scene(0, VisualMode.STOCK_MEDIA)] + [
        _scene(i, VisualMode.FAST_HYBRID) for i in range(1, 6)
    ]
    assert await _corrections_for(scenes) == []


async def test_half_the_scenes_falling_back_pays_back_a_share():
    """Why the rule changed. Local diffusion failed all-or-nothing, so
    wholesale-only was the whole story; generating over an API fails one
    scene at a time, and a video with half its footage downgraded was
    being billed in full and saying nothing about it."""
    scenes = [_scene(i, VisualMode.STOCK_MEDIA) for i in range(3)] + [
        _scene(i, VisualMode.FAST_HYBRID) for i in range(3, 6)
    ]
    assert await _corrections_for(scenes) == [1]


async def test_an_outro_card_is_not_mistaken_for_a_downgrade():
    """Outro cards are drawn, not generated, so their mode is whatever the
    schema defaulted to — counting them would make every render with an
    outro look either downgraded or not, at random."""
    scenes = [
        _scene(0, VisualMode.FAST_HYBRID),
        _scene(1, VisualMode.FAST_HYBRID),
        _scene(2, VisualMode.STOCK_MEDIA, outro=True),
    ]
    assert await _corrections_for(scenes) == []


async def test_a_stock_render_is_never_re_priced():
    """It is already the cheapest thing on the menu; there is nothing to
    give back, and cost_for would compute a zero difference anyway."""
    scenes = [_scene(i, VisualMode.STOCK_MEDIA) for i in range(3)]
    assert await _corrections_for(scenes, requested=VisualMode.STOCK_MEDIA) == []
