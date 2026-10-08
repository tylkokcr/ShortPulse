"use client";

import { useEffect, useRef, useState } from "react";
import { Link2, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { getMediaImport, importMediaLink } from "@/lib/api";
import type { MediaFile } from "@/lib/types";

const POLL_MS = 2000;

/**
 * Bring a video in from a link — Google Drive, Dropbox, a plain video link,
 * or YouTube where the operator allows it. The server fetches it into My
 * files and the caller gets the file back, exactly as if it had been picked
 * there, so nothing after this knows it came from a link.
 *
 * The rights box is not decoration: the server refuses without it (see
 * backend services/link_import.py).
 */
export function LinkImport({
  onImported,
  disabled,
}: {
  onImported: (media: MediaFile) => void;
  disabled?: boolean;
}) {
  const t = useTranslations("studio.link");
  const [url, setUrl] = useState("");
  const [rights, setRights] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    []
  );

  const youtube = /(^|\/\/|\.)(youtube\.com|youtu\.be)\//i.test(url);

  async function start() {
    setError(null);
    setBusy(true);
    try {
      const job = await importMediaLink(url.trim(), rights);
      const poll = async () => {
        try {
          const now = await getMediaImport(job.id);
          if (now.status === "running") {
            timer.current = window.setTimeout(poll, POLL_MS);
            return;
          }
          setBusy(false);
          if (now.status === "done" && now.media) {
            setUrl("");
            onImported(now.media);
          } else {
            setError(now.error ?? t("failed"));
          }
        } catch {
          setBusy(false);
          setError(t("failed"));
        }
      };
      timer.current = window.setTimeout(poll, POLL_MS);
    } catch (err) {
      setBusy(false);
      const message = err instanceof Error ? err.message : "";
      setError(/youtube/i.test(message) && /can't be imported/i.test(message) ? t("youtubeOff") : message || t("failed"));
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border bg-black/20 p-3">
      <label htmlFor="video-link" className="flex items-center gap-1.5 text-xs font-medium text-white/60">
        <Link2 size={13} />
        {t("label")}
      </label>
      <div className="flex gap-2">
        <input
          id="video-link"
          type="url"
          inputMode="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder={t("placeholder")}
          disabled={busy || disabled}
          className="min-w-0 flex-1 rounded-md border border-border bg-surface px-3 py-2 text-sm placeholder:text-white/25 focus:border-accent focus:outline-none disabled:opacity-50"
        />
        <button
          type="button"
          onClick={start}
          disabled={!url.trim() || !rights || busy || disabled}
          className="flex shrink-0 items-center gap-1.5 rounded-md border border-border px-3 py-2 text-xs text-white/75 hover:border-border-strong hover:text-white disabled:opacity-40"
        >
          {busy && <Loader2 size={13} className="animate-spin" />}
          {t(busy ? "fetching" : "fetch")}
        </button>
      </div>
      <label className="flex cursor-pointer items-start gap-2 text-[11px] leading-snug text-white/55">
        <input
          type="checkbox"
          checked={rights}
          onChange={(e) => setRights(e.target.checked)}
          disabled={busy}
          className="mt-0.5 accent-[rgb(var(--accent))]"
        />
        {t("rights")}
      </label>
      {youtube && !error && <p className="text-[11px] leading-snug text-white/40">{t("youtubeNote")}</p>}
      {busy && <p className="text-[11px] text-white/40">{t("busyHint")}</p>}
      {error && <p className="text-[11px] leading-snug text-red-400">{error}</p>}
    </div>
  );
}
