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
  /** Real edge-tts ShortName, verified against edge_tts.list_voices(). */
  voiceId: string;
}

export const LANGUAGE_OPTIONS: LanguageOption[] = [
  { code: "en", label: "English", voiceId: "en-US-AndrewNeural" },
  { code: "tr", label: "Türkçe", voiceId: "tr-TR-AhmetNeural" },
  { code: "es", label: "Español", voiceId: "es-ES-AlvaroNeural" },
  { code: "fr", label: "Français", voiceId: "fr-FR-HenriNeural" },
  { code: "de", label: "Deutsch", voiceId: "de-DE-ConradNeural" },
  { code: "pt", label: "Português", voiceId: "pt-BR-AntonioNeural" },
  { code: "ja", label: "日本語", voiceId: "ja-JP-KeitaNeural" },
  { code: "ar", label: "العربية", voiceId: "ar-SA-HamedNeural" },
  { code: "ru", label: "Русский", voiceId: "ru-RU-DmitryNeural" },
  { code: "it", label: "Italiano", voiceId: "it-IT-DiegoNeural" },
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

export const DEFAULT_VOICE_CONFIG: VoiceConfig = {
  provider: "edge_tts",
  voice_id: "en-US-AndrewNeural",
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
