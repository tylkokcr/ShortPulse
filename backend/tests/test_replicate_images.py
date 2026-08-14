"""fast_hybrid generated over Replicate rather than on this machine.

The failure this guards is the same one the availability gate exists for,
one layer down: every way a hosted prediction can go wrong ends in a
finished video that looks exactly like the one that was paid for. A
rejected prompt, an expired model version, an unpaid account — all of them
come back through generate_scene_visual's fallback as stock footage, and
the only trace is a line in the ledger.

So these pin what reaches the API, what happens to the money when it
doesn't come back, and that none of it needs torch — the container this
runs in has no diffusion stack at all.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.engines import visual_engine
from app.schemas.project import Scene, SceneAudio, SceneVisual, VisualMode
from app.services import art_styles

PREDICTION_ID = "pred123"
IMAGE_URL = "https://replicate.delivery/pbxt/abc/out-0.png"
API = "https://api.replicate.com/v1"


def _prediction(status: str = "succeeded", **overrides) -> dict:
    """A prediction with the nesting and key names of a real one — the
    point is to fail if the shape assumptions are wrong."""
    body = {
        "id": PREDICTION_ID,
        "status": status,
        "output": [IMAGE_URL] if status == "succeeded" else None,
        "error": None,
        "metrics": {"predict_time": 7.5} if status == "succeeded" else {},
        "urls": {
            "get": f"{API}/predictions/{PREDICTION_ID}",
            "cancel": f"{API}/predictions/{PREDICTION_ID}/cancel",
        },
    }
    body.update(overrides)
    return body


class FakeReplicate:
    """One account's worth of Replicate, over a MockTransport.

    `states` is what successive reads of the prediction return, so a test
    describes a cold start as ["starting", "processing", "succeeded"] and
    the polling loop is exercised for real.
    """

    def __init__(self, states=("succeeded",), create_status=201, retry_then=None):
        self.states = list(states)
        self.create_status = create_status
        self.retry_then = retry_then  # status code to return once, then succeed
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path

        if request.url.host == "replicate.delivery":
            return httpx.Response(200, content=b"\x89PNG fake image bytes")

        if path.endswith("/cancel"):
            return httpx.Response(200, content=json.dumps(_prediction("canceled")))

        if request.method == "POST" and path == "/v1/predictions":
            if self.retry_then is not None:
                status, self.retry_then = self.retry_then, None
                return httpx.Response(status, content=json.dumps({"detail": "slow down"}))
            if self.create_status >= 400:
                return httpx.Response(self.create_status, content=json.dumps({"detail": "no"}))
            return httpx.Response(
                self.create_status, content=json.dumps(_prediction(self.states[0]))
            )

        # A poll. Advance to the next state, holding on the last one.
        if len(self.states) > 1:
            self.states.pop(0)
        return httpx.Response(200, content=json.dumps(_prediction(self.states[0])))

    @property
    def created(self) -> dict:
        """The input the API was actually asked to run."""
        for request in self.requests:
            if request.method == "POST" and request.url.path == "/v1/predictions":
                return json.loads(request.content)
        raise AssertionError("no prediction was created")

    @property
    def cancelled(self) -> bool:
        return any(r.url.path.endswith("/cancel") for r in self.requests)


class Settings:
    def __init__(self, *, guidance=7.0, steps=25, timeout=120.0, token="r8_test"):
        self.replicate_api_token = token
        self.replicate_image_model = "owner/model:abc123"
        self.replicate_timeout_s = timeout
        self.sdxl_num_inference_steps = steps
        self.sdxl_guidance_scale = guidance
        self.visual_provider = "replicate"
        self.pexels_api_key = "key"
        self.pixabay_api_key = None


@pytest.fixture
def scene() -> Scene:
    return Scene(
        index=3,
        duration_s=4,
        visual=SceneVisual(prompt="a lone hiker on a ridge"),
        audio=SceneAudio(voiceover_line="the climb begins"),
    )


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    """Polling and backoff are real code paths; their durations are not."""
    monkeypatch.setattr(visual_engine, "_REPLICATE_POLL_INTERVAL_S", 0)
    monkeypatch.setattr(visual_engine, "_REPLICATE_RETRY_BACKOFF_S", (0, 0))


def _serve(monkeypatch, fake: FakeReplicate) -> FakeReplicate:
    """Point visual_engine's httpx.AsyncClient() at the fake. The real
    class is captured first, or the replacement would construct itself."""
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(fake))
    )
    return fake


# --- what reaches the API -----------------------------------------------


async def test_the_art_style_leads_the_prompt_and_brings_its_negative(
    monkeypatch, scene, tmp_path
):
    """The reason this provider was chosen over a cheaper one: the six
    styles carry templates and negative prompts tuned for this checkpoint,
    and a backend that dropped either would quietly stop matching the
    samples the landing page presents as real renders."""
    fake = _serve(monkeypatch, FakeReplicate())
    style = art_styles.by_id("anime")

    await visual_engine._generate_replicate_image(scene, tmp_path, Settings(), style)

    sent = fake.created["input"]
    assert sent["prompt"] == style.build_prompt("a lone hiker on a ridge")
    assert sent["prompt"].startswith("anime"), "the style has to lead, not trail"
    assert sent["negative_prompt"] == style.negative_prompt
    assert fake.created["version"] == "owner/model:abc123"


async def test_a_scene_negative_prompt_wins_over_the_style_one(monkeypatch, scene, tmp_path):
    fake = _serve(monkeypatch, FakeReplicate())
    scene.visual.negative_prompt = "no birds"

    await visual_engine._generate_replicate_image(scene, tmp_path, Settings())

    assert fake.created["input"]["negative_prompt"] == "no birds"


async def test_steps_and_guidance_come_from_the_same_settings_as_the_local_path(
    monkeypatch, scene, tmp_path
):
    fake = _serve(monkeypatch, FakeReplicate())

    await visual_engine._generate_replicate_image(
        scene, tmp_path, Settings(steps=12, guidance=5.5)
    )

    assert fake.created["input"]["num_inference_steps"] == 12
    assert fake.created["input"]["guidance_scale"] == 5.5


async def test_turbo_guidance_is_clamped_rather_than_rejected(monkeypatch, scene, tmp_path):
    """0.0 is the documented way to run a turbo checkpoint locally, and the
    hosted cog 422s below 1. A .env written for the local path must not
    fail every scene here."""
    fake = _serve(monkeypatch, FakeReplicate())

    await visual_engine._generate_replicate_image(scene, tmp_path, Settings(guidance=0.0))

    assert fake.created["input"]["guidance_scale"] >= 1


async def test_the_image_lands_where_the_renderer_looks(monkeypatch, scene, tmp_path):
    """render_engine dispatches on the file extension, not the mode, so
    the hosted path has to produce the same filename the local one does or
    the Ken Burns branch never runs."""
    _serve(monkeypatch, FakeReplicate())

    path = await visual_engine._generate_replicate_image(scene, tmp_path, Settings())

    from app.engines import render_engine

    assert path == tmp_path / "scene_03.png"
    assert path.read_bytes(), "wrote an empty file"
    assert path.suffix in render_engine._IMAGE_EXTENSIONS


async def test_what_the_provider_will_bill_for_is_recorded(monkeypatch, scene, tmp_path):
    _serve(monkeypatch, FakeReplicate())

    await visual_engine._generate_replicate_image(scene, tmp_path, Settings())

    assert scene.visual.predict_time_s == 7.5


# --- the prediction lifecycle -------------------------------------------


async def test_a_prediction_that_is_not_done_is_polled_until_it_is(
    monkeypatch, scene, tmp_path
):
    fake = _serve(monkeypatch, FakeReplicate(states=["starting", "processing", "succeeded"]))

    path = await visual_engine._generate_replicate_image(scene, tmp_path, Settings())

    polls = [r for r in fake.requests if r.method == "GET" and "/v1/predictions/" in str(r.url)]
    assert polls, "never polled"
    assert str(polls[0].url) == f"{API}/predictions/{PREDICTION_ID}", "poll URL must come from urls.get"
    assert path.exists()


async def test_a_poll_url_outside_the_api_host_is_refused(monkeypatch, scene, tmp_path):
    """An address read out of a response body that this server then
    fetches. Same shape as the llm.base_url hole, whoever sent it."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = _prediction("processing")
            body["urls"]["get"] = "http://169.254.169.254/latest/meta-data/"
            return httpx.Response(201, content=json.dumps(body))
        raise AssertionError("must not fetch a URL off the API host")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(RuntimeError, match="unusable poll URL"):
        await visual_engine._generate_replicate_image(scene, tmp_path, Settings())


