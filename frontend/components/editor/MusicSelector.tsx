"use client";

import { useEffect, useRef, useState } from "react";
import { Music, Pause, Play, VolumeX } from "lucide-react";
import { useTranslations } from "next-intl";
import clsx from "clsx";
import { listMusic, musicPreviewUrl } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import type { MusicTrack } from "@/lib/types";

/**
 * Background music picker.
 *
 * The list comes from the server rather than being hardcoded, so whatever
 * sits in `backend/app/assets/music` is what's offered — add a file there
 * and it shows up here. Selecting a track sends its id; the path is
 * resolved server-side.
 *
 * Auditioning matters more here than anywhere else in the editor. Every
 * other setting can be described — a language, an aspect ratio, an art
 * style with a sample image — and "Airport Lounge" describes nothing at
 * all. A list of filenames is not a choice, which is also why adding more
 * of them was only worth doing alongside a way to hear them.
 */
/** Folder names are ids; the translations are what a person reads.
 *  Anything not listed falls back to the folder name, so adding a mood
 *  needs no code change — only a message key if you want a nicer label. */
const CATEGORY_KEYS = ["lofi", "upbeat", "atmospheric", "suspense"] as const;

export function MusicSelector() {
  const t = useTranslations("studio.music");
  const { draft, setDraft } = useShortPulseStore();

  // "" is the bundled folder, and an unrecognised folder keeps its own
  // name rather than being labelled "Other" in the wrong language.
  const moodLabel = (category: string) => {
    if (category === "") return t("moods.bundled");
    return (CATEGORY_KEYS as readonly string[]).includes(category)
      ? t(`moods.${category}`)
      : category;
  };
  const [tracks, setTracks] = useState<MusicTrack[]>([]);
  const [failed, setFailed] = useState(false);
  const [playing, setPlaying] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    listMusic()
      .then(setTracks)
      .catch(() => setFailed(true));
  }, []);

  // Otherwise a preview keeps playing under a collapsed section, or over
  // the render that started while it was still going.
  useEffect(() => () => audioRef.current?.pause(), []);

  function audition(trackId: string) {
    if (playing === trackId) {
      audioRef.current?.pause();
      setPlaying(null);
      return;
    }
    audioRef.current?.pause();
    const audio = new Audio(musicPreviewUrl(trackId));
    audioRef.current = audio;
    audio.onended = () => setPlaying(null);
    audio.onerror = () => setPlaying(null);
    audio.play().then(() => setPlaying(trackId)).catch(() => setPlaying(null));
  }

  const noneSelected = !draft.musicEnabled;

  // Grouped by the mood folder the file came from. Forty tracks in one
  // flat grid is a wall, not a choice — and the grouping costs nothing to
  // maintain because it *is* the directory layout.
  const groups = new Map<string, MusicTrack[]>();
  for (const track of tracks) {
    const key = track.category ?? "";
    groups.set(key, [...(groups.get(key) ?? []), track]);
  }
  // Uncategorised last: that is where the bundled default sits, and it is
  // the least interesting thing in the list once there are alternatives.
  const ordered = [...groups.entries()].sort(([a], [b]) =>
    a === "" ? 1 : b === "" ? -1 : a.localeCompare(b)
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <button
          type="button"
          onClick={() => setDraft({ musicEnabled: false, musicTrackId: null })}
          className={clsx(
            "flex items-center gap-2 rounded-lg border px-3 py-2.5 text-left transition-all duration-200",
            noneSelected
              ? "border-accent bg-accent/10"
              : "border-border bg-background hover:border-border-strong hover:bg-surface-hover"
          )}
        >
          <VolumeX size={14} className={noneSelected ? "text-accent" : "text-white/40"} />
          <span className="text-xs font-medium">{t("none")}</span>
        </button>
      </div>

      {ordered.map(([category, inGroup]) => (
        <div key={category || "other"} className="flex flex-col gap-2">
          <span className="font-mono text-[10px] uppercase tracking-widest text-white/25">
            {moodLabel(category)}
          </span>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {inGroup.map((track) => {
          const selected = draft.musicEnabled && draft.musicTrackId === track.id;
          return (
            <div
              key={track.id}
              className={clsx(
                "flex items-center gap-1 rounded-lg border pr-1 transition-all duration-200",
                selected
                  ? "border-accent bg-accent/10"
                  : "border-border bg-background hover:border-border-strong hover:bg-surface-hover"
              )}
            >
              <button
                type="button"
                onClick={() => setDraft({ musicEnabled: true, musicTrackId: track.id })}
                className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2.5 text-left"
              >
                <Music size={14} className={selected ? "text-accent" : "text-white/40"} />
                <span className="truncate text-xs font-medium">{track.name}</span>
              </button>

              {/* Its own control, not a click on the tile: hearing a track
                  and choosing it are different intentions, and making the
                  first imply the second means you cannot listen to two. */}
              <button
                type="button"
                onClick={() => audition(track.id)}
                aria-label={
                  playing === track.id
                    ? t("stop", { name: track.name })
                    : t("play", { name: track.name })
                }
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-white/40 transition-colors hover:bg-surface-hover hover:text-white/80"
              >
                {playing === track.id ? <Pause size={12} /> : <Play size={12} />}
              </button>
            </div>
          );
        })}
          </div>
        </div>
      ))}

      <p className="text-[11px] leading-relaxed text-white/30">
        {failed
          ? t("failed")
          : t("hint")}
      </p>
    </div>
  );
}
