"""Visual generation dispatch across the three supported modes.

  Mode A (ai_video):    Local text-to-video diffusion (LTX-Video / CogVideoX).
                         Slowest, most "alive" looking, needs a real GPU.
  Mode B (fast_hybrid):  One SDXL still per scene, animated with an FFmpeg
                         Ken Burns pan/zoom in the render engine. Two
                         implementations of the same mode — diffusers on
                         this machine, or the same checkpoint on
                         Replicate's hosted inference (see image_backend).
                         Recommended default either way.
  Mode C (stock_media):  Pulls a matching stock clip from Pexels/Pixabay's
                         free APIs. Zero GPU required, good fallback when
                         no local diffusion hardware is available.

Mode B is deliberately one mode and not two. A VisualMode is a price, a
promise and a tile in the picker; which machine ran the checkpoint is
neither, and splitting it would fork the tariff, the availability list, the
refund comparison and three pieces of marketing copy to express something
nobody is choosing between. What actually produced an asset is recorded in
the project's timings.json instead.

Each generator writes its asset into the project's `visuals/` directory and
returns the path, which is stored on `scene.visual.asset_path`.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import httpx

from app.schemas.project import Scene, StockAttribution, VisualMode
from app.services import art_styles
from app.services.art_styles import ArtStyle

logger = logging.getLogger(__name__)

_sdxl_pipeline_cache: dict[str, object] = {}
_ltx_pipeline_cache: dict[str, object] = {}

# Applied whenever a scene doesn't supply its own negative_prompt. Local
# diffusion models (SDXL-Turbo/LTX-Video distilled variants especially,
# since they're optimized for speed over a handful of steps) are prone to
# anatomical hallucinations — extra limbs/tentacles/fingers — without this.
DEFAULT_NEGATIVE_PROMPT = (
    "deformed, distorted, disfigured, extra limbs, extra hands, extra fingers, "
    "extra tentacles, bad anatomy, mutated, malformed, low quality, blurry, "
    "text overlay, watermark, signature, cgi, 3d render, illustration, "
    "overly smooth, plastic, oversaturated"
)

# The photoreal wording that used to live here is now the "photoreal"
# entry in app.services.art_styles, alongside the other looks — see
# ArtStyle.prompt_template, and the note there about why the style has to
# lead the prompt rather than trail it.

# SDXL is trained around ~1MP; these are the standard buckets for each
# orientation. Generating vertical and letting the renderer crop to
# landscape would throw away most of the frame, so the shape asked for
# here follows the project's aspect ratio.
SDXL_SIZE_BY_ORIENTATION: dict[str, tuple[int, int]] = {
    "vertical": (832, 1472),
    "square": (1024, 1024),
    "landscape": (1472, 832),
}


def sdxl_size_for(width: int, height: int) -> tuple[int, int]:
    """Generation size matching the render target's orientation."""
    if width > height:
        return SDXL_SIZE_BY_ORIENTATION["landscape"]
    if width == height:
        return SDXL_SIZE_BY_ORIENTATION["square"]
    return SDXL_SIZE_BY_ORIENTATION["vertical"]


# Hosted inference is a different machine with different comfortable
# resolutions, so Mode B's two implementations do not share a bucket table.
# The shape is what matters — the render engine crops to the project's
# aspect ratio and Ken Burns oversizes before panning — so these keep the
# orientation and give up some pixels. 768x1344 is the stable portrait size
# for SDXL checkpoints served this way.
REPLICATE_SIZE_BY_ORIENTATION: dict[str, tuple[int, int]] = {
    "vertical": (768, 1344),
    "square": (1024, 1024),
    "landscape": (1344, 768),
}


def replicate_size_for(width: int, height: int) -> tuple[int, int]:
    """Hosted generation size matching the render target's orientation."""
    if width > height:
        return REPLICATE_SIZE_BY_ORIENTATION["landscape"]
    if width == height:
        return REPLICATE_SIZE_BY_ORIENTATION["square"]
    return REPLICATE_SIZE_BY_ORIENTATION["vertical"]


class ImageBackend(StrEnum):
    """Which implementation runs fast_hybrid.

    Not in schemas/project.py next to LLMProvider: that one is there
    because LLMConfig is a wire schema a client sends. This never crosses
    the wire — it is derived from settings and the packages present — so it
    lives beside the dispatch that reads it.
    """

    LOCAL = "local"
    REPLICATE = "replicate"


