"""Core Pydantic data contracts shared across the pipeline.

These schemas are the single source of truth for the shape of data moving
between the script, audio, subtitle, visual and render engines. The
TypeScript mirror lives at frontend/lib/types.ts and must be kept in sync
manually (see that file's header comment).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


class VisualMode(str, Enum):
    AI_VIDEO = "ai_video"  # Mode A: LTX-Video / CogVideoX
    FAST_HYBRID = "fast_hybrid"  # Mode B: Flux/SDXL stills + Ken Burns (default)
    STOCK_MEDIA = "stock_media"  # Mode C: Pexels / Pixabay footage


class TTSProvider(str, Enum):
    EDGE_TTS = "edge_tts"
    PIPER = "piper"
    COQUI_XTTS = "coqui_xtts"


class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"


class AspectRatio(str, Enum):
    VERTICAL_9_16 = "9:16"
    SQUARE_1_1 = "1:1"
    HORIZONTAL_16_9 = "16:9"


class VideoLength(str, Enum):
    SHORT = "short"  # ~15-25s, 5-6 scenes
    MEDIUM = "medium"  # ~30-45s, 8-10 scenes
    LONG = "long"  # ~60s+, 12-15 scenes


class RenderStage(str, Enum):
    QUEUED = "queued"
    SCRIPT_GENERATION = "script_generation"
    AUDIO_SYNTHESIS = "audio_synthesis"
    TRANSCRIPTION = "transcription"
    VISUAL_GENERATION = "visual_generation"
    SUBTITLE_GENERATION = "subtitle_generation"
    ASSEMBLY = "assembly"
    DONE = "done"
    FAILED = "failed"


class ProjectStatus(str, Enum):
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


class SceneVisual(BaseModel):
    prompt: str
    negative_prompt: str | None = None
    mode: VisualMode = VisualMode.FAST_HYBRID
    asset_path: str | None = None
    source_attribution: str | None = None  # e.g. Pexels photographer credit


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


class MusicConfig(BaseModel):
    enabled: bool = True
    track_path: str | None = None
    volume_db: float = -18.0
    duck_on_voice: bool = True


class OutroConfig(BaseModel):
    """Optional branded closing card appended after the LLM-generated
    scenes, so the video doesn't end on whatever the model happened to
    imagine for the call-to-action (e.g. a random editing-software UI)."""

    enabled: bool = False
    text: str | None = Field(
        default=None, description="Falls back to the script's call_to_action if unset"
    )
    logo_path: str | None = None
    background_color: str = "#0b0b0f"
    accent_color: str = "#7c5cff"


class ProjectConfig(BaseModel):
    """Top-level request body for POST /api/projects."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    raw_script: str | None = Field(
        default=None, description="If provided, skips LLM scene generation"
    )
    aspect_ratio: AspectRatio = AspectRatio.VERTICAL_9_16
    fps: int = 30
    visual_mode: VisualMode = VisualMode.FAST_HYBRID
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
    # What this render was charged, recorded on the project so the amount
    # refunded on failure is the amount taken — not a price recomputed
    # later, which could have changed in between. 0 on self-hosted
    # installs, where there is no billing at all.
    credits_cost: int = 0


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
