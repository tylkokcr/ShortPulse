"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import clsx from "clsx";
import { Check, FolderOpen, Loader2, Music, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { getMediaUrls, listMedia } from "@/lib/api";
import type { MediaFile } from "@/lib/types";
import { Button } from "@/components/ui/Button";

/** m:ss for a file's length. */
export function clockOf(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return "";
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function sizeOf(bytes: number): string {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 ** 3).toFixed(1)}GB`;
  return `${Math.max(0.1, bytes / 1024 ** 2).toFixed(1)}MB`;
}

/**
 * A file's still, or a note for a song. The poster is behind a signed URL
 * like a project's, so it is asked for once per thumbnail.
 */
export function MediaThumb({ file, className }: { file: MediaFile; className?: string }) {
  const [poster, setPoster] = useState<string | null>(null);
  useEffect(() => {
    if (file.kind !== "video") return;
    let live = true;
    getMediaUrls(file.id)
      .then((urls) => live && setPoster(urls.poster_url))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [file.id, file.kind]);

  return (
    <div className={clsx("relative overflow-hidden bg-black/50", className)}>
      {file.kind === "video" && poster ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={poster} alt="" className="h-full w-full object-cover" />
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          <Music size={18} className="text-white/30" />
        </div>
      )}
      {file.duration_s !== null && (
        <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 font-mono text-[9px] text-white/80">
          {clockOf(file.duration_s)}
        </span>
      )}
    </div>
  );
}

/**
 * Choose from My files without uploading again.
 *
 * A modal rather than a page: the person is in the middle of setting up a
 * video and only wants to point at a file. Portalled to the body for the
 * reason the settings drawer is — a transformed ancestor would otherwise
 * pin it to the card it was opened from.
 */
type PickerProps = {
  kind: "video" | "audio";
  multiple?: boolean;
  /** Already chosen — not offered again. */
  exclude?: string[];
  onClose: () => void;
  onPick: (files: MediaFile[]) => void;
};

export function MediaPicker({ open, ...props }: PickerProps & { open: boolean }) {
  // Mounted only while open, so every opening starts from a fresh list
  // and an empty selection.
  if (!open || typeof document === "undefined") return null;
  return <PickerBody {...props} />;
}

function PickerBody({ kind, multiple = false, exclude = [], onClose, onPick }: PickerProps) {
  const t = useTranslations("files");
  const [files, setFiles] = useState<MediaFile[] | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);

  useEffect(() => {
    let live = true;
    listMedia()
      .then((list) =>
        live && setFiles(list.files.filter((f) => f.kind === kind && !exclude.includes(f.id)))
      )
      .catch(() => live && setFiles([]));
    return () => {
      live = false;
    };
    // `exclude` is read when the picker opens; changing it while open
    // would reshuffle the grid under the pointer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind]);

  useEffect(() => {
    const close = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);

  function toggle(file: MediaFile) {
    if (!multiple) {
      onPick([file]);
      onClose();
      return;
    }
    setChosen((current) =>
      current.includes(file.id) ? current.filter((id) => id !== file.id) : [...current, file.id]
    );
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-6">
      <button type="button" aria-label={t("close")} onClick={onClose} className="absolute inset-0 cursor-default" />
      <div
        role="dialog"
        aria-modal
        aria-label={t(kind === "video" ? "pickVideos" : "pickSong")}
        className="relative flex max-h-[85vh] w-full max-w-3xl flex-col rounded-t-xl border border-border bg-surface-raised sm:rounded-xl"
      >
        <div className="flex items-center gap-2 border-b border-border px-5 py-3.5">
          <FolderOpen size={15} className="text-accent" />
          <span className="flex-1 text-sm font-medium">{t(kind === "video" ? "pickVideos" : "pickSong")}</span>
          <button type="button" onClick={onClose} aria-label={t("close")} className="rounded p-1 text-white/40 hover:text-white">
            <X size={16} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          {files === null ? (
            <p className="flex items-center gap-2 text-sm text-white/40">
              <Loader2 size={14} className="animate-spin" />
              {t("loading")}
            </p>
          ) : files.length === 0 ? (
            <p className="text-sm text-white/40">{t(kind === "video" ? "noVideos" : "noSongs")}</p>
          ) : (
            <div className={clsx("grid gap-3", kind === "video" ? "grid-cols-3 sm:grid-cols-4" : "grid-cols-1")}>
              {files.map((file) => {
                const on = chosen.includes(file.id);
                return (
                  <button
                    key={file.id}
                    type="button"
                    onClick={() => toggle(file)}
                    className={clsx(
                      "group relative flex text-left transition-colors",
                      kind === "video" ? "flex-col gap-1.5" : "items-center gap-3 rounded-md border px-3 py-2",
                      kind === "audio" && (on ? "border-accent/60 bg-accent/[0.08]" : "border-border hover:border-border-strong")
                    )}
                  >
                    {kind === "video" ? (
                      <MediaThumb
                        file={file}
                        className={clsx(
                          "aspect-[9/16] w-full rounded-md border transition-colors",
                          on ? "border-accent ring-2 ring-accent/40" : "border-border group-hover:border-border-strong"
                        )}
                      />
                    ) : (
                      <Music size={14} className="shrink-0 text-white/40" />
                    )}
                    <span className="min-w-0 truncate text-[11px] text-white/70">{file.name}</span>
                    {kind === "audio" && (
                      <span className="ml-auto shrink-0 font-mono text-[10px] text-white/35">{clockOf(file.duration_s)}</span>
                    )}
                    {on && kind === "video" && (
                      <span className="absolute right-1.5 top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-accent text-black">
                        <Check size={12} />
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {multiple && (
          <div className="flex items-center justify-between gap-3 border-t border-border px-5 py-3">
            <span className="text-xs text-white/40">{t("chosen", { count: chosen.length })}</span>
            <Button
              size="sm"
              variant="gradient"
              disabled={chosen.length === 0}
              onClick={() => {
                onPick((files ?? []).filter((f) => chosen.includes(f.id)));
                onClose();
              }}
            >
              {t("useThese")}
            </Button>
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}