def _has_local_diffusion() -> bool:
    # find_spec rather than an import: loading torch costs seconds and
    # hundreds of MB, and this runs on ordinary requests.
    return all(importlib.util.find_spec(n) is not None for n in ("torch", "diffusers"))


def image_backend(settings) -> ImageBackend | None:
    """Which implementation would run fast_hybrid here, or None if neither can.

    settings.visual_provider is honoured when that backend is usable and
    otherwise ignored, so neither shape of install has to configure
    anything: the container has a token and no torch, a GPU box has torch
    and no token, and only a machine with both is actually expressing a
    preference.

    One function, so the availability gate, the dispatch and the
    concurrency limit can never disagree about what this install can do.
    """
    usable = {
        ImageBackend.LOCAL: _has_local_diffusion(),
        ImageBackend.REPLICATE: bool(getattr(settings, "replicate_api_token", None)),
    }
    preferred = getattr(settings, "visual_provider", ImageBackend.LOCAL)
    for backend in (preferred, ImageBackend.LOCAL, ImageBackend.REPLICATE):
        if backend in usable and usable[backend]:
            return ImageBackend(backend)
    return None


# Network work overlaps; a shared accelerator does not.
#
# Two, not four. Four was picked from the stock-media path, where the work
# is a search and a download; against Replicate it made every request in a
# six-scene batch hit a 429 and one of them exhaust its retries — a scene
# silently downgraded to stock footage on a render that was paid for as AI
# stills. There is little to win anyway: an image bills ~3.5s of predict
# time and the rest of the wall clock is the model booting, which happens
# once and is shared by everything behind it.
_REMOTE_SCENE_CONCURRENCY = 2


def scene_concurrency(mode: VisualMode, settings) -> int:
    """How many scenes may be generated at once.

    This follows from what the work *is*, not from which mode was asked
    for — which is why it stopped being a mode check in render_manager the
    moment one mode grew two implementations with opposite answers. Stock
    media and hosted generation are network-bound and were two thirds of a
    render's wall clock when run one at a time; local diffusion shares one
    GPU, where concurrency buys nothing and costs memory.
    """
    if mode == VisualMode.STOCK_MEDIA:
        return _REMOTE_SCENE_CONCURRENCY
    if mode == VisualMode.FAST_HYBRID and image_backend(settings) is ImageBackend.REPLICATE:
        return _REMOTE_SCENE_CONCURRENCY
    return 1


def is_model_fully_cached(model_id: str) -> bool:
    """Best-effort check for whether a HF model is already fully downloaded
    on disk (not just its small metadata files) — used to warn the caller
    before a large first-time download (e.g. LTX-Video, tens of GB) kicks
    off during what looks like a normal render.
    """
    import os

    from huggingface_hub import try_to_load_from_cache
    from huggingface_hub.constants import HF_HUB_CACHE

    # model_index.json downloads in seconds even when the real weight
    # files are still mid-download, so its presence alone isn't proof the
    # model is ready — also check for leftover partial-download blobs.
    if try_to_load_from_cache(model_id, filename="model_index.json") is None:
        return False

    repo_folder = "models--" + model_id.replace("/", "--")
    blobs_dir = os.path.join(HF_HUB_CACHE, repo_folder, "blobs")
    if not os.path.isdir(blobs_dir):
        return False
    return not any(name.endswith(".incomplete") for name in os.listdir(blobs_dir))


def unavailable_reason(mode: VisualMode, settings) -> str | None:
    """Why this install cannot run `mode`, or None if it can.

    Every mode has a silent failure waiting behind it, because
    generate_scene_visual falls back to stock footage rather than losing
    the render. That is right for a self-hosted install — a missing GPU
    shouldn't mean no video — but on a deployment that charges by mode it
    meant taking three credits for a one-credit result and saying nothing.

    So availability is answered before anything is charged: the UI hides
    what this install can't do, and the API refuses to sell it.
    """
    # The two generated modes stopped sharing a branch when they stopped
    # sharing a requirement: fast_hybrid has a hosted implementation,
    # ai_video does not.
    if mode == VisualMode.FAST_HYBRID:
        if image_backend(settings) is not None:
            return None
        return (
            "needs torch and diffusers to generate on this machine, or "
            "REPLICATE_API_TOKEN to generate over Replicate's API — this install has neither"
        )

    if mode == VisualMode.AI_VIDEO:
        if _has_local_diffusion():
            return None
        # Hosted text-to-video costs more per render than this mode is
        # priced at, so there is no API route behind this one and the
        # reason has to make sense to a paying customer reading it as a
        # tooltip, not just to an operator reading a dependency list.
        return (
            "runs text-to-video on the machine serving the render, so it needs torch, "
            "diffusers and a GPU — it is available when you self-host, not on this service"
        )

    if mode == VisualMode.STOCK_MEDIA:
        if not (settings.pexels_api_key or settings.pixabay_api_key):
            return "needs a Pexels or Pixabay API key, and neither is configured"
        return None

    return f"unknown mode {mode}"


