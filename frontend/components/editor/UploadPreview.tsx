"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { useTranslations } from "next-intl";
import { Film } from "lucide-react";
import type { AspectRatio, SubtitleStyle } from "@/lib/types";

/**
 * The right-hand column of the caption flow.
 *
 * Without it that screen is one narrow card floating in the middle of a
 * black page, which reads as unfinished rather than as minimal — and it is
 * the only screen in the product with nothing on the right, so it also
 * reads as a different app from the studio next door.
 *
 * Once a file is chosen it plays it, locally, immediately. That is worth
 * more than a prettier placeholder: the single most common upload mistake
 * is picking the wrong take, and until now nothing confirmed which video
 * was about to be spent a credit on.
 *
 * The object URL is revoked when the file changes or the panel unmounts.
 * Without that every re-pick leaks the previous blob for the life of the
 * document, which for a 200MB video is not a rounding error.
 */
/**
 * Same proportions the render will have, same idiom as `StudioPreview` —
 * the widths differ only because this column is narrower than that one.
 *
 * A template can set a square or landscape frame, so a box hardcoded to
 * 9:16 would show a shape the extraction is not going to produce.
 */
const ASPECT_CLASS: Record<AspectRatio, string> = {
  "9:16": "aspect-[9/16] max-w-[260px]",
  "1:1": "aspect-square max-w-[280px]",
  "16:9": "aspect-video max-w-[300px]",
};

/** Where the placeholder bars sit, matching the placement control. */
const BAR_CLASS: Record<SubtitleStyle["position"], string> = {
  top_third: "top-[12%]",
  middle: "top-1/2 -translate-y-1/2",
  bottom_third: "bottom-0",
};

export function UploadPreview({
  file,
  aspectRatio,
  captionPosition,
}: {
  file: File | null;
  aspectRatio: AspectRatio;
  captionPosition: SubtitleStyle["position"];
}) {
  const t = useTranslations("studio.uploadPreview");
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!file) {
      setUrl(null);
      return;
    }
    const next = URL.createObjectURL(file);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [file]);

  return (
    <div className="lg:sticky lg:top-6">
      <div
        className={clsx(
          "relative mx-auto w-full overflow-hidden rounded-xl border border-border bg-surface",
          ASPECT_CLASS[aspectRatio]
        )}
      >
        {url ? (
          <video
            key={url}
            src={url}
            className="h-full w-full object-cover"
            autoPlay
            muted
            loop
            playsInline
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
            <Film size={22} className="text-white/25" />
            <p className="text-xs leading-relaxed text-white/35">
              {t("empty")}
            </p>
          </div>
        )}

        {/* Where the captions will sit, drawn as bars rather than words:
            lorem text at this size is unreadable anyway, and a shape is
            honest about being a placeholder in a way fake sentences are
            not. Hidden once a real video is playing — the point is made. */}
        {!url && (
          <div
            className={clsx(
              "pointer-events-none absolute inset-x-0 flex flex-col items-center gap-1.5 p-5",
              BAR_CLASS[captionPosition]
            )}
          >
            <span className="h-2 w-3/4 rounded-full bg-white/10" />
            <span className="h-2 w-1/2 rounded-full bg-accent/30" />
          </div>
        )}
      </div>

      <p className="mt-3 text-center font-mono text-[10px] uppercase tracking-[0.18em] text-white/25">
        {t("caption", { ratio: aspectRatio })}
      </p>
    </div>
  );
}
