"use client";

import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { FolderOpen, Loader2, Music, Trash2, Upload } from "lucide-react";
import { useTranslations } from "next-intl";
import { deleteMedia, listMedia, uploadMedia } from "@/lib/api";
import type { MediaFile, MediaList } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { MediaThumb, clockOf, sizeOf } from "@/components/media/MediaPicker";

/**
 * My files: the videos and songs someone has kept, to use again.
 *
 * Kept here by uploading on this page, or by ticking "keep" when uploading
 * for a caption or an edit. Each one can then be picked from the studio
 * instead of uploaded again. Deleting one here does not touch a video
 * already made from it — the project has its own copy.
 */
export default function FilesPage() {
  return (
    <RequireAuth>
      <Files />
    </RequireAuth>
  );
}

const ACCEPT = "video/*,audio/*,.mp3,.wav,.m4a,.aac,.ogg,.flac,.mp4,.mov,.m4v,.webm,.mkv";

function Files() {
  const t = useTranslations("files");
  const input = useRef<HTMLInputElement>(null);
  const [list, setList] = useState<MediaList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState<{ name: string; progress: number } | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  function reload() {
    listMedia()
      .then(setList)
      .catch((err) => setError(err instanceof Error ? err.message : t("loadFailed")));
  }
  useEffect(reload, [t]);

  async function add(files: FileList | File[] | null) {
    if (!files) return;
    setError(null);
    // One at a time: each is a large body, and the quota is checked per
    // file, so the second should see what the first used.
    for (const file of Array.from(files)) {
      setUploading({ name: file.name, progress: 0 });
      try {
        await uploadMedia(file, (progress) => setUploading({ name: file.name, progress }));
      } catch (err) {
        setError(`${file.name}: ${err instanceof Error ? err.message : t("uploadFailed")}`);
      }
    }
    setUploading(null);
    reload();
  }

  async function remove(file: MediaFile) {
    if (confirming !== file.id) {
      setConfirming(file.id);
      return;
    }
    setConfirming(null);
    setList((current) =>
      current
        ? {
            ...current,
            files: current.files.filter((f) => f.id !== file.id),
            used_bytes: current.used_bytes - file.size_bytes,
          }
        : current
    );
    try {
      await deleteMedia(file.id);
    } catch {
      reload();
    }
  }

  const videos = list?.files.filter((f) => f.kind === "video") ?? [];
  const songs = list?.files.filter((f) => f.kind === "audio") ?? [];
  const usedPct = list ? Math.min(100, (list.used_bytes / Math.max(list.quota_bytes, 1)) * 100) : 0;

  return (
    <AppShell section="files" wide>
      <div className="animate-fade-up flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{t("title")}</h1>
          <p className="mt-2 max-w-xl text-sm text-white/50">{t("intro")}</p>
        </div>
        <Button variant="gradient" onClick={() => input.current?.click()} disabled={uploading !== null}>
          {uploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
          {t("upload")}
        </Button>
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            void add(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {list && (
        <div className="mt-5 max-w-sm">
          <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
            <div
              className={clsx("h-full rounded-full", usedPct > 90 ? "bg-red-400" : "bg-accent")}
              style={{ width: `${usedPct}%` }}
            />
          </div>
          <p className="mt-1.5 font-mono text-[11px] text-white/40">
            {t("usage", { used: sizeOf(list.used_bytes), quota: sizeOf(list.quota_bytes) })}
          </p>
        </div>
      )}

      {uploading && (
        <p className="mt-5 flex items-center gap-2 text-xs text-white/60">
          <Loader2 size={13} className="animate-spin" />
          {t("uploading", { name: uploading.name, pct: Math.round(uploading.progress * 100) })}
        </p>
      )}
      {error && (
        <p className="mt-5 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          {error}
        </p>
      )}

      {/* Dropping onto the page works as well as the button. */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void add(e.dataTransfer.files);
        }}
        className={clsx(
          "mt-8 rounded-xl border border-dashed p-1 transition-colors",
          dragging ? "border-accent bg-accent/[0.04]" : "border-transparent"
        )}
      >
        {list === null && !error ? (
          <p className="flex items-center gap-2 p-4 text-sm text-white/40">
            <Loader2 size={14} className="animate-spin" />
            {t("loading")}
          </p>
        ) : list && list.files.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <FolderOpen size={32} className="text-white/20" />
            <p className="text-sm font-medium">{t("emptyTitle")}</p>
            <p className="max-w-sm text-sm text-white/40">{t("emptyBody")}</p>
          </div>
        ) : (
          <div className="flex flex-col gap-10">
            {videos.length > 0 && (
              <section>
                <h2 className="mb-3 text-sm font-medium text-white/70">
                  {t("videos")} <span className="font-mono text-xs text-white/35">{videos.length}</span>
                </h2>
                <div className="grid grid-cols-2 gap-x-4 gap-y-5 sm:grid-cols-4 lg:grid-cols-6">
                  {videos.map((file) => (
                    <figure key={file.id} className="group flex flex-col gap-1.5">
                      <MediaThumb file={file} className="aspect-[9/16] w-full rounded-md border border-border" />
                      <figcaption className="flex items-start gap-1.5">
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-xs">{file.name}</span>
                          <span className="block font-mono text-[10px] text-white/35">
                            {sizeOf(file.size_bytes)}
                            {file.width && file.height ? ` · ${file.width}×${file.height}` : ""}
                          </span>
                        </span>
                        <DeleteButton
                          confirming={confirming === file.id}
                          label={confirming === file.id ? t("confirmDelete") : t("delete")}
                          onClick={() => remove(file)}
                        />
                      </figcaption>
                    </figure>
                  ))}
                </div>
              </section>
            )}
            {songs.length > 0 && (
              <section>
                <h2 className="mb-3 text-sm font-medium text-white/70">
                  {t("songs")} <span className="font-mono text-xs text-white/35">{songs.length}</span>
                </h2>
                <div className="flex max-w-2xl flex-col gap-1.5">
                  {songs.map((file) => (
                    <div
                      key={file.id}
                      className="flex items-center gap-3 rounded-md border border-border bg-surface px-3 py-2 text-xs"
                    >
                      <Music size={14} className="shrink-0 text-white/40" />
                      <span className="min-w-0 flex-1 truncate">{file.name}</span>
                      <span className="shrink-0 font-mono text-[10px] text-white/35">
                        {clockOf(file.duration_s)} · {sizeOf(file.size_bytes)}
                      </span>
                      <DeleteButton
                        confirming={confirming === file.id}
                        label={confirming === file.id ? t("confirmDelete") : t("delete")}
                        onClick={() => remove(file)}
                      />
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}

function DeleteButton({
  confirming,
  label,
  onClick,
}: {
  confirming: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={clsx(
        "shrink-0 rounded p-1 transition-colors",
        confirming ? "bg-red-500/15 text-red-400" : "text-white/30 hover:bg-surface-hover hover:text-red-400"
      )}
    >
      <Trash2 size={13} />
    </button>
  );
}
