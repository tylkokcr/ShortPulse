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
# Shipped with the app rather than relied upon from the OS. `Montserrat` is
# the caption font every project defaults to, and it is not installed on a
# typical machine — libass silently substitutes whatever fontconfig offers,
# so the same project rendered on a laptop and in a container came out in
# different typefaces. Passing this to the `ass` filter makes the output
# depend on the repository instead of the host. OFL 1.1; see OFL.txt.
FONTS_DIR = BACKEND_ROOT / "app" / "assets" / "fonts"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    #
    # These are the *only* values the script engine ever runs with. Whatever
    # a request carries in `config.llm` is discarded at the HTTP boundary
    # and replaced with this — see projects.create_project. A client-chosen
    # `base_url` is a server-side fetch to an address the client picked.
    llm_provider: str = "ollama"
    llm_model: str = "llama3"
    ollama_base_url: str = "http://localhost:11434"
    # Required when llm_provider is "openai". A hosted deployment usually
    # wants this: an 8B model needs ~6GB of RAM and, on a modest VPS CPU,
    # takes longer to write the script than the rest of the render takes to
    # produce the video.
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

    # Which implementation runs fast_hybrid:
    #   "local"     — diffusers on this machine, needs torch + diffusers.
    #   "replicate" — the same checkpoint on Replicate's hosted inference.
    #
    # A preference rather than a requirement: visual_engine.image_backend
    # falls through to whichever backend this install can actually run, so
    # the container (a token, no torch) and a GPU box (torch, no token)
    # both need nothing set here. Only a machine with both has a choice to
    # express, and this is where it says so.
    #
    # Like the LLM block above, the token is read from here and never from
    # a request. There is deliberately no field for it on ProjectConfig:
    # the `llm` block had to be *discarded* at the HTTP boundary once a
    # client-chosen base_url turned out to be a server-side fetch, and a
    # field that does not exist cannot be forgotten about later.
    visual_provider: str = "local"
    replicate_api_token: str | None = None
    # Pinned to a version hash, not a bare owner/name. Model owners revise
    # what `owner/name` points at, and a revised input schema is a 422 on
    # every scene of every render — which the fallback would turn into a
    # silent stock-media downgrade rather than an error anyone sees. This
    # id is RealVisXL_V4.0, the same checkpoint sdxl_model_id names, so the
    # art styles and the published samples describe both backends.
    replicate_image_model: str = (
        "adirik/realvisxl-v4.0:"
        "85a58cc71587cc27539b7c83eb1ce4aea02feedfb9a9fae0598cebc110a3d695"
    )
    # Wall clock for one image, covering the retries, the queue and the
    # generation. A prediction still running when this expires is
    # cancelled: it bills for the seconds it burns whether or not anyone
    # is waiting for the result.
    #
    # Measured rather than guessed: an image bills ~3.5s of predict time,
    # but the first request after the model has gone cold took 88s of wall
    # clock to come back, and a rate-limited one adds Retry-After: 10 on
    # top of that. 120 left no room for both at once.
    replicate_timeout_s: float = 180.0

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
    # Credits handed to a user the first time they authenticate.
    #
    # This was 15 when the giveaway was our own idle compute and the only
    # cost of a farmed address was electricity. Serving fast_hybrid from
    # Replicate turned it into cash: a signup is now up to ~30 generated
    # images, and a thousand throwaway accounts is a real invoice against
    # zero revenue. 5 still buys a full short render to judge the output
    # by, which is what the grant is for, while cutting the cost of an
    # abused signup by two thirds. Set a spend limit on the Replicate key
    # as well — this bounds one account, not the total.
    signup_credit_grant: int = 5
    # Signs the short-lived tokens in video URLs. A <video> tag can't send
    # an Authorization header, so playback of an owned project needs the
    # credential in the URL — same shape as an S3 presigned link. Leave
    # unset and one is generated per process: fine for a single local
    # instance, but links then break on restart and across replicas.
    media_url_secret: str | None = None
    media_url_ttl_s: int = 900

    # Payments (hosted deployment only)
    # Without a secret key there is no checkout: the endpoints report
    # themselves unavailable rather than half-working, and a self-hosted
    # install never sees them.
    stripe_secret_key: str | None = None
    # Verifies that a webhook really came from Stripe. Mandatory whenever
    # the webhook route is reachable — the handler grants credits, so an
    # unverified one is a free-credits endpoint for anyone who finds it.
    stripe_webhook_secret: str | None = None
    # What the packs are priced in. Changing it does not convert anything:
    # the numbers in credits.CREDIT_PACKS are reinterpreted in the new
    # currency, so 900 becomes €9.00 rather than the euro equivalent of $9.
    stripe_currency: str = "usd"
    # Let Stripe work out and collect VAT.
    #
    # Off by default because it fails the checkout outright unless Stripe
    # Tax is activated and an origin address is set in the dashboard —
    # better a deliberate switch than a payment page that 500s.
    #
    # Selling digital services to EU consumers means VAT at the *buyer's*
    # local rate, which is not something to work out by hand. Prices are
    # sent tax-inclusive, because EU consumer law wants the displayed price
    # to be the final one: a €9 pack stays €9 and the VAT comes out of it,
    # varying the net by country (19% in Germany, 27% in Hungary).
    stripe_automatic_tax: bool = False

    # Where Stripe returns the customer. Must be a URL of *this* app.
    checkout_success_url: str = "http://localhost:3000/library?purchase=ok"
    checkout_cancel_url: str = "http://localhost:3000/#pricing"

    # Social publishing (hosted deployment only)
    #
    # Where this deployment is reachable from the public internet, with no
    # trailing slash. Two things need it and neither can be derived from a
    # request:
    #
    #   * the OAuth redirect_uri sent to each platform, which has to match
    #     what is registered in their developer console exactly
    #   * the video URL Instagram and TikTok are handed, because both fetch
    #     the file themselves rather than accepting an upload
    #
    # That second one is why this cannot default to something harmless.
    # A localhost URL given to Instagram is a fetch from Instagram's
    # network to Instagram's own loopback, which fails as a media error
    # with nothing pointing back here.
    public_base_url: str = "http://localhost:3000"

    # Encrypts the platform tokens before they are written (see
    # services/social_tokens.py). Without it there is no publishing at
    # all: the endpoints report themselves unavailable rather than
    # storing somebody's YouTube credentials in plain text.
    #
    #     openssl rand -base64 48
    #
    # Changing it orphans every stored connection — users reconnect, which
    # is one OAuth round trip and the only honest recovery.
    social_token_secret: str | None = None

    # YouTube upload, via the Data API v3.
    #
    # A separate OAuth client from the one that signs users in, even
    # though both live in the same Google Cloud project. The sign-in
    # client is configured inside Supabase and redirects there; this one
    # redirects to our own API, because the tokens it returns must never
    # reach the browser.
    #
    # Note what an unaudited project can do: uploads succeed and are
    # forced to `private` regardless of what is asked for. That is not a
    # failure to handle, it is a state to report — see social_posts.privacy.
    youtube_client_id: str | None = None
    youtube_client_secret: str | None = None

    # How long the signed URL handed to a platform stays valid. Longer
    # than the playback TTL above because nothing is watching this one:
    # the platform fetches on its own schedule, behind its own queue, and
    # a link that expired while it waited is a failure with no cause
    # visible from either side.
    social_media_url_ttl_s: int = 3600
    max_concurrent_publishes: int = 2

    # Error reporting (optional)
    # A render failure is caught and written to the project row, so the
    # exception never leaves the process — on a deployment that means the
    # first you hear of a broken pipeline is a user telling you. Unset,
    # nothing is sent anywhere.
    sentry_dsn: str | None = None
    sentry_environment: str = "development"

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
    # How long a finished project keeps the files a scene re-roll needs —
    # its per-scene voiceover and clips, roughly 3-7MB on top of the ~28MB
    # a finished project already occupies. After this, prune_storage.py
    # sweeps them and the project can no longer be re-rolled.
    #
    # Thirty days because re-rolling is a "this render came out wrong"
    # action taken while the video is still unpublished. Nobody re-rolls a
    # scene from a video they posted two months ago, and the alternative —
    # keeping them forever — turns a bounded cost into an unbounded one.
    regeneration_retention_days: int = 30

    # Background music — used when MusicConfig.enabled is true but the
    # request didn't supply its own track_path.
    default_music_track_path: Path = DEFAULT_MUSIC_TRACK


@lru_cache
def get_settings() -> Settings:
    return Settings()


def project_dir(project_id: str) -> Path:
    """Root directory for a single project's generated assets.

    The id is validated at the schema (ProjectConfig.id is pattern-bound),
    but this function is the one that turns it into a path and mkdir's it,
    so it re-checks rather than trusting that every caller came through the
    schema. A migration backfill, a test, or a future endpoint that builds
    an id some other way would otherwise reopen the traversal this closes.
    The result must live directly under storage_root and nowhere else.
    """
    root = get_settings().storage_root.resolve()
    path = (root / project_id).resolve()
    if path.parent != root:
        raise ValueError(f"Unsafe project id: {project_id!r}")
    for sub in ("audio", "visuals", "subtitles", "output", "source"):
        (path / sub).mkdir(parents=True, exist_ok=True)
    return path
