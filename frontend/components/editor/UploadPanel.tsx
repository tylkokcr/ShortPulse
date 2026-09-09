"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Captions, FileVideo, TriangleAlert, Upload } from "lucide-react";
import clsx from "clsx";
import { InsufficientCreditsError, uploadVideo } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { LanguageSelector } from "./LanguageSelector";
import { CaptionStyleSelector } from "./CaptionStyleSelector";
import { UploadPreview } from "./UploadPreview";

/**
 * The second way in: caption a video the user already has.
 *
 * Everything the generate path does before the burn-in has already
 * happened in whatever they shot, so this collects only what the captioner
 * genuinely needs — the file, and the language being spoken (which stops
 * Whisper mis-detecting it on a short clip).
 *
 * Once accepted it becomes an ordinary project, so this hands off to the
 * same project page and the same progress socket.
 */
const MAX_BYTES = 200 * 1024 * 1024;

function formatSize(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return mb >= 1000 ? `${(mb / 1024).toFixed(1)}GB` : `${mb.toFixed(0)}MB`;
}

export function UploadPanel() {
  const router = useRouter();
  const { draft, credits } = useShortPulseStore();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  function choose(next: File | null) {
    setError(null);
    if (!next) return;
    // Checked here as well as on the server so a 200MB upload isn't sent
    // over a phone connection just to be refused at the end of it.
    if (next.size > MAX_BYTES) {
      setError(`That file is ${formatSize(next.size)}. The limit is 200MB.`);
      return;
    }
    setFile(next);
  }

  async function handleUpload() {
    if (!file) return;
    setError(null);
    setProgress(0);
    try {
      const project = await uploadVideo(
        file,
        { language: draft.language, title: file.name.replace(/\.[^.]+$/, "") },
        setProgress
      );
      router.push(`/project/${project.config.id}`);
    } catch (err) {
      setError(
        err instanceof InsufficientCreditsError
          ? `Captioning costs ${err.required} credit${err.required === 1 ? "" : "s"} and you have ${err.balance}.`
          : err instanceof Error
            ? err.message
            : "Upload failed"
      );
      setProgress(null);
    }
  }

  const uploading = progress !== null;

  return (
    // Two columns, matching the generate flow next door. The caption
    // screen used to be a single narrow card in the middle of the page,
    // which made it look like a different product from the studio it
    // shares a tab strip with.
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_280px] lg:items-start">
      <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-5">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            choose(e.dataTransfer.files[0] ?? null);
          }}
          onClick={() => !uploading && inputRef.current?.click()}
          className={clsx(
            "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-md border border-dashed px-6 py-12 text-center transition-colors duration-200",
            dragging
              ? "border-accent bg-accent/5"
              : "border-border-strong hover:border-accent/50 hover:bg-surface-hover",
            uploading && "pointer-events-none opacity-60"
          )}
        >
          <input
            ref={inputRef}
            type="file"
            accept="video/mp4,video/quicktime,video/webm,video/x-matroska"
            className="hidden"
            onChange={(e) => choose(e.target.files?.[0] ?? null)}
          />

          {file ? (
            <>
              <FileVideo size={28} className="text-accent" />
              <div>
                <p className="text-sm font-medium">{file.name}</p>
                <p className="mt-0.5 font-mono text-xs text-white/40">{formatSize(file.size)}</p>
              </div>
              <p className="text-xs text-white/40">Click to pick a different file</p>
            </>
          ) : (
            <>
              <Upload size={28} className="text-white/40" />
              <div>
                <p className="text-sm font-medium">Drop a video here</p>
                <p className="mt-1 text-xs text-white/40">
                  MP4, MOV, WebM or MKV · up to 200MB · needs an audio track
                </p>
              </div>
            </>
          )}
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-white/70">Spoken language</label>
          <LanguageSelector />
          <p className="mt-1.5 text-xs text-white/40">
            Telling it the language up front stops short clips getting mis-detected.
          </p>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-white/70">Caption style</label>
          <CaptionStyleSelector />
        </div>
      </Card>

      {error && (
        <p className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <TriangleAlert size={14} className="mt-0.5 shrink-0" />
          {error}
        </p>
      )}

      {uploading && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between text-xs text-white/50">
            <span>{progress < 1 ? "Uploading..." : "Processing..."}</span>
            <span className="font-mono">{Math.round(progress * 100)}%</span>
          </div>
          <div className="h-1 overflow-hidden bg-border">
            <div
              className="h-full bg-accent transition-[width] duration-200"
              style={{ width: `${Math.max(progress * 100, 2)}%` }}
            />
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-4">
        <p className="flex items-center gap-1.5 text-xs text-white/40">
          <Captions size={13} />
          {credits?.enabled
            ? `1 credit · ${credits.balance} remaining`
            : "Free · runs on this machine"}
        </p>
        <Button onClick={handleUpload} disabled={!file || uploading} variant="gradient">
          {uploading ? (
            "Working..."
          ) : (
            <>
              Add captions
              <ArrowRight size={16} />
            </>
          )}
        </Button>
      </div>
      </div>

      <UploadPreview file={file} />
    </div>
  );
}
