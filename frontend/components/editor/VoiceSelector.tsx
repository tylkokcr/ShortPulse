"use client";

import { useEffect, useRef, useState } from "react";
import { Play, Pause, Loader2, Check } from "lucide-react";
import { useTranslations } from "next-intl";
import clsx from "clsx";
import { listVoices, voicePreviewUrl } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import type { Voice } from "@/lib/types";

/**
 * Voice picker for the chosen language.
 *
 * Piper publishes no gender or tone for its voices, so rather than
 * inventing adjectives this shows what the catalog does record — speaker
 * name, region, quality — and lets you hear the thing itself. The first
 * preview of a voice downloads its model server-side, which is why a slow
 * one says so instead of looking broken.
 */
export function VoiceSelector() {
  const t = useTranslations("studio.voice");
  const { draft, setDraft } = useShortPulseStore();
  const [voices, setVoices] = useState<Voice[]>([]);
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState<string | null>(null);
  const [buffering, setBuffering] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listVoices(draft.language)
      .then((list) => {
        if (cancelled) return;
        setVoices(list);
        // The catalog is per-language, so a voice chosen for the previous
        // language is meaningless here — fall back to that language's
        // default rather than sending an id the backend would reject.
        if (!list.some((voice) => voice.id === draft.voiceId)) {
          setDraft({ voiceId: "" });
        }
      })
      .catch(() => !cancelled && setVoices([]))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.language]);

  // Stop playback when this unmounts (the section collapses), otherwise a
  // preview keeps talking over a collapsed panel.
  useEffect(() => {
    return () => audioRef.current?.pause();
  }, []);

  function togglePreview(voice: Voice) {
    if (playing === voice.id) {
      audioRef.current?.pause();
      setPlaying(null);
      return;
    }

    audioRef.current?.pause();
    const audio = new Audio(voicePreviewUrl(voice.id));
    audioRef.current = audio;
    setBuffering(voice.id);
    setFailed(null);

    audio.onplaying = () => {
      setBuffering(null);
      setPlaying(voice.id);
    };
    audio.onended = () => setPlaying(null);
    audio.onerror = () => {
      setBuffering(null);
      setPlaying(null);
      setFailed(voice.id);
    };
    audio.play().catch(() => {
      setBuffering(null);
      setFailed(voice.id);
    });
  }

  if (loading) {
    return (
      <p className="flex items-center gap-2 text-xs text-white/40">
        <Loader2 size={13} className="animate-spin" />
        {t("loading")}
      </p>
    );
  }

  if (voices.length === 0) {
    return (
      <p className="text-xs text-white/40">
        {t("listFailed")}
      </p>
    );
  }

  const selectedId = draft.voiceId || voices.find((voice) => voice.is_default)?.id;

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {voices.map((voice) => {
          const selected = voice.id === selectedId;
          return (
            <div
              key={voice.id}
              className={clsx(
                "flex items-center gap-2 rounded-lg border px-3 py-2.5 transition-all duration-200",
                selected
                  ? "border-accent bg-accent/10"
                  : "border-border bg-background hover:border-border-strong hover:bg-surface-hover"
              )}
            >
              <button
                type="button"
                onClick={() => togglePreview(voice)}
                aria-label={`Preview ${voice.name}`}
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-surface text-white/70 transition-colors hover:border-accent hover:text-white"
              >
                {buffering === voice.id ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : playing === voice.id ? (
                  <Pause size={12} />
                ) : (
                  <Play size={12} className="translate-x-[1px]" />
                )}
              </button>

              <button
                type="button"
                onClick={() => setDraft({ voiceId: voice.id })}
                className="min-w-0 flex-1 text-left"
              >
                <span className="flex items-center gap-1.5">
                  <span className="truncate text-xs font-medium">{voice.name}</span>
                  {selected && <Check size={12} className="shrink-0 text-accent" />}
                </span>
                <span className="block truncate text-[11px] text-white/40">
                  {voice.region} · {voice.quality}
                  {voice.is_default ? t("default") : ""}
                </span>
              </button>
            </div>
          );
        })}
      </div>

      <p className="text-[11px] leading-relaxed text-white/30">
        {failed
          ? t("failed")
          : t("hint")}
      </p>
    </div>
  );
}