def available_modes(settings) -> list[VisualMode]:
    return [m for m in VisualMode if unavailable_reason(m, settings) is None]


async def generate_scene_visual(
    scene: Scene,
    mode: VisualMode,
    output_dir: Path,
    settings,
    art_style: ArtStyle | None = None,
    size: tuple[int, int] | None = None,
    render_size: tuple[int, int] | None = None,
) -> Scene:
    """Populate scene.visual.asset_path using the requested mode, with a
    stock-media fallback if a local generation mode fails (e.g. no GPU).

    `art_style` and `size` only reach the locally generated modes: stock
    footage is whatever was filmed, at whatever the clip's own dimensions
    are, and the render step crops it to fit.
    """
    style = art_style or art_styles.DEFAULT_ART_STYLE
    render_height = (render_size or (1080, 1920))[1]
    try:
        if mode == VisualMode.AI_VIDEO:
            path = await _generate_ai_video(scene, output_dir, settings, style)
        elif mode == VisualMode.FAST_HYBRID:
            if image_backend(settings) is ImageBackend.REPLICATE:
                path = await _generate_replicate_image(scene, output_dir, settings, style, size)
            else:
                path = await _generate_fast_hybrid_image(scene, output_dir, settings, style, size)
        elif mode == VisualMode.STOCK_MEDIA:
            path = await _fetch_stock_media(scene, output_dir, settings, render_height)
        else:
            raise ValueError(f"Unsupported visual mode: {mode}")
        produced_by = mode
    except Exception:
        logger.exception(
            "Visual generation failed for scene %s in mode %s; falling back to stock media",
            scene.index,
            mode,
        )
        path = await _fetch_stock_media(scene, output_dir, settings, render_height)
        produced_by = VisualMode.STOCK_MEDIA

    scene.visual.asset_path = str(path)
    # What actually made this asset, which is not always what was asked
    # for. The caller charges by mode, so it has to be able to tell.
    scene.visual.mode = produced_by
    return scene


# --------------------------------------------------------------------------
# Mode A: local AI video generation
# --------------------------------------------------------------------------


def _get_ltx_pipeline(model_id: str, device: str):
    if model_id not in _ltx_pipeline_cache:
        import torch
        from diffusers import LTXPipeline

        logger.info("Loading LTX-Video pipeline %s on %s", model_id, device)
        # This is a 13B-parameter model — fp32 (~52GB of weights alone) will
        # thrash swap on most machines. fp16 works fine on both cuda and mps
        # and halves that footprint; only plain cpu needs fp32.
        pipeline = LTXPipeline.from_pretrained(
            model_id, torch_dtype=torch.float16 if device in ("cuda", "mps") else torch.float32
        )
        pipeline.to(device)
        # NOTE: enable_model_cpu_offload() and vae.enable_tiling()/
        # enable_slicing() were all tried here to fit this 13B-parameter
        # model's ~28GB of fp16 weights into 32GB of unified memory. Plain
        # fp16 alone still thrashes swap; adding cpu_offload avoided that
        # but then hung indefinitely during VAE decode (CPU time stopped
        # advancing, no crash) both with and without tiling — a deeper
        # accelerate/MPS interaction bug beyond what's worth chasing here.
        # Shrinking the actual generation size (see _generate_ai_video) is
        # the more reliable lever on memory-constrained hardware.
        _ltx_pipeline_cache[model_id] = pipeline
    return _ltx_pipeline_cache[model_id]