async def test_an_abandoned_prediction_is_cancelled(monkeypatch, scene, tmp_path):
    """It bills for the seconds it burns whether or not anyone is still
    waiting for the result. This is the only place the code can stop
    paying."""
    fake = _serve(monkeypatch, FakeReplicate(states=["processing"]))

    with pytest.raises(RuntimeError, match="cancelled"):
        await visual_engine._generate_replicate_image(
            scene, tmp_path, Settings(timeout=0.0)
        )

    assert fake.cancelled


async def test_a_rate_limited_prediction_is_retried(monkeypatch, scene, tmp_path):
    """Four scenes generate at once, so 429 is the ordinary case rather
    than the exceptional one."""
    fake = _serve(monkeypatch, FakeReplicate(retry_then=429))

    path = await visual_engine._generate_replicate_image(scene, tmp_path, Settings())

    creates = [r for r in fake.requests if r.method == "POST" and r.url.path == "/v1/predictions"]
    assert len(creates) == 2
    assert path.exists()


async def test_a_rejected_prompt_is_named_rather_than_indexed_into(
    monkeypatch, scene, tmp_path
):
    """The safety checker returns a null element, not an error."""
    _serve(monkeypatch, FakeReplicate())
    monkeypatch.setattr(
        visual_engine,
        "_replicate_predict",
        lambda payload, settings: _async(_prediction("succeeded", output=[None])),
    )

    with pytest.raises(RuntimeError, match="produced no image"):
        await visual_engine._generate_replicate_image(scene, tmp_path, Settings())


