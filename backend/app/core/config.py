"""Application-wide settings, loaded from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = BACKEND_ROOT / "app" / "storage" / "projects"
# "Airport Lounge" by Kevin MacLeod (incompetech.com), CC BY 3.0 — see
# app/assets/music/ATTRIBUTION.md.
DEFAULT_MUSIC_TRACK = BACKEND_ROOT / "app" / "assets" / "music" / "Airport Lounge.mp3"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    ollama_base_url: str = "http://localhost:11434"
    openai_api_key: str | None = None

    # TTS / ASR
    whisper_model_size: str = "small"
    whisper_device: str = "cpu"  # "cuda" if a GPU is available
    whisper_compute_type: str = "int8"

    # Visual generation
    pexels_api_key: str | None = None
    pixabay_api_key: str | None = None
    # fast_hybrid image model. Defaults to a photorealistic SDXL fine-tune,
    # which needs full guidance and ~25 steps — measurably slower per scene
    # (~59s vs ~5s on Apple Silicon) but reads as an actual photograph
    # rather than a glossy render.
    #
    # For the fast alternative, set in .env:
    #   SDXL_MODEL_ID=stabilityai/sdxl-turbo
    #   SDXL_MODEL_VARIANT=
    #   SDXL_NUM_INFERENCE_STEPS=4
    #   SDXL_GUIDANCE_SCALE=0.0
    # Note that turbo's guidance_scale=0.0 makes diffusers disable
    # classifier-free guidance, so negative prompts have no effect there.
    sdxl_model_id: str = "SG161222/RealVisXL_V4.0"
    sdxl_model_variant: str | None = "fp16"  # halves download + resident size
    sdxl_num_inference_steps: int = 25
    sdxl_guidance_scale: float = 7.0
    ltx_video_model_id: str = "Lightricks/LTX-Video"
    diffusion_device: str = "cpu"

    # Rendering
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    # Silence appended after each scene's voiceover. Scene clips are
    # concatenated back to back, so without a pause here one sentence ends
    # and the next begins in the same instant — it sounds like the narrator
    # is talking over themselves. 0.35s is a natural sentence break; raise
    # it for a slower read, set 0 to butt the lines together.
    scene_gap_s: float = 0.35
    default_fps: int = 30
    default_resolution: tuple[int, int] = (1080, 1920)

    # Persistence
    # Postgres connection string (Supabase gives you one under
    # Settings -> Database). Leave empty to keep projects in memory, which
    # is fine for a single-user local install but loses everything on
    # restart — including any render that was in flight.
    database_url: str | None = None

    # Auth (hosted deployment only)
    # Supabase project URL, e.g. https://abcdefgh.supabase.co. Setting it
    # turns on token verification; leaving it empty means anonymous access,
    # which is the self-hosted install. No secret is needed either way —
    # tokens are checked against the project's public JWKS.
    supabase_url: str | None = None
    # Reject unauthenticated requests outright. Must be true on any public
    # deployment: without it an anonymous caller looks like a self-hoster
    # and renders for free.
    require_auth: bool = False
    # Credits handed to a user the first time they authenticate. This is
    # real compute given away, so it is a deliberate number rather than a
    # round one: 15 buys five short fast_hybrid renders — enough to judge
    # the output quality before paying, and not enough to be worth farming
    # new addresses for.
    signup_credit_grant: int = 15
    # Signs the short-lived tokens in video URLs. A <video> tag can't send
    # an Authorization header, so playback of an owned project needs the
    # credential in the URL — same shape as an S3 presigned link. Leave
    # unset and one is generated per process: fine for a single local
    # instance, but links then break on restart and across replicas.
    media_url_secret: str | None = None
    media_url_ttl_s: int = 900

    # Throttling. Credits bound what a render costs, not how fast someone
    # can ask — one account could otherwise fill the render queue ahead of
    # everyone else. Counted per authenticated user, or per client address
    # when there is no user.
    render_submissions_per_hour: int = 30
    api_requests_per_minute: int = 120  # 15 minutes: long enough to watch, short enough to leak harmlessly

    # Server
    # Next.js dev falls back to 3001/3002 when 3000 is taken, so allow the
    # range rather than pinning a single port.
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
    ]
    storage_root: Path = STORAGE_ROOT
    max_concurrent_renders: int = 2

    # Background music — used when MusicConfig.enabled is true but the
    # request didn't supply its own track_path.
    default_music_track_path: Path = DEFAULT_MUSIC_TRACK


@lru_cache
def get_settings() -> Settings:
    return Settings()


def project_dir(project_id: str) -> Path:
    """Root directory for a single project's generated assets."""
    path = get_settings().storage_root / project_id
    for sub in ("audio", "visuals", "subtitles", "output", "source"):
        (path / sub).mkdir(parents=True, exist_ok=True)
    return path