async def _generate_ai_video(
    scene: Scene, output_dir: Path, settings, style: ArtStyle | None = None
) -> Path:
    import asyncio

    output_path = output_dir / f"scene_{scene.index:02d}.mp4"
    style = style or art_styles.DEFAULT_ART_STYLE

    def _run() -> Path:
        from diffusers.utils import export_to_video

        pipeline = _get_ltx_pipeline(settings.ltx_video_model_id, settings.diffusion_device)
        result = pipeline(
            prompt=style.build_prompt(scene.visual.prompt),
            negative_prompt=scene.visual.negative_prompt or style.negative_prompt,
            # LTXPipeline requires both dimensions divisible by 32. Kept
            # deliberately small (1/4 the pixel area of the previous
            # 768x1376) — this 13B model has no reliable low-memory path on
            # unified-memory Apple Silicon (see _get_ltx_pipeline), so this
            # is the main remaining lever to keep it inside 32GB of RAM.
            # render_engine upscales to the final 1080x1920 output anyway.
            width=384,
            height=672,
            num_frames=int(scene.duration_s * 24),
            num_inference_steps=30,
        )
        export_to_video(result.frames[0], str(output_path), fps=24)
        return output_path

    return await asyncio.to_thread(_run)


# --------------------------------------------------------------------------
# Mode B: fast still-image generation (recommended default)
# --------------------------------------------------------------------------


def _get_sdxl_pipeline(model_id: str, device: str, variant: str | None = None):
    if model_id not in _sdxl_pipeline_cache:
        import torch
        from diffusers import AutoPipelineForText2Image

        logger.info("Loading diffusion pipeline %s on %s", model_id, device)
        kwargs = {"torch_dtype": torch.float16 if device in ("cuda", "mps") else torch.float32}
        if variant:
            # Full SDXL fine-tunes ship both fp32 and fp16 weight sets;
            # asking for the fp16 variant halves the download and the
            # resident footprint.
            kwargs["variant"] = variant
            kwargs["use_safetensors"] = True
        pipeline = AutoPipelineForText2Image.from_pretrained(model_id, **kwargs)
        pipeline.to(device)
        _sdxl_pipeline_cache[model_id] = pipeline
    return _sdxl_pipeline_cache[model_id]


async def _generate_fast_hybrid_image(
    scene: Scene,
    output_dir: Path,
    settings,
    style: ArtStyle | None = None,
    size: tuple[int, int] | None = None,
) -> Path:
    import asyncio

    output_path = output_dir / f"scene_{scene.index:02d}.png"
    style = style or art_styles.DEFAULT_ART_STYLE
    width, height = size or SDXL_SIZE_BY_ORIENTATION["vertical"]

    def _run() -> Path:
        pipeline = _get_sdxl_pipeline(
            settings.sdxl_model_id, settings.diffusion_device, settings.sdxl_model_variant
        )
        image = pipeline(
            prompt=style.build_prompt(scene.visual.prompt),
            # NOTE: with the default SDXL-Turbo settings (4 steps,
            # guidance_scale=0.0) diffusers disables classifier-free
            # guidance entirely, so negative_prompt has no effect —
            # confirmed by reading diffusers' do_classifier_free_guidance
            # property and empirically (hand/octopus test renders were
            # equally malformed at guidance 1.8 / 8 steps, for 2.5x the
            # time). It does take effect when these settings are pointed
            # at a full SDXL fine-tune (see Settings.sdxl_* in core/config).
            negative_prompt=scene.visual.negative_prompt or style.negative_prompt,
            width=width,
            height=height,
            num_inference_steps=settings.sdxl_num_inference_steps,
            guidance_scale=settings.sdxl_guidance_scale,
        ).images[0]
        image.save(output_path)
        return output_path

    return await asyncio.to_thread(_run)


# --------------------------------------------------------------------------
# Mode B, hosted: the same checkpoint on Replicate
# --------------------------------------------------------------------------

_REPLICATE_API = "https://api.replicate.com/v1"
_REPLICATE_POLL_INTERVAL_S = 1.5
# Worth another attempt: the account is over its concurrency allowance, or
# a gateway blinked. Anything else — a bad token, a deleted model version,
# an input the cog rejects — will fail again identically, and the caller
# degrades that scene to stock media rather than looping.
_REPLICATE_RETRY_STATUSES = frozenset({429, 502, 503, 504})
# Four waits, not two. Replicate's burst limiter answers 429 with
# Retry-After: 10, so a two-attempt budget of 2s and 4s was spent before
# the window it was told to wait for had even opened. The whole chain is
# bounded by replicate_timeout_s regardless, so the tail here costs
# nothing when the limiter is not the problem.
_REPLICATE_RETRY_BACKOFF_S = (2.0, 5.0, 10.0, 20.0)


