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

export interface SceneVisual {
  prompt: string;
  negative_prompt?: string | null;
  mode: VisualMode;
  asset_path?: string | null;
  source_attribution?: string | null;
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
  track_path?: string | null;
  volume_db: number;
  duck_on_voice: boolean;
}

export interface OutroConfig {
  enabled: boolean;
  text?: string | null;
  logo_path?: string | null;
  background_color: string;
  accent_color: string;
}

export interface ProjectConfig {
  id: string;
  topic: string;
  raw_script?: string | null;
  aspect_ratio: AspectRatio;
  fps: number;
  visual_mode: VisualMode;
  video_length: VideoLength;
  language: string;
  llm: LLMConfig;
  voice: VoiceConfig;
  subtitles: SubtitleStyle;
  music: MusicConfig;
  outro: OutroConfig;
  created_at: string;
}

export interface Project {
  config: ProjectConfig;
  status: ProjectStatus;
  script?: ScriptOutput | null;
  output_path?: string | null;
  error?: string | null;
  /** Credits this render was charged. Always 0 on a self-hosted install,
   *  where there is no billing. */
  credits_cost: number;
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
  track_path: null,
  volume_db: -18.0,
  duck_on_voice: true,
};

export const DEFAULT_OUTRO_CONFIG: OutroConfig = {
  enabled: false,
  text: null,
  logo_path: null,
  background_color: "#0b0b0f",
  accent_color: "#7c5cff",
};
