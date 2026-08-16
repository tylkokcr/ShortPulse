"""Core Pydantic data contracts shared across the pipeline.

These schemas are the single source of truth for the shape of data moving
between the script, audio, subtitle, visual and render engines. The
TypeScript mirror lives at frontend/lib/types.ts and must be kept in sync
manually (see that file's header comment).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


class VisualMode(StrEnum):
    AI_VIDEO = "ai_video"  # Mode A: LTX-Video / CogVideoX
    FAST_HYBRID = "fast_hybrid"  # Mode B: Flux/SDXL stills + Ken Burns (default)
    STOCK_MEDIA = "stock_media"  # Mode C: Pexels / Pixabay footage


class TTSProvider(StrEnum):
    EDGE_TTS = "edge_tts"
    PIPER = "piper"
    COQUI_XTTS = "coqui_xtts"


class LLMProvider(StrEnum):
    OLLAMA = "ollama"
    OPENAI = "openai"


class AspectRatio(StrEnum):
    VERTICAL_9_16 = "9:16"
    SQUARE_1_1 = "1:1"
    HORIZONTAL_16_9 = "16:9"


class VideoLength(StrEnum):
    SHORT = "short"  # ~15-25s, 5-6 scenes
    MEDIUM = "medium"  # ~30-45s, 8-10 scenes
    LONG = "long"  # ~60s+, 12-15 scenes


class ProjectSource(StrEnum):
    """Where the video came from.

    A generated project runs the whole pipeline. An upload skips to the
    end: the user already has the footage, and only wants the captioning
    that the pipeline would have produced. Both converge on the same
    finished object — a video file plus a caption track — which is what
    lets one edit-and-reburn path serve both.
    """

    GENERATED = "generated"
    UPLOAD = "upload"


class RenderStage(StrEnum):
    QUEUED = "queued"
    SCRIPT_GENERATION = "script_generation"
    AUDIO_SYNTHESIS = "audio_synthesis"
    TRANSCRIPTION = "transcription"
    VISUAL_GENERATION = "visual_generation"
    SUBTITLE_GENERATION = "subtitle_generation"
    ASSEMBLY = "assembly"
    DONE = "done"
    FAILED = "failed"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    RENDERING = "rendering"
    COMPLETE = "complete"
    FAILED = "failed"


# --------------------------------------------------------------------------
# Script / scene schemas (LLM layer output)
# --------------------------------------------------------------------------


class Word(BaseModel):
    """A single word with millisecond-accurate timing, produced by the
    transcription step and consumed by the subtitle renderer."""

    text: str
    start_ms: int
    end_ms: int
    confidence: float | None = None


class SceneAudio(BaseModel):
    voiceover_line: str
    audio_path: str | None = None
    duration_ms: int | None = None
    words: list[Word] = Field(default_factory=list)


class StockAttribution(BaseModel):
    """Credit for a stock clip.

    Pexels' API terms require a prominent link back to Pexels from any
    application using the API, and crediting the photographer where
    possible. That is a condition of the licence, not a courtesy, so the
    pieces needed to render a real link are captured at fetch time —
    reconstructing them later is impossible once the clip is downloaded.
    """

    provider: str                      # "Pexels" / "Pixabay"
    provider_url: str
    author: str | None = None
    author_url: str | None = None
    source_url: str | None = None      # the clip's own page

    def as_text(self) -> str:
        """One line a user can paste into a post description."""
        if self.author:
            return f"Video by {self.author} on {self.provider}"
        return f"Video from {self.provider}"


class SceneVisual(BaseModel):
    prompt: str
    negative_prompt: str | None = None
    mode: VisualMode = VisualMode.FAST_HYBRID
    asset_path: str | None = None
    # Populated for stock_media scenes only; AI-generated visuals have
    # nobody to credit.
    attribution: StockAttribution | None = None
    # Seconds of hosted inference this scene was billed for, when it was
    # generated over an API rather than on this machine. Reported by the
    # provider, so it is what the invoice will say rather than what we
    # timed — render_manager sums it into timings.json, where the rest of
    # the stage's cost already lives.
    predict_time_s: float | None = None
    # How many times this scene's visual has been re-rolled since the
    # render. Three jobs, which is why it is a count and not a flag: it
    # keys the charge so a retried request is free and a second re-roll is
    # not, it selects a different stock clip from the same search, and the
    # UI can say a scene has been re-drawn.
    revision: int = 0


class Scene(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    index: int
    duration_s: float = Field(ge=3, le=5, description="Target scene length in seconds")
    visual: SceneVisual
    audio: SceneAudio
    is_outro: bool = Field(
        default=False, description="Branded closing card appended after the LLM-generated scenes"
    )

    model_config = ConfigDict(use_enum_values=True)


class ScriptOutput(BaseModel):
    """Structured output returned by the script_engine LLM call."""

    topic: str
    hook: str = Field(description="High-retention hook line delivered in the first 3s")
    scenes: list[Scene]
    total_duration_s: float
    call_to_action: str | None = None


# --------------------------------------------------------------------------
# Project configuration (request payload from the frontend)
# --------------------------------------------------------------------------


class VoiceConfig(BaseModel):
    """Voice settings.

    Defaults to Piper: fully local, MIT licensed, and therefore usable in a
    commercial/hosted context. edge-tts sounds good and needs no key, but it
    calls an undocumented Microsoft endpoint meant for the Edge browser's
    read-aloud feature — fine for personal use, not something to build a
    paid product on.
    """

    provider: TTSProvider = TTSProvider.PIPER
    # Empty means "pick the default voice for the project's language" (see
    # audio_engine.PIPER_VOICE_BY_LANGUAGE). Set explicitly to override.
    voice_id: str = ""
    # edge-tts only; Piper exposes speed differently and ignores these.
    rate: str = "+0%"
    pitch: str = "+0Hz"


class LLMConfig(BaseModel):
    provider: LLMProvider = LLMProvider.OLLAMA
    model: str = "llama3"
    base_url: str = "http://localhost:11434"
    api_key: str | None = None
    temperature: float = 0.8


class SubtitleStyle(BaseModel):
    font_family: str = "Montserrat"
    font_size: int = 84
    primary_color: str = "&H00FFFFFF"  # ASS BGR hex, white
    highlight_color: str = "&H0000D7FF"  # gold/amber active-word highlight
    outline_color: str = "&H00000000"
    outline_width: int = 4
    position: str = "bottom_third"
    max_words_per_line: int = 4
    uppercase: bool = True


class CaptionTrack(BaseModel):
    """Words timed against the finished video, plus how to draw them.

    Deliberately not tied to scenes. A generated project's words start out
    relative to each scene's own audio clip; an uploaded video has no
    scenes at all. Materialising the track in absolute time is what makes
    the two editable by the same code — and what makes a caption edit a
    single ffmpeg pass instead of a re-run of the pipeline.
    """

    words: list[Word] = Field(default_factory=list)
    style: SubtitleStyle = Field(default_factory=SubtitleStyle)


class OverlayPosition(StrEnum):
    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


class TextOverlay(BaseModel):
    """A line of text the user placed on the video themselves.

    Distinct from captions: captions are a transcript with timings derived
    from speech, while this is authored — a title, a label, a joke. Both
    end up as events in the same .ass file, which is why the renderer needs
    only one pass and why the typography matches.
    """

    text: str = Field(max_length=200)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    position: OverlayPosition = OverlayPosition.TOP
    font_size: int = Field(default=72, ge=12, le=300)
    color: str = "&H00FFFFFF"


class Layout(StrEnum):
    FULL = "full"
    # The split-screen format: the video on top, a second clip underneath.
    SPLIT_V = "split_v"


class MusicConfig(BaseModel):
    enabled: bool = True
    # What HTTP clients choose with: an id from GET /api/music, resolved
    # server-side against the music directory.
    track_id: str | None = None
    # Absolute path handed to ffmpeg. Never trusted from an HTTP request —
    # the projects route overwrites it from `track_id` — because ffmpeg
    # would happily open any file the server can read and mix it into a
    # video the caller then downloads. In-process callers (a self-hosted
    # script) may still set it directly.
    track_path: str | None = None
    volume_db: float = -18.0
    duck_on_voice: bool = True


class EditSpec(BaseModel):
    """What the finished video should look like, as a document.

    The pipeline produces one of these; editing mutates it; re-rendering
    replays it. That separation is what makes an edit cheap — the burn-in
    step already takes an arbitrary video plus a subtitle file, so applying
    an edit is one ffmpeg pass over footage that is already on disk, not a
    re-run of the LLM, the voice and the visuals.
    """

    layout: Layout = Layout.FULL
    # Server-derived path to the bottom clip in a split. Never accepted
    # from a client, for the same reason as MusicConfig.track_path.
    secondary_path: str | None = None
    captions: CaptionTrack | None = None
    overlays: list[TextOverlay] = Field(default_factory=list, max_length=50)
    music: MusicConfig | None = None


class OutroConfig(BaseModel):
    """Optional branded closing card appended after the LLM-generated
    scenes, so the video doesn't end on whatever the model happened to
    imagine for the call-to-action (e.g. a random editing-software UI)."""

    enabled: bool = False
    text: str | None = Field(
        default=None, description="Falls back to the script's call_to_action if unset"
    )
    logo_path: str | None = None
    # Matches the site's palette, because this card is the one piece of
    # brand that ends up burned into the video itself.
    background_color: str = "#0a0a0a"
    accent_color: str = "#ff5c1a"


class ProjectConfig(BaseModel):
    """Top-level request body for POST /api/projects."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    source: ProjectSource = ProjectSource.GENERATED
    raw_script: str | None = Field(
        default=None, description="If provided, skips LLM scene generation"
    )
    aspect_ratio: AspectRatio = AspectRatio.VERTICAL_9_16
    fps: int = 30
    visual_mode: VisualMode = VisualMode.FAST_HYBRID
    # Id from app.services.art_styles. Only affects the locally generated
    # modes — stock footage is whatever the videographer shot.
    art_style: str = "photoreal"
    video_length: VideoLength = VideoLength.SHORT
    language: str = Field(
        default="en",
        description="BCP-47-ish language code for the spoken script (hook/voiceover/CTA). "
        "Visual prompts are always written in English regardless. See "
        "script_engine.LANGUAGE_NAMES for supported codes.",
    )
    llm: LLMConfig = Field(default_factory=LLMConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    subtitles: SubtitleStyle = Field(default_factory=SubtitleStyle)
    music: MusicConfig = Field(default_factory=MusicConfig)
    outro: OutroConfig = Field(default_factory=OutroConfig)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(use_enum_values=True)


class Project(BaseModel):
    config: ProjectConfig
    status: ProjectStatus = ProjectStatus.DRAFT
    script: ScriptOutput | None = None
    output_path: str | None = None
    error: str | None = None
    # The video this project started from, when it wasn't generated here.
    # Always a server-derived path under the project's own directory —
    # never a client-supplied one, which would hand ffmpeg an arbitrary
    # file to open (same reasoning as MusicConfig.track_path).
    source_path: str | None = None
    # Materialised after the first render so captions can be corrected and
    # reburned without re-running the pipeline. Absent until then.
    captions: CaptionTrack | None = None
    # The user's edits on top of what was generated. Absent until they
    # make one, at which point it — not `captions` — is what the video
    # shows.
    edit: EditSpec | None = None
    # What this render was charged, recorded on the project so the amount
    # refunded on failure is the amount taken — not a price recomputed
    # later, which could have changed in between. 0 on self-hosted
    # installs, where there is no billing at all.
    credits_cost: int = 0
    # Whether one of this project's scenes could be re-drawn, and the
    # sentence to show when it can't.
    #
    # Computed per request from what is on disk, never persisted — which
    # is also why neither name appears in PostgresProjectStore._COLUMNS.
    # The answer changes without the project changing: every video
    # rendered before re-rolling existed is a permanent no, and every
    # other one becomes a no when its retention window closes. A UI that
    # assumed yes would offer a button that always failed.
    can_regenerate: bool = False
    regenerate_blocked_reason: str | None = None


# --------------------------------------------------------------------------
# Render progress (WebSocket push schema)
# --------------------------------------------------------------------------


class RenderProgress(BaseModel):
    project_id: str
    stage: RenderStage
    progress_pct: float = Field(ge=0, le=100)
    message: str
    current_scene: int | None = None
    total_scenes: int | None = None
    output_path: str | None = None
    error: str | None = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(use_enum_values=True)