def _replicate_image_input(scene: Scene, style: ArtStyle, size, settings) -> dict:
    """The cog's inputs, mapped from the same settings the local path reads.

    Deliberately the same precedence as _generate_fast_hybrid_image, so
    SDXL_NUM_INFERENCE_STEPS and SDXL_GUIDANCE_SCALE keep one meaning
    across both implementations of the mode.
    """
    width, height = replicate_size_for(*(size or SDXL_SIZE_BY_ORIENTATION["vertical"]))
    return {
        "prompt": style.build_prompt(scene.visual.prompt),
        "negative_prompt": scene.visual.negative_prompt or style.negative_prompt,
        "width": width,
        "height": height,
        "num_inference_steps": settings.sdxl_num_inference_steps,
        # The hosted cog validates guidance_scale >= 1 and 422s below it,
        # while locally 0.0 is the documented way to run a turbo model with
        # classifier-free guidance off. Clamping keeps a .env written for
        # the local path from failing every scene here — and the negative
        # prompts the art styles carry only do anything above 1 anyway.
        "guidance_scale": max(1.0, float(settings.sdxl_guidance_scale)),
        "num_outputs": 1,
    }


async def _replicate_call(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict,
    json: dict | None = None,
    deadline: float | None = None,
) -> httpx.Response:
    """One request, retried while it is worth retrying and there is time.

    `deadline` is the same monotonic budget the polling loop uses, so a
    scene cannot spend an unbounded stretch being told to come back later:
    a rate limiter answering Retry-After: 10 forever would otherwise hold
    a render open for as long as it kept saying it.
    """
    last_exc: Exception | None = None
    # A backoff per retry, then None for the final attempt that must not
    # sleep and must not swallow.
    for backoff in (*_REPLICATE_RETRY_BACKOFF_S, None):
        try:
            response = await client.request(method, url, headers=headers, json=json)
            if response.status_code in _REPLICATE_RETRY_STATUSES and backoff is not None:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if (retry_after or "").strip().isdigit() else backoff
                if deadline is not None and time.monotonic() + delay >= deadline:
                    logger.warning(
                        "Replicate returned %s with no time left to wait it out",
                        response.status_code,
                    )
                    response.raise_for_status()
                logger.warning(
                    "Replicate returned %s; retrying in %.1fs", response.status_code, delay
                )
                await asyncio.sleep(delay)
                continue
            if response.status_code == 402:
                # Distinct from every other failure: nothing is wrong with
                # the request, the account cannot pay for it. Without this
                # line it reads as a generic outage while every render on
                # the deployment quietly downgrades to stock media.
                logger.error(
                    "Replicate refused the prediction for payment reasons (402) — "
                    "the account has no billing set up or has hit its spend limit"
                )
            response.raise_for_status()
            return response
        except httpx.TransportError as exc:  # connect/read errors, not HTTP status
            last_exc = exc
            if backoff is None:
                raise
            logger.warning("Replicate request failed (%r); retrying in %.1fs", exc, backoff)
            await asyncio.sleep(backoff)
    raise last_exc or RuntimeError("Replicate request exhausted its retries")


async def _replicate_cancel(client: httpx.AsyncClient, prediction: dict, headers: dict) -> None:
    """Stop paying for a prediction nobody is waiting for any more.

    Best effort by design: this runs while another error is already on its
    way up, and failing to cancel must not replace it.
    """
    url = (prediction.get("urls") or {}).get("cancel")
    if not url or not url.startswith(f"{_REPLICATE_API}/"):
        return
    try:
        await client.post(url, headers=headers)
    except Exception:  # noqa: BLE001
        logger.warning("Could not cancel Replicate prediction %s", prediction.get("id"))


