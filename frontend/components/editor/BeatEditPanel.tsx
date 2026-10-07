"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { Film, FolderOpen, Loader2, Music, Pause, Play, Plus, Scissors, Upload, X, Zap } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import {
  createBeatEdit,
  InsufficientCreditsError,
  listMusic,
  musicPreviewUrl,
  type BeatEditStyle,
} from "@/lib/api";
import type { MediaFile, MusicTrack } from "@/lib/types";
import { MediaPicker, clockOf } from "@/components/media/MediaPicker";
import { useShortPulseStore } from "@/lib/store";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

/**
 * Cut your own clips to a track.
 *
 * Everything here is the user's: the clips they drop in and, if they
 * bring one, the song. Nothing is searched for or fetched on their
 * behalf — see backend/app/engines/beat_edit.py for why that line is
 * where it is. The notice under the file list says the same thing to the
 * person choosing the files.
 *
 * The rest is decided for them and can be overruled: the stretch of the
 * song is chosen around its drop, the busiest moment of each clip is the
 * one used, and the cuts land on the beat.
 */
const MAX_CLIPS = 12;
const DURATIONS = [10, 15, 30, 60] as const;
const STYLES: { id: BeatEditStyle; icon: typeof Zap }[] = [
  { id: "energetic", icon: Zap },
  { id: "cinematic", icon: Film },
  { id: "calm", icon: Music },
];
const VIDEO_TYPES = "video/mp4,video/quicktime,video/webm,video/x-matroska";
const AUDIO_TYPES = "audio/mpeg,audio/wav,audio/x-wav,audio/mp4,audio/aac,audio/ogg,audio/flac,.mp3,.wav,.m4a,.aac,.ogg,.flac";

