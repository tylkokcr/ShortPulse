/**
 * TypeScript mirror of backend/app/schemas/project.py.
 * Keep these two files in sync manually whenever the Pydantic schema changes.
 */

export type VisualMode = "ai_video" | "fast_hybrid" | "stock_media";
export type TTSProvider = "edge_tts" | "piper" | "coqui_xtts";
export type LLMProvider = "ollama" | "openai";
export type AspectRatio = "9:16" | "1:1" | "16:9";
export type VideoLength = "short" | "medium" | "long";

/** Matches backend/app/engines/script_engine.py's LANGUAGE_NAMES keys. */
export type LanguageCode = "en" | "tr" | "es" | "fr" | "de" | "pt" | "ja" | "ar" | "ru" | "it";

export interface LanguageOption {
  code: LanguageCode;
  label: string;
}

/**
 * Languages with a local Piper voice, mirroring
 * audio_engine.PIPER_VOICE_BY_LANGUAGE. The backend resolves the actual
 * voice model from the language, so no voice id is sent from here.
 *
 * Japanese ("ja") is deliberately absent: the script engine can write it,
 * but Piper ships no Japanese voice, and the only alternative today is
 * edge-tts, which has no commercial licence. Re-add it once a licensed
 * local engine covers Japanese (Kokoro-82M does).
 */