async def _replicate_predict(payload: dict, settings) -> dict:
    """Create a prediction and return it once it reaches a terminal state.

    `Prefer: wait` gets the finished prediction back on the original
    request in the common case — an SDXL still is ~5-10s of predict time —
    and polling is the cold-start path, not the normal one.
    """
    headers = {
        "Authorization": f"Bearer {settings.replicate_api_token}",
        "Content-Type": "application/json",
    }
    deadline = time.monotonic() + float(settings.replicate_timeout_s)

    # The socket is legitimately held open by Prefer: wait, so the read
    # timeout has to exceed it while the connect timeout stays short.
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
        prediction = (
            await _replicate_call(
                client,
                "POST",
                f"{_REPLICATE_API}/predictions",
                {**headers, "Prefer": "wait=60"},
                json=payload,
                deadline=deadline,
            )
        ).json()

        while prediction.get("status") in ("starting", "processing"):
            if time.monotonic() >= deadline:
                await _replicate_cancel(client, prediction, headers)
                raise RuntimeError(
                    f"Replicate prediction {prediction.get('id')} still running after "
                    f"{settings.replicate_timeout_s:.0f}s; cancelled"
                )
            await asyncio.sleep(_REPLICATE_POLL_INTERVAL_S)
            poll_url = (prediction.get("urls") or {}).get("get")
            # An address read out of a response body that this server then
            # fetches — the same shape as the llm.base_url hole, even
            # though this response came from a host we chose. Constraining
            # it costs one line (see SECURITY.md, "Server-side requests").
            if not poll_url or not poll_url.startswith(f"{_REPLICATE_API}/"):
                raise RuntimeError(f"Replicate returned an unusable poll URL: {poll_url!r}")
            prediction = (
                await _replicate_call(client, "GET", poll_url, headers, deadline=deadline)
            ).json()

    if prediction.get("status") != "succeeded":
        raise RuntimeError(
            f"Replicate prediction {prediction.get('id')} "
            f"{prediction.get('status')}: {prediction.get('error')}"
        )
    return prediction


def _replicate_output_url(prediction: dict) -> str:
    """The one image URL, from a schema that is a list but not always.

    A safety-checker rejection comes back as a null element rather than an
    error, so an empty or null-filled output is a real outcome to name
    rather than an IndexError to trip over.
    """
    output = prediction.get("output")
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        urls = [u for u in output if isinstance(u, str) and u]
        if urls:
            return urls[0]
    raise RuntimeError(
        f"Replicate prediction {prediction.get('id')} produced no image "
        f"(output was {output!r}); a rejected prompt looks like this"
    )


async def _generate_replicate_image(
    scene: Scene,
    output_dir: Path,
    settings,
    style: ArtStyle | None = None,
    size: tuple[int, int] | None = None,
) -> Path:
    """fast_hybrid over the API. Same signature and same output filename as
    the local generator, which is what keeps the render engine's
    extension-based dispatch and the caller's fallback both unchanged."""
    output_path = output_dir / f"scene_{scene.index:02d}.png"
    style = style or art_styles.DEFAULT_ART_STYLE

    prediction = await _replicate_predict(
        {
            "version": settings.replicate_image_model,
            "input": _replicate_image_input(scene, style, size, settings),
        },
        settings,
    )
    await _download(_replicate_output_url(prediction), output_path)
    # Read back by render_manager for timings.json: part of this stage's
    # cost is now an invoice rather than our own wall clock.
    scene.visual.predict_time_s = (prediction.get("metrics") or {}).get("predict_time")
    return output_path


# --------------------------------------------------------------------------
# Mode C: stock media fallback (Pexels primary, Pixabay secondary)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StockClip:
    """A stock clip plus the credit its licence requires.

    The two travel together deliberately. Pexels' API terms make
    attribution a condition of use, and once the file is downloaded there
    is nothing left to derive the photographer's name from — so a function
    that returned only a URL would make compliance impossible by
    construction.
    """

    url: str
    attribution: StockAttribution


# Words that carry no meaning for a stock-footage search. Kept short and
# obvious on purpose: the goal is to get from a sentence to its nouns, not
# to do linguistics.
_SEARCH_STOPWORDS = frozenset(
    """a an the of or and with in on at to for from by as is are was were be
    being been that this these those it its their his her they we you your
    some several various many much more most showing shows featuring depicting
    depicts scene shot view image video footage clip
    over under against during through between into onto above below behind
    near around while before after out up down off
    """.split()
)

# Stock search is keyword matching; a whole descriptive sentence is not what
# these libraries index against.
_MAX_SEARCH_WORDS = 6