export function BeatEditPanel() {
  const t = useTranslations("studio.beat");
  const tf = useTranslations("files");
  const router = useRouter();
  const credits = useShortPulseStore((s) => s.credits);
  const clipInput = useRef<HTMLInputElement>(null);
  const musicInput = useRef<HTMLInputElement>(null);

  const [clips, setClips] = useState<File[]>([]);
  // Clips and a song already in My files: sent as ids, never uploaded.
  const [pickedClips, setPickedClips] = useState<MediaFile[]>([]);
  const [pickedSong, setPickedSong] = useState<MediaFile | null>(null);
  const [picking, setPicking] = useState<"video" | "audio" | null>(null);
  // On by default: someone cutting clips to a song is likely to want them
  // again, and re-uploading them is the cost this exists to remove.
  const [keep, setKeep] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [musicSource, setMusicSource] = useState<"library" | "own">("library");
  const [tracks, setTracks] = useState<MusicTrack[]>([]);
  const [trackId, setTrackId] = useState<string>("");
  const [musicFile, setMusicFile] = useState<File | null>(null);
  const [duration, setDuration] = useState<number>(15);
  const [style, setStyle] = useState<BeatEditStyle>("energetic");
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    listMusic()
      .then((all) => {
        // Upbeat first: a cut on the beat wants something with one.
        const ordered = [...all].sort(
          (a, b) => Number(b.category === "upbeat") - Number(a.category === "upbeat")
        );
        setTracks(ordered);
        setTrackId((current) => current || ordered[0]?.id || "");
      })
      .catch(() => setTracks([]));
  }, []);
  useEffect(() => () => audioRef.current?.pause(), []);

  function addClips(files: FileList | File[] | null) {
    if (!files) return;
    const videos = Array.from(files).filter((f) => f.type.startsWith("video/") || /\.(mp4|mov|m4v|webm|mkv)$/i.test(f.name));
    setClips((current) => [...current, ...videos].slice(0, MAX_CLIPS - pickedClips.length));
    setError(null);
  }

  function audition(id: string) {
    if (playing === id) {
      audioRef.current?.pause();
      setPlaying(null);
      return;
    }
    audioRef.current?.pause();
    const audio = new Audio(musicPreviewUrl(id));
    audioRef.current = audio;
    audio.onended = () => setPlaying(null);
    audio.onerror = () => setPlaying(null);
    audio.play().then(() => setPlaying(id)).catch(() => setPlaying(null));
  }

  const hasMusic =
    musicSource === "library" ? Boolean(trackId) : Boolean(musicFile || pickedSong);
  const clipCount = clips.length + pickedClips.length;
  const ready = clipCount > 0 && hasMusic && progress === null;
  const price = credits?.enabled ? (credits.pricing?.["beat_edit"] ?? 1) : null;

  async function submit() {
    if (!ready) return;
    setError(null);
    setProgress(0);
    audioRef.current?.pause();
    try {
      const project = await createBeatEdit(
        clips,
        {
          musicTrackId: musicSource === "library" ? trackId : undefined,
          musicFile: musicSource === "own" && !pickedSong ? (musicFile ?? undefined) : undefined,
          musicMediaId: musicSource === "own" ? pickedSong?.id : undefined,
          clipMediaIds: pickedClips.map((f) => f.id),
          saveToFiles: keep,
          durationS: duration,
          style,
          title: (pickedClips[0]?.name ?? clips[0]?.name ?? "").replace(/\.[^.]+$/, ""),
        },
        setProgress
      );
      router.push(`/project/${project.config.id}`);
    } catch (err) {
      setProgress(null);
      if (err instanceof InsufficientCreditsError) setError(t("errors.credits"));
      else setError(err instanceof Error ? err.message : t("errors.generic"));
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_280px] lg:items-start">
      <Card className="flex flex-col gap-6">
        {/* The clips. */}
        <div>
          <span className="mb-1.5 block text-sm font-medium text-white/70">{t("clips")}</span>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              addClips(e.dataTransfer.files);
            }}
            onClick={() => clipInput.current?.click()}
            className={clsx(
              "flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed px-4 py-7 text-center transition-colors",
              dragging ? "border-accent bg-accent/[0.06]" : "border-border-strong hover:border-white/30"
            )}
          >
            <Upload size={18} className="text-white/50" />
            <span className="text-sm font-medium">{t("drop")}</span>
            <span className="text-xs text-white/40">{t("dropHint", { max: MAX_CLIPS })}</span>
            <input
              ref={clipInput}
              type="file"
              accept={VIDEO_TYPES}
              multiple
              className="hidden"
              onChange={(e) => {
                addClips(e.target.files);
                e.target.value = "";
              }}
            />
          </div>
          <button
            type="button"
            onClick={() => setPicking("video")}
            className="mt-2 flex items-center gap-1.5 px-1 py-1 text-xs text-white/55 hover:text-white"
          >
            <FolderOpen size={13} />
            {tf("fromFiles")}
          </button>
          {clipCount > 0 && (
            <ul className="mt-3 flex flex-col gap-1.5">
              {pickedClips.map((file) => (
                <li
                  key={file.id}
                  className="flex items-center gap-2.5 rounded-md border border-border bg-surface px-3 py-2 text-xs"
                >
                  <FolderOpen size={13} className="shrink-0 text-accent/70" />
                  <span className="min-w-0 flex-1 truncate">{file.name}</span>
                  <span className="shrink-0 font-mono text-[10px] text-white/35">{clockOf(file.duration_s)}</span>
                  <button
                    type="button"
                    aria-label={t("remove")}
                    onClick={() => setPickedClips((current) => current.filter((f) => f.id !== file.id))}
                    className="shrink-0 rounded p-0.5 text-white/35 hover:bg-surface-hover hover:text-white/80"
                  >
                    <X size={13} />
                  </button>
                </li>
              ))}
              {clips.map((clip, i) => (
                <li
                  key={`${clip.name}-${i}`}
                  className="flex items-center gap-2.5 rounded-md border border-border bg-surface px-3 py-2 text-xs"
                >
                  <Film size={13} className="shrink-0 text-white/40" />
                  <span className="min-w-0 flex-1 truncate">{clip.name}</span>
                  <span className="shrink-0 font-mono text-[10px] text-white/35">
                    {(clip.size / (1024 * 1024)).toFixed(1)}MB
                  </span>
                  <button
                    type="button"
                    aria-label={t("remove")}
                    onClick={() => setClips((current) => current.filter((_, k) => k !== i))}
                    className="shrink-0 rounded p-0.5 text-white/35 hover:bg-surface-hover hover:text-white/80"
                  >
                    <X size={13} />
                  </button>
                </li>
              ))}
              {clipCount < MAX_CLIPS && (
                <li>
                  <button
                    type="button"
                    onClick={() => clipInput.current?.click()}
                    className="flex items-center gap-1.5 px-1 py-1 text-xs text-white/45 hover:text-white/80"
                  >
                    <Plus size={13} />
                    {t("addMore")}
                  </button>
                </li>
              )}
            </ul>
          )}
          <p className="mt-2 text-xs text-white/35">{t("rights")}</p>
        </div>

        {/* The music. */}
        <div>
          <span className="mb-1.5 block text-sm font-medium text-white/70">{t("music")}</span>
          <div className="mb-3 inline-flex rounded-md border border-border bg-surface p-0.5">
            {(["library", "own"] as const).map((source) => (
              <button
                key={source}
                type="button"
                onClick={() => setMusicSource(source)}
                aria-pressed={musicSource === source}
                className={clsx(
                  "rounded px-3 py-1.5 text-xs font-medium transition-colors",
                  musicSource === source ? "bg-surface-raised text-white" : "text-white/50 hover:text-white/80"
                )}
              >
                {t(`musicSource.${source}`)}
              </button>
            ))}
          </div>
          {musicSource === "library" ? (
            <div className="flex max-h-56 flex-col gap-1 overflow-y-auto pr-1">
              {tracks.map((track) => {
                const selected = trackId === track.id;
                return (
                  <div
                    key={track.id}
                    className={clsx(
                      "flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs transition-colors",
                      selected ? "border-accent/60 bg-accent/[0.08]" : "border-border hover:border-border-strong"
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => audition(track.id)}
                      aria-label={t("preview")}
                      className="shrink-0 rounded p-1 text-white/50 hover:text-white"
                    >
                      {playing === track.id ? <Pause size={12} /> : <Play size={12} />}
                    </button>
                    <button
                      type="button"
                      onClick={() => setTrackId(track.id)}
                      className="min-w-0 flex-1 truncate text-left"
                    >
                      {track.name}
                    </button>
                    {track.category && (
                      <span className="shrink-0 font-mono text-[10px] text-white/30">{track.category}</span>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <button
                  type="button"
                  onClick={() => musicInput.current?.click()}
                  className="flex min-w-0 flex-1 items-center gap-2.5 rounded-md border border-dashed border-border-strong px-3 py-3 text-left text-xs hover:border-white/30"
                >
                  <Music size={14} className="shrink-0 text-white/50" />
                  <span className="min-w-0 flex-1 truncate">
                    {pickedSong ? pickedSong.name : musicFile ? musicFile.name : t("pickSong")}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => setPicking("audio")}
                  className="flex shrink-0 items-center justify-center gap-1.5 rounded-md border border-border px-3 py-3 text-xs text-white/60 hover:border-border-strong hover:text-white"
                >
                  <FolderOpen size={13} />
                  {tf("fromFiles")}
                </button>
              </div>
              <input
                ref={musicInput}
                type="file"
                accept={AUDIO_TYPES}
                className="hidden"
                onChange={(e) => {
                  setMusicFile(e.target.files?.[0] ?? null);
                  setPickedSong(null);
                }}
              />
              <p className="mt-2 text-xs text-white/35">{t("ownSongNotice")}</p>
            </div>
          )}
          <p className="mt-2 text-xs text-white/40">{t("musicHint")}</p>
        </div>

        {/* Length and style. */}
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <div>
            <span className="mb-1.5 block text-sm font-medium text-white/70">{t("length")}</span>
            <div className="flex gap-2">
              {DURATIONS.map((seconds) => (
                <button
                  key={seconds}
                  type="button"
                  onClick={() => setDuration(seconds)}
                  aria-pressed={duration === seconds}
                  className={clsx(
                    "rounded-lg border px-3 py-1.5 text-xs transition-colors",
                    duration === seconds
                      ? "border-accent/60 bg-accent/[0.08] text-white"
                      : "border-border text-white/50 hover:border-border-strong"
                  )}
                >
                  {seconds}s
                </button>
              ))}
            </div>
          </div>
          <div>
            <span className="mb-1.5 block text-sm font-medium text-white/70">{t("style")}</span>
            <div className="flex flex-wrap gap-2">
              {STYLES.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => setStyle(option.id)}
                  aria-pressed={style === option.id}
                  className={clsx(
                    "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-colors",
                    style === option.id
                      ? "border-accent/60 bg-accent/[0.08] text-white"
                      : "border-border text-white/50 hover:border-border-strong"
                  )}
                >
                  <option.icon size={12} />
                  {t(`styles.${option.id}.name`)}
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-white/40">{t(`styles.${style}.hint`)}</p>
          </div>
        </div>

        {/* Only matters for what is being uploaded now; files picked from
            My files are there already. */}
        {(clips.length > 0 || (musicSource === "own" && musicFile && !pickedSong)) && (
          <label className="flex cursor-pointer items-start gap-2.5 text-xs">
            <input
              type="checkbox"
              checked={keep}
              onChange={(e) => setKeep(e.target.checked)}
              className="mt-0.5 accent-[rgb(var(--accent))]"
            />
            <span>
              <span className="text-white/80">{tf("keep")}</span>
              <span className="block text-white/40">{tf("keepHint")}</span>
            </span>
          </label>
        )}

        {error && (
          <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">
            {error}
          </p>
        )}

        <div className="flex items-center justify-between gap-3 border-t border-border pt-4">
          <span className="text-xs text-white/40">
            {price !== null ? t("price", { credits: price }) : t("free")}
          </span>
          <Button onClick={submit} disabled={!ready} variant="gradient">
            {progress !== null ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                {progress < 1 ? t("uploading", { pct: Math.round(progress * 100) }) : t("starting")}
              </>
            ) : (
              <>
                <Scissors size={14} />
                {t("cta")}
              </>
            )}
          </Button>
        </div>
      </Card>

      <MediaPicker
        open={picking !== null}
        kind={picking ?? "video"}
        multiple={picking === "video"}
        exclude={pickedClips.map((f) => f.id)}
        onClose={() => setPicking(null)}
        onPick={(files) => {
          if (picking === "audio") {
            setPickedSong(files[0] ?? null);
            setMusicFile(null);
          } else {
            setPickedClips((current) =>
              [...current, ...files].slice(0, MAX_CLIPS - clips.length)
            );
          }
        }}
      />

      {/* What it will do, in order — the decisions it makes on its own. */}
      <Card className="flex flex-col gap-3 bg-surface-raised lg:sticky lg:top-6">
        <span className="text-sm font-medium text-white/70">{t("how.title")}</span>
        <ol className="flex flex-col gap-2.5 text-xs leading-relaxed text-white/50">
          {(["beat", "moments", "drop", "effects"] as const).map((step, i) => (
            <li key={step} className="flex gap-2.5">
              <span className="mt-px font-mono text-[10px] text-accent">0{i + 1}</span>
              <span>{t(`how.${step}`)}</span>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
