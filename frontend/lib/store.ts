import { create } from "zustand";
import { DEFAULT_CAPTION_PRESET, captionStyleFor } from "./captionStyles";
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
  type SubtitleStyle,
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
  /** Where the captions sit and how big they are, applied on top of
   *  whatever the preset chose. Separate from the preset because they are
   *  a different kind of decision: the preset is a look, these two are
   *  placement, and a viewer who wants the words higher does not want a
   *  different font to come with it. */
  captionPosition: SubtitleStyle["position"];
  /** Pixel height at a 1080-wide frame, or null to keep whatever the
   *  preset chose. Absolute rather than a multiplier so the same three
   *  steps mean the same thing here and in the post-render editor, where
   *  there is no preset left to multiply. */
  captionFontSize: number | null;
  aspectRatio: AspectRatio;
  /** Id from GET /api/art-styles; ignored for stock footage. */
  artStyle: string;
  /** Things to keep out of every generated frame, added to what the art
   *  style already excludes. Ignored for stock footage, same as artStyle.
   *  Empty means "just the style's own". */
  negativePrompt: string;
  /** Piper voice id; empty means "the backend's default for this
   *  language" (see audio_engine.PIPER_VOICE_BY_LANGUAGE). */
  voiceId: string;
  musicEnabled: boolean;
  /** Id from GET /api/music; null means "let the backend use its default". */
  musicTrackId: string | null;
  censorProfanity: boolean;
  zoomPunch: boolean;
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
  /** Bumped whenever the finished video is rewritten in place.
   *
   *  final.mp4 keeps its name and the signed URL is a function of the
   *  project id, so nothing about a re-roll or an edit tells the player
   *  that the bytes behind it changed — the media-URL effect only re-runs
   *  on a status change, and status stays "complete". Without this the
   *  user watches the old video and concludes nothing happened, which is
   *  already the behaviour after applying an edit today. */
  videoVersion: number;
  bumpVideoVersion: () => void;

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
    captionPosition: DEFAULT_CAPTION_PRESET.style.position,
    captionFontSize: null,
    aspectRatio: "9:16",
    artStyle: "photoreal",
    negativePrompt: "",
    voiceId: "",
    musicEnabled: true,
    musicTrackId: null,
    censorProfanity: false,
    zoomPunch: true,
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
      negative_prompt: draft.negativePrompt.trim() || null,
      video_length: draft.videoLength,
      language: draft.language,
      aspect_ratio: draft.aspectRatio,
      fps: 30,
      llm: DEFAULT_LLM_CONFIG,
      // An empty voice_id leaves the choice to the backend, which picks
      // the default Piper voice for `language`.
      voice: { ...DEFAULT_VOICE_CONFIG, voice_id: draft.voiceId },
      subtitles: captionStyleFor(draft),
      censor_profanity: draft.censorProfanity,
      zoom_punch: draft.zoomPunch,
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

  videoVersion: 0,
  bumpVideoVersion: () => set((state) => ({ videoVersion: state.videoVersion + 1 })),

  credits: null,
  setCredits: (credits) => set({ credits }),

  renderProgress: null,
  setRenderProgress: (progress) => set({ renderProgress: progress }),
}));