def stock_search_terms(prompt: str) -> str:
    """Condense a scene's visual prompt into a keyword query.

    Two reasons, one of which is not obvious.

    The obvious one: Pexels and Pixabay match on keywords, and handing them
    a fifteen-word sentence buries the two nouns that actually matter.

    The other: Pexels sits behind Cloudflare, and long natural-language
    queries intermittently trip a WAF rule that returns a 403 HTML page
    rather than an API error. It is content-dependent and not reproducible
    from length alone — "...various modules and" succeeds where
    "...various modules and solar" is blocked. That killed whole renders,
    because one blocked scene aborted the pipeline. Short keyword queries
    have not been observed to trigger it.

    Falls back to the original prompt if the filter leaves nothing, which
    is better than searching for an empty string.
    """
    words = [w.strip(".,!?;:()[]\"'").lower() for w in prompt.split()]
    keywords = [w for w in words if w and w not in _SEARCH_STOPWORDS]
    return " ".join(keywords[:_MAX_SEARCH_WORDS]) or prompt[:60]


async def _fetch_stock_media(
    scene: Scene, output_dir: Path, settings, target_height: int = 1920
) -> Path:
    output_path = output_dir / f"scene_{scene.index:02d}_stock.mp4"
    query = stock_search_terms(scene.visual.prompt)

    for search, api_key in (
        (_search_pexels, settings.pexels_api_key),
        (_search_pixabay, settings.pixabay_api_key),
    ):
        if not api_key:
            continue
        # A provider being down, rate-limited or WAF-blocked is a reason to
        # try the next one, not to fail the render. Previously any non-2xx
        # from Pexels raised straight out and lost every scene rendered so
        # far.
        try:
            clip = await search(query, api_key, target_height)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning(
                "Stock provider %s failed for scene %s (%r); trying the next one",
                search.__name__,
                scene.index,
                exc,
            )
            continue
        if clip:
            needed = max(
                (scene.audio.duration_ms or 0) / 1000 + _STOCK_HEAD_MARGIN_S,
                _STOCK_MIN_HEAD_S,
            )
            await _download_head(clip.url, output_path, needed, settings.ffmpeg_binary)
            scene.visual.attribution = clip.attribution
            return output_path

    raise RuntimeError(
        "No stock media provider configured (set PEXELS_API_KEY or PIXABAY_API_KEY) "
        "and no local visual asset could be produced."
    )


def _pick_rendition(files: list[dict], target_height: int) -> dict:
    """The smallest file that still covers the render height.

    Stock libraries serve the same clip at up to 4K, and this used to take
    the largest of them: for a 1080x1920 render that meant fetching a
    2160x3840 master — measured at 33MB and 26s where the 1080 rendition
    was 7MB and 3s — only to have ffmpeg scale it back down. Downloading
    is most of what the visuals stage spends its time on, so this is the
    single biggest lever on how long a stock render takes.

    Portrait renditions are preferred where they exist, since a landscape
    source gets centre-cropped and loses most of its width. If nothing
    reaches the target height, the largest available is the best on offer.
    """
    portrait = [f for f in files if (f.get("height") or 0) >= (f.get("width") or 1)]
    candidates = portrait or files
    tall_enough = [f for f in candidates if (f.get("height") or 0) >= target_height]
    if tall_enough:
        return min(tall_enough, key=lambda f: f.get("height") or 0)
    return max(candidates, key=lambda f: f.get("height") or 0)


async def _search_pexels(query: str, api_key: str, target_height: int = 1920) -> StockClip | None:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": api_key},
            params={"query": query, "orientation": "portrait", "per_page": 1},
        )
        response.raise_for_status()
        data = response.json()
        videos = data.get("videos", [])
        if not videos:
            return None
        video = videos[0]
        chosen = _pick_rendition(video["video_files"], target_height)
        user = video.get("user") or {}
        return StockClip(
            url=chosen["link"],
            attribution=StockAttribution(
                provider="Pexels",
                provider_url="https://www.pexels.com",
                author=user.get("name"),
                author_url=user.get("url"),
                source_url=video.get("url"),
            ),
        )