export const LANGUAGE_OPTIONS: LanguageOption[] = [
  { code: "en", label: "English" },
  { code: "tr", label: "Türkçe" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
  { code: "de", label: "Deutsch" },
  { code: "pt", label: "Português" },
  { code: "ar", label: "العربية" },
  { code: "ru", label: "Русский" },
  { code: "it", label: "Italiano" },
];

export type RenderStage =
  | "queued"
  | "script_generation"
  | "audio_synthesis"
  | "transcription"
  | "visual_generation"
  | "subtitle_generation"
  | "assembly"
  | "done"
  | "failed";

export type ProjectStatus = "draft" | "rendering" | "complete" | "failed";

export interface Word {
  text: string;
  start_ms: number;
  end_ms: number;
  confidence?: number | null;
}

export interface SceneAudio {
  voiceover_line: string;
  audio_path?: string | null;
  duration_ms?: number | null;
  words: Word[];
}

/** Credit for a stock clip. Pexels' API terms require a visible link back
 *  to Pexels and, where possible, to the photographer — so this must be
 *  rendered, not just carried. */
export interface StockAttribution {
  provider: string;
  provider_url: string;
  author?: string | null;
  author_url?: string | null;
  source_url?: string | null;
}

export interface SceneVisual {
  prompt: string;
  negative_prompt?: string | null;
  mode: VisualMode;
  asset_path?: string | null;
  /** Stock scenes only; AI-generated visuals have nobody to credit. */
  attribution?: StockAttribution | null;
}

export interface Scene {
  id: string;
  index: number;
  duration_s: number;
  visual: SceneVisual;
  audio: SceneAudio;
}

export interface ScriptOutput {
  topic: string;
  hook: string;
  scenes: Scene[];
  total_duration_s: number;
  call_to_action?: string | null;
}

export interface VoiceConfig {
  provider: TTSProvider;
  voice_id: string;
  rate: string;
  pitch: string;
}

export interface LLMConfig {
  provider: LLMProvider;
  model: string;
  base_url: string;
  api_key?: string | null;
  temperature: number;
}

export interface SubtitleStyle {
  font_family: string;
  font_size: number;
  primary_color: string;
  highlight_color: string;
  outline_color: string;
  outline_width: number;
  position: string;
  max_words_per_line: number;
  uppercase: boolean;
}

export interface MusicConfig {
  enabled: boolean;
  /** Id from GET /api/music. The server resolves it to a path — clients
   *  can't name arbitrary files, so `track_path` is response-only. */
  track_id?: string | null;
  track_path?: string | null;
  volume_db: number;
  duck_on_voice: boolean;
}

/** One entry in the background-music library. */
export interface MusicTrack {
  id: string;
  name: string;
}

/** One art style. `sample` is a filename under /art-styles, produced by
 *  the real pipeline rather than sourced elsewhere. */
export interface ArtStyle {
  id: string;
  name: string;
  description: string;
  sample: string;
  is_default: boolean;
}

/** A selectable Piper voice. `id` goes straight into VoiceConfig.voice_id.
 *  Piper's catalog records no gender or tone, so the only descriptors here
 *  are the ones it actually publishes — hence the audio preview. */
export interface Voice {
  id: string;
  name: string;
  language: string;
  region: string;
  quality: string;
  is_default: boolean;
}

export interface OutroConfig {
  enabled: boolean;
  text?: string | null;
  logo_path?: string | null;
  background_color: string;
  accent_color: string;
}

/** Where the video came from. An upload skips generation entirely and
 *  only runs the captioning tail of the pipeline. */
export type ProjectSource = "generated" | "upload";

export interface ProjectConfig {
  id: string;
  topic: string;
  source: ProjectSource;
  raw_script?: string | null;
  aspect_ratio: AspectRatio;
  fps: number;
  visual_mode: VisualMode;
  /** Id from GET /api/art-styles. Only affects the locally generated
   *  modes — stock footage is whatever the videographer shot. */
  art_style: string;
  video_length: VideoLength;
  language: string;
  llm: LLMConfig;
  voice: VoiceConfig;
  subtitles: SubtitleStyle;
  music: MusicConfig;
  outro: OutroConfig;
  created_at: string;
}

/** Words timed against the finished video. Materialised after the first
 *  render so captions can be corrected and reburned without re-running the
 *  pipeline. */
export interface CaptionTrack {
  words: Word[];
  style: SubtitleStyle;
}

export type OverlayPosition = "top" | "middle" | "bottom";

/** Text the user placed themselves, as opposed to the transcript. Both are
 *  drawn by libass from the same .ass file, which is why one burn-in pass
 *  covers both. */
export interface TextOverlay {
  text: string;
  start_ms: number;
  end_ms: number;
  position: OverlayPosition;
  font_size: number;
  color: string;
}

export type Layout = "full" | "split_v";

export interface EditSpec {
  layout: Layout;
  captions?: CaptionTrack | null;
  overlays: TextOverlay[];
  /** Server-derived path to the bottom clip. Present once one is uploaded;
   *  the client never sends it, only the layout that uses it. */
  secondary_path?: string | null;
}

export interface Project {
  config: ProjectConfig;
  status: ProjectStatus;
  script?: ScriptOutput | null;
  output_path?: string | null;
  error?: string | null;
  /** The uploaded video this project started from, if it wasn't generated. */
  source_path?: string | null;
  captions?: CaptionTrack | null;
  /** The user's edits on top of what was generated. Absent until they make
   *  one, at which point it — not `captions` — is what the video shows. */
  edit?: EditSpec | null;
  /** Credits this render was charged. Always 0 on a self-hosted install,
   *  where there is no billing. */
  credits_cost: number;
}

/**
 * GET /api/projects/{id}/timings — per-stage wall clock, written by the
 * pipeline next to the output. Empty for renders that predate it and for
 * uploads that failed before the report was written, so every field is
 * optional.
 */
export interface RenderTimings {
  total_s?: number;
  stages_s?: Record<string, number>;
  stage_share_pct?: Record<string, number>;
  video_duration_s?: number;
  scene_count?: number;
  word_count?: number;
  visual_mode?: string;
  diffusion_device?: string;
  language?: string;
}

/** GET /api/credits. `enabled: false` means self-hosted — hide the credit
 *  UI entirely rather than showing a balance of zero. */
export interface CreditSummary {
  enabled: boolean;
  balance: number;
  entries: CreditEntry[];
  /** Keyed `"<visual_mode>:<video_length>"`, so the UI can quote a price
   *  before the user submits. */
  pricing: Record<string, number>;
  /** Served even when `enabled` is false, so the marketing page renders
   *  the same prices the ledger would charge. */
  packs: CreditPack[];
}

/** One-off purchase — nothing here renews, and credits never expire. */
export interface CreditPack {
  id: string;
  credits: number;
  price_cents: number;
  popular: boolean;
}

export interface CreditEntry {
  id: number;
  delta: number;
  reason: "purchase" | "grant" | "render" | "refund" | "adjustment";
  project_id?: string | null;
  note?: string | null;
  created_at: string;
}

export interface RenderProgress {
  project_id: string;
  stage: RenderStage;
  progress_pct: number;
  message: string;
  current_scene?: number | null;
  total_scenes?: number | null;
  output_path?: string | null;
  error?: string | null;
  updated_at: string;
}

// --------------------------------------------------------------------------
// Sane client-side defaults, mirroring the Pydantic field defaults.
// --------------------------------------------------------------------------

// Piper: fully local and MIT licensed. An empty voice_id tells the backend
// to pick the default voice for the project's language.
export const DEFAULT_VOICE_CONFIG: VoiceConfig = {
  provider: "piper",
  voice_id: "",
  rate: "+0%",
  pitch: "+0Hz",
};

export const DEFAULT_LLM_CONFIG: LLMConfig = {
  provider: "ollama",
  model: "llama3",
  base_url: "http://localhost:11434",
  temperature: 0.8,
};

export const DEFAULT_SUBTITLE_STYLE: SubtitleStyle = {
  font_family: "Montserrat",
  font_size: 84,
  primary_color: "&H00FFFFFF",
  highlight_color: "&H0000D7FF",
  outline_color: "&H00000000",
  outline_width: 4,
  position: "bottom_third",
  max_words_per_line: 4,
  uppercase: true,
};

export const DEFAULT_MUSIC_CONFIG: MusicConfig = {
  enabled: true,
  track_id: null,
  volume_db: -18.0,
  duck_on_voice: true,
};

export const DEFAULT_OUTRO_CONFIG: OutroConfig = {
  enabled: false,
  text: null,
  logo_path: null,
  background_color: "#0a0a0a",
  accent_color: "#ff5c1a",
};
