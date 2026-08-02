"""Visual generation dispatch across the three supported modes.

  Mode A (ai_video):    Local text-to-video diffusion (LTX-Video / CogVideoX).
                         Slowest, most "alive" looking, needs a real GPU.
  Mode B (fast_hybrid):  Flux.1-Schnell / SDXL-Turbo still image per scene,
                         animated with an FFmpeg Ken Burns pan/zoom in the
                         render engine. Recommended default: fast on modest
                         hardware, looks intentional rather than static.
  Mode C (stock_media):  Pulls a matching stock clip from Pexels/Pixabay's
                         free APIs. Zero GPU required, good fallback when
                         no local diffusion hardware is available.

Each generator writes its asset into the project's `visuals/` directory and
returns the path, which is stored on `scene.visual.asset_path`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.schemas.project import Scene, StockAttribution, VisualMode

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

# Appended to every fast_hybrid image prompt. Without it SDXL-Turbo tends
# toward a glossy "stock photo" look; these push it to read as an actual
# photograph rather than a rendering.
PHOTOREALISTIC_STYLE_SUFFIX = (
    ", shot on 35mm film, natural light, shallow depth of field, "
    "subtle film grain, realistic textures, candid documentary photography"
)


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


async def generate_scene_visual(
    scene: Scene,
    mode: VisualMode,
    output_dir: Path,
    settings,
) -> Scene:
    """Populate scene.visual.asset_path using the requested mode, with a
    stock-media fallback if a local generation mode fails (e.g. no GPU)."""
    try:
        if mode == VisualMode.AI_VIDEO:
            path = await _generate_ai_video(scene, output_dir, settings)
        elif mode == VisualMode.FAST_HYBRID:
            path = await _generate_fast_hybrid_image(scene, output_dir, settings)
        elif mode == VisualMode.STOCK_MEDIA:
            path = await _fetch_stock_media(scene, output_dir, settings)
        else:
            raise ValueError(f"Unsupported visual mode: {mode}")
    except Exception:
        logger.exception(
            "Visual generation failed for scene %s in mode %s; falling back to stock media",
            scene.index,
            mode,
        )
        path = await _fetch_stock_media(scene, output_dir, settings)

    scene.visual.asset_path = str(path)
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


async def _generate_ai_video(scene: Scene, output_dir: Path, settings) -> Path:
    import asyncio

    output_path = output_dir / f"scene_{scene.index:02d}.mp4"

    def _run() -> Path:
        from diffusers.utils import export_to_video

        pipeline = _get_ltx_pipeline(settings.ltx_video_model_id, settings.diffusion_device)
        result = pipeline(
            prompt=scene.visual.prompt,
            negative_prompt=scene.visual.negative_prompt or DEFAULT_NEGATIVE_PROMPT,
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


async def _generate_fast_hybrid_image(scene: Scene, output_dir: Path, settings) -> Path:
    import asyncio

    output_path = output_dir / f"scene_{scene.index:02d}.png"

    def _run() -> Path:
        pipeline = _get_sdxl_pipeline(
            settings.sdxl_model_id, settings.diffusion_device, settings.sdxl_model_variant
        )
        image = pipeline(
            prompt=scene.visual.prompt + PHOTOREALISTIC_STYLE_SUFFIX,
            # NOTE: with the default SDXL-Turbo settings (4 steps,
            # guidance_scale=0.0) diffusers disables classifier-free
            # guidance entirely, so negative_prompt has no effect —
            # confirmed by reading diffusers' do_classifier_free_guidance
            # property and empirically (hand/octopus test renders were
            # equally malformed at guidance 1.8 / 8 steps, for 2.5x the
            # time). It does take effect when these settings are pointed
            # at a full SDXL fine-tune (see Settings.sdxl_* in core/config).
            negative_prompt=scene.visual.negative_prompt or DEFAULT_NEGATIVE_PROMPT,
            width=832,
            height=1472,  # vertical-friendly base resolution, upscaled by render_engine
            num_inference_steps=settings.sdxl_num_inference_steps,
            guidance_scale=settings.sdxl_guidance_scale,
        ).images[0]
        image.save(output_path)
        return output_path

    return await asyncio.to_thread(_run)


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


async def _fetch_stock_media(scene: Scene, output_dir: Path, settings) -> Path:
    output_path = output_dir / f"scene_{scene.index:02d}_stock.mp4"

    for search, api_key in (
        (_search_pexels, settings.pexels_api_key),
        (_search_pixabay, settings.pixabay_api_key),
    ):
        if not api_key:
            continue
        clip = await search(scene.visual.prompt, api_key)
        if clip:
            await _download(clip.url, output_path)
            scene.visual.attribution = clip.attribution
            return output_path

    raise RuntimeError(
        "No stock media provider configured (set PEXELS_API_KEY or PIXABAY_API_KEY) "
        "and no local visual asset could be produced."
    )


async def _search_pexels(query: str, api_key: str) -> StockClip | None:
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
        files = sorted(video["video_files"], key=lambda f: f.get("height", 0), reverse=True)
        portrait_files = [f for f in files if f.get("height", 0) >= f.get("width", 1)]
        chosen = (portrait_files or files)[0]
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


async def _search_pixabay(query: str, api_key: str) -> StockClip | None:
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
    background_color: str = "#0b0b0f",
    accent_color: str = "#7c5cff",
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
