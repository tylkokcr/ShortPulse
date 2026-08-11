import { create } from "zustand";
import { DEFAULT_CAPTION_PRESET, presetById } from "./captionStyles";
import {
  DEFAULT_LLM_CONFIG,
  DEFAULT_MUSIC_CONFIG,
  DEFAULT_OUTRO_CONFIG,
  DEFAULT_VOICE_CONFIG,
  type CreditSummary,
  type LanguageCode,
  type Project,
  type ProjectConfig,
  type RenderProgress,
  type AspectRatio,
  type VideoLength,
  type VisualMode,
} from "./types";

interface ProjectDraft {
  topic: string;
  rawScript: string;
  visualMode: VisualMode;
  videoLength: VideoLength;
  language: LanguageCode;
  /** Id from CAPTION_PRESETS — resolved to a full SubtitleStyle on submit. */
  captionPreset: string;
  aspectRatio: AspectRatio;
  /** Id from GET /api/art-styles; ignored for stock footage. */
  artStyle: string;
  /** Piper voice id; empty means "the backend's default for this
   *  language" (see audio_engine.PIPER_VOICE_BY_LANGUAGE). */
  voiceId: string;
  musicEnabled: boolean;
  /** Id from GET /api/music; null means "let the backend use its default". */
  musicTrackId: string | null;
  outroEnabled: boolean;
  outroText: string;
  aiVideoAcknowledged: boolean;
}

interface ShortPulseState {
  draft: ProjectDraft;
  setDraft: (patch: Partial<ProjectDraft>) => void;
  toProjectConfig: () => Partial<ProjectConfig> & { topic: string };

  activeProject: Project | null;
  setActiveProject: (project: Project | null) => void;

  renderProgress: RenderProgress | null;
  setRenderProgress: (progress: RenderProgress | null) => void;

  /** Null until the backend has been asked. `enabled: false` means this
   *  install has no billing at all — see CreditSummary. */
  credits: CreditSummary | null;
  setCredits: (credits: CreditSummary | null) => void;
}

export const useShortPulseStore = create<ShortPulseState>((set, get) => ({
  draft: {
    topic: "",
    rawScript: "",
    visualMode: "fast_hybrid",
    videoLength: "short",
    language: "en",
    captionPreset: DEFAULT_CAPTION_PRESET.id,
    aspectRatio: "9:16",
    artStyle: "photoreal",
    voiceId: "",
    musicEnabled: true,
    musicTrackId: null,
    outroEnabled: false,
    outroText: "",
    aiVideoAcknowledged: false,
  },
  setDraft: (patch) => set((state) => ({ draft: { ...state.draft, ...patch } })),
  toProjectConfig: () => {
    const { draft } = get();
    return {
      topic: draft.topic,
      raw_script: draft.rawScript.trim() ? draft.rawScript : null,
      visual_mode: draft.visualMode,
      art_style: draft.artStyle,
      video_length: draft.videoLength,
      language: draft.language,
      aspect_ratio: draft.aspectRatio,
      fps: 30,
      llm: DEFAULT_LLM_CONFIG,
      // An empty voice_id leaves the choice to the backend, which picks
      // the default Piper voice for `language`.
      voice: { ...DEFAULT_VOICE_CONFIG, voice_id: draft.voiceId },
      subtitles: presetById(draft.captionPreset).style,
      music: {
        ...DEFAULT_MUSIC_CONFIG,
        enabled: draft.musicEnabled,
        track_id: draft.musicTrackId,
      },
      outro: {
        ...DEFAULT_OUTRO_CONFIG,
        enabled: draft.outroEnabled,
        text: draft.outroText.trim() ? draft.outroText : null,
      },
    };
  },

  activeProject: null,
  setActiveProject: (project) => set({ activeProject: project }),

  credits: null,
  setCredits: (credits) => set({ credits }),

  renderProgress: null,
  setRenderProgress: (progress) => set({ renderProgress: progress }),
}));
