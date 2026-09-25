"use client";

import { useRef, useState } from "react";
import { ArrowRight, Captions, FileVideo, TriangleAlert, Upload } from "lucide-react";
import { useTranslations } from "next-intl";
import clsx from "clsx";
import { useRouter } from "@/i18n/navigation";
import { InsufficientCreditsError, uploadVideo } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import { LANGUAGE_OPTIONS } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { LanguageSelector } from "./LanguageSelector";
import { CaptionStyleSelector } from "./CaptionStyleSelector";
import { CensorToggle } from "./CensorToggle";
import { presetById } from "@/lib/captionStyles";
import { UploadPreview } from "./UploadPreview";

/**
 * The second way in: caption — or dub — a video the user already has.
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
  const t = useTranslations("studio.upload");
  // The credit line and the free-install line are shared with the
  // generate tab, so they live one level up rather than twice.
  const ts = useTranslations("studio");
  const router = useRouter();
  const { draft, credits } = useShortPulseStore();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Local rather than in the draft store: the target language is a
  // property of this one action, not of a project that outlives it.
  const [dubLanguage, setDubLanguage] = useState("");
  const [censor, setCensor] = useState(false);
  // Zero means "caption it whole". The two are mutually exclusive — the
  // API refuses both together rather than quietly doing one — so choosing
  // either clears the other here instead of letting the server say no
  // after the file has been uploaded.
  const [clipCount, setClipCount] = useState(0);

  // Quoted from the table the API serves, which is the one the backend
  // charges from — the panel used to print "1 credit" whatever was
  // chosen, which was wrong about a dub and about every clip count.
  const unit = clipCount ? "upload:clip" : dubLanguage ? "upload:dub" : "upload:caption";
  const price = (credits?.pricing?.[unit] ?? 1) * (clipCount || 1);

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
        {
          language: draft.language,
          title: file.name.replace(/\.[^.]+$/, ""),
          dubLanguage,
          clipCount,
          // The picker below has been on this panel from the start; what
          // was missing was this line, so every upload came back Classic
          // whatever was chosen.
          subtitles: presetById(draft.captionPreset).style,
          censorProfanity: censor,
        },
        setProgress
      );
      router.push(`/project/${project.config.id}`);
    } catch (err) {
      setError(
        err instanceof InsufficientCreditsError
          ? t("errors.insufficient", {
              what: t(clipCount ? "errors.clips" : dubLanguage ? "errors.dub" : "errors.caption"),
              required: err.required,
              balance: err.balance,
            })
          : err instanceof Error
            ? err.message
            : t("errors.failed")
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
              <p className="text-xs text-white/40">{t("pickAnother")}</p>
            </>
          ) : (
            <>
              <Upload size={28} className="text-white/40" />
              <div>
                <p className="text-sm font-medium">{t("dropTitle")}</p>
                <p className="mt-1 text-xs text-white/40">{t("dropHint")}</p>
              </div>
            </>
          )}
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-white/70">{t("spokenLanguage")}</label>
          <LanguageSelector />
          <p className="mt-1.5 text-xs text-white/40">{t("spokenLanguageHint")}</p>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-white/70">{t("clips")}</label>
          <div className="flex flex-wrap gap-2">
            {[0, 2, 3, 4, 5].map((count) => (
              <button
                key={count}
                type="button"
                onClick={() => {
                  setClipCount(count);
                  if (count) setDubLanguage("");
                }}
                className={clsx(
                  "rounded-lg border px-3 py-1.5 text-xs transition-colors duration-200",
                  clipCount === count
                    ? "border-accent/60 bg-accent/[0.08] text-white"
                    : "border-border text-white/50 hover:border-border-strong hover:text-white/80"
                )}
              >
                {count === 0 ? t("clipsNone") : t("clipsCount", { count })}
              </button>
            ))}
          </div>
          <p className="mt-1.5 text-xs text-white/40">
            {clipCount ? t("clipsOnHint") : t("clipsOffHint")}
          </p>
        </div>

        <div className={clsx(clipCount && "pointer-events-none opacity-40")}>
          <label
            htmlFor="dub-language"
            className="mb-1.5 block text-sm font-medium text-white/70"
          >
            {t("dub")}
          </label>
          <select
            id="dub-language"
            value={dubLanguage}
            onChange={(event) => setDubLanguage(event.target.value)}
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-white outline-none transition-colors hover:border-border-strong focus:border-accent"
          >
            <option value="">{t("dubNone")}</option>
            {LANGUAGE_OPTIONS.filter((option) => option.code !== draft.language).map(
              (option) => (
                <option key={option.code} value={option.code}>
                  {option.label}
                </option>
              )
            )}
          </select>
          <p className="mt-1.5 text-xs text-white/40">
            {clipCount
              ? t("dubWithClipsHint")
              : dubLanguage
              ? t("dubOnHint")
              : t("dubOffHint")}
          </p>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-white/70">{t("captionStyle")}</label>
          <CaptionStyleSelector />
        </div>

        {/* Here as well as in the generate tab: somebody captioning their
            own recording is the case this matters most for — they cannot
            re-write what was already said. */}
        <CensorToggle
          className="border-t border-border pt-4"
          checked={censor}
          onChange={setCensor}
        />
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
            <span>{progress < 1 ? t("uploading") : t("processing")}</span>
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
            ? t("costLine", {
                credits: ts("cost.credits", { count: price }),
                balance: credits.balance,
              })
            : ts("cost.free")}
        </p>
        <Button onClick={handleUpload} disabled={!file || uploading} variant="gradient">
          {uploading ? (
            t("working")
          ) : (
            <>
              {clipCount
                ? t("ctaClips", { count: clipCount })
                : dubLanguage
                  ? t("ctaDub")
                  : t("ctaCaption")}
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