async def _async(value):
    return value


# --- the money ----------------------------------------------------------


async def test_a_failed_prediction_degrades_to_stock_media(monkeypatch, scene, tmp_path):
    """The money path. The render survives, and what actually produced the
    asset is recorded so the ledger can re-price it."""
    _serve(monkeypatch, FakeReplicate(create_status=402))

    async def fake_stock(scene_, output_dir, settings_, target_height=1920):
        path = output_dir / f"scene_{scene_.index:02d}_stock.mp4"
        path.write_bytes(b"fake mp4")
        return path

    monkeypatch.setattr(visual_engine, "_fetch_stock_media", fake_stock)

    await visual_engine.generate_scene_visual(
        scene, VisualMode.FAST_HYBRID, tmp_path, Settings()
    )

    assert scene.visual.mode == VisualMode.STOCK_MEDIA, "the downgrade has to be recorded"
    assert scene.visual.asset_path.endswith("_stock.mp4")


# --- the deployment constraint ------------------------------------------


async def test_this_path_never_needs_torch(monkeypatch, scene, tmp_path):
    """The image ships without the diffusion stack on purpose. Pinned as a
    test because an import added at the top of a helper would only fail in
    production, and only for the mode that earns money."""
    _serve(monkeypatch, FakeReplicate())
    monkeypatch.setattr(
        visual_engine.importlib.util,
        "find_spec",
        lambda name: None if name in ("torch", "diffusers") else object(),
    )

    path = await visual_engine._generate_replicate_image(scene, tmp_path, Settings())

    assert path.exists()
