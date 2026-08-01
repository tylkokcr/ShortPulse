import { create } from "zustand";
import {
  DEFAULT_LLM_CONFIG,
  DEFAULT_MUSIC_CONFIG,
  DEFAULT_OUTRO_CONFIG,
  DEFAULT_SUBTITLE_STYLE,
  DEFAULT_VOICE_CONFIG,
  LANGUAGE_OPTIONS,
  type LanguageCode,
  type Project,
  type ProjectConfig,
  type RenderProgress,
  type VideoLength,
  type VisualMode,
} from "./types";

interface ProjectDraft {
  topic: string;
  rawScript: string;
  visualMode: VisualMode;
  videoLength: VideoLength;
  language: LanguageCode;
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
}

export const useShortPulseStore = create<ShortPulseState>((set, get) => ({
  draft: {
    topic: "",
    rawScript: "",
    visualMode: "fast_hybrid",
    videoLength: "short",
    language: "en",
    outroEnabled: false,
    outroText: "",
    aiVideoAcknowledged: false,
  },
  setDraft: (patch) => set((state) => ({ draft: { ...state.draft, ...patch } })),
  toProjectConfig: () => {
    const { draft } = get();
    const languageOption = LANGUAGE_OPTIONS.find((l) => l.code === draft.language) ?? LANGUAGE_OPTIONS[0];
    return {
      topic: draft.topic,
      raw_script: draft.rawScript.trim() ? draft.rawScript : null,
      visual_mode: draft.visualMode,
      video_length: draft.videoLength,
      language: draft.language,
      aspect_ratio: "9:16",
      fps: 30,
      llm: DEFAULT_LLM_CONFIG,
      voice: { ...DEFAULT_VOICE_CONFIG, voice_id: languageOption.voiceId },
      subtitles: DEFAULT_SUBTITLE_STYLE,
      music: DEFAULT_MUSIC_CONFIG,
      outro: {
        ...DEFAULT_OUTRO_CONFIG,
        enabled: draft.outroEnabled,
        text: draft.outroText.trim() ? draft.outroText : null,
      },
    };
  },

  activeProject: null,
  setActiveProject: (project) => set({ activeProject: project }),

  renderProgress: null,
  setRenderProgress: (progress) => set({ renderProgress: progress }),
}));