async def _search_pixabay(
    query: str, api_key: str, target_height: int = 1920
) -> StockClip | None:
    """Pixabay serves a fixed set of named sizes rather than a ladder, and
    `medium` already sits near 1080 — so `target_height` is accepted for a
    uniform signature with the Pexels search and not otherwise used."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            "https://pixabay.com/api/videos/",
            params={"key": api_key, "q": query, "per_page": 3},
        )
        response.raise_for_status()
        data = response.json()
        hits = data.get("hits", [])
        if not hits:
            return None
        hit = hits[0]
        return StockClip(
            url=hit["videos"]["medium"]["url"],
            attribution=StockAttribution(
                provider="Pixabay",
                provider_url="https://pixabay.com",
                author=hit.get("user"),
                author_url=(
                    f"https://pixabay.com/users/{hit['user']}-{hit['user_id']}/"
                    if hit.get("user") and hit.get("user_id")
                    else None
                ),
                source_url=hit.get("pageURL"),
            ),
        )


async def _download(url: str, output_path: Path) -> None:
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(output_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=1 << 16):
                    f.write(chunk)


# A scene is a few seconds long, so pulling a whole stock clip to use the
# start of it is nearly all waste. Measured on one 5-scene render: 238MB
# fetched for 18 seconds of finished video, including a 13s clip that was
# 113MB on its own — these are high-bitrate masters.
#
# A little more than the scene needs, because the render step loops a clip
# that comes up short and a hard cut at exactly the scene length leaves no
# margin for keyframe alignment.
_STOCK_HEAD_MARGIN_S = 2.0
_STOCK_MIN_HEAD_S = 5.0


async def _download_head(
    url: str, output_path: Path, seconds: float, ffmpeg_binary: str = "ffmpeg"
) -> None:
    """Fetch only the first `seconds` of a remote clip.

    ffmpeg reads the URL directly and stops once it has enough, so the
    transfer ends early instead of pulling the whole master. Stream-copied,
    not re-encoded: this is a fetch, and the real encode happens later in
    the render engine.

    Falls back to downloading the file whole if ffmpeg can't read the URL —
    a clip that arrives slowly is better than a render that fails.
    """
    import asyncio

    args = [
        ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error",
        "-i", url,
        "-t", f"{seconds:.2f}",
        "-map", "0:v:0",
        "-c", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 0:
        return

    logger.warning(
        "Trimmed fetch failed for %s (%s); downloading the whole clip",
        url,
        stderr.decode(errors="ignore").strip()[:160],
    )
    await _download(url, output_path)


# --------------------------------------------------------------------------
# Branded outro card (no AI generation — drawn locally with Pillow)
# --------------------------------------------------------------------------

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",  # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
    "C:\\Windows\\Fonts\\arialbd.ttf",  # Windows
]


def _load_bold_font(size: int):
    from PIL import ImageFont

    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def generate_outro_card(
    text: str,
    output_path: Path,
    logo_path: str | None = None,
    background_color: str = "#0a0a0a",
    accent_color: str = "#ff5c1a",
    width: int = 1080,
    height: int = 1920,
) -> Path:
    """Render a simple branded closing card (solid background, centered
    wrapped text, accent-colored divider, optional logo) instead of leaving
    the final scene's visual up to whatever the LLM imagined for the
    call-to-action. Runs synchronously — it's Pillow drawing, not a model
    inference call, so it's fast enough to call directly from async code.
    """
    from PIL import Image, ImageDraw

    bg = _hex_to_rgb(background_color)
    accent = _hex_to_rgb(accent_color)

    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)

    center_y = height // 2
    logo_bottom = center_y - 120

    if logo_path and Path(logo_path).exists():
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((width // 3, width // 3))
        logo_x = (width - logo.width) // 2
        logo_y = logo_bottom - logo.height
        image.paste(logo, (logo_x, logo_y), logo)

    font = _load_bold_font(72)
    max_text_width = int(width * 0.8)

    words = text.split()
    lines: list[str] = []
    current_line = ""
    for word in words:
        candidate = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] > max_text_width and current_line:
            lines.append(current_line)
            current_line = word
        else:
            current_line = candidate
    if current_line:
        lines.append(current_line)

    line_height = font.size + 20
    text_block_height = len(lines) * line_height
    text_y = center_y - text_block_height // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        draw.text(((width - line_width) // 2, text_y), line, font=font, fill=(255, 255, 255))
        text_y += line_height

    divider_y = text_y + 30
    divider_width = 120
    draw.rectangle(
        [(width - divider_width) // 2, divider_y, (width + divider_width) // 2, divider_y + 6],
        fill=accent,
    )

    image.save(output_path)
    return output_path
