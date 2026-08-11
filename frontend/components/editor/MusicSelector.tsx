"use client";

import { useEffect, useState } from "react";
import { Music, VolumeX } from "lucide-react";
import clsx from "clsx";
import { listMusic } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import type { MusicTrack } from "@/lib/types";

/**
 * Background music picker.
 *
 * The list comes from the server rather than being hardcoded, so whatever
 * sits in `backend/app/assets/music` is what's offered — add a file there
 * and it shows up here. Selecting a track sends its id; the path is
 * resolved server-side.
 */
export function MusicSelector() {
  const { draft, setDraft } = useShortPulseStore();
  const [tracks, setTracks] = useState<MusicTrack[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    listMusic()
      .then(setTracks)
      .catch(() => setFailed(true));
  }, []);

  const noneSelected = !draft.musicEnabled;

  return (
    <div className="flex flex-col gap-3">
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
          <span className="text-xs font-medium">No music</span>
        </button>

        {tracks.map((track) => {
          const selected = draft.musicEnabled && draft.musicTrackId === track.id;
          return (
            <button
              key={track.id}
              type="button"
              onClick={() => setDraft({ musicEnabled: true, musicTrackId: track.id })}
              className={clsx(
                "flex items-center gap-2 rounded-lg border px-3 py-2.5 text-left transition-all duration-200",
                selected
                  ? "border-accent bg-accent/10"
                  : "border-border bg-background hover:border-border-strong hover:bg-surface-hover"
              )}
            >
              <Music size={14} className={selected ? "text-accent" : "text-white/40"} />
              <span className="truncate text-xs font-medium">{track.name}</span>
            </button>
          );
        })}
      </div>

      <p className="text-[11px] leading-relaxed text-white/30">
        {failed
          ? "Couldn't reach the music library — the render will fall back to the bundled track."
          : "Music ducks automatically under the voiceover. Drop more files into " +
            "backend/app/assets/music to add to this list."}
      </p>
    </div>
  );
}
