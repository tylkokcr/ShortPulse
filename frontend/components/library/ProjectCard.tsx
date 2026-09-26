"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Play, Scissors, Trash2, TriangleAlert, Upload } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import clsx from "clsx";
import { Link } from "@/i18n/navigation";
import { getMediaUrl, type MediaUrl } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";

/**
 * One project in the library grid.
 *
 * The thumbnail is fetched per card rather than served from a static path,
 * because the poster sits behind the same signed short-lived URL as the
 * video — a project's frames are no more public than the project. Cards
 * for a render that hasn't finished have nothing to show yet and say so,
 * rather than holding an empty box.
 */
export function ProjectCard({
  project,
  onDelete,
}: {
  project: Project;
  onDelete: (id: string) => void;
}) {
  const t = useTranslations("app.library");
  // Intl.RelativeTimeFormat through next-intl, so "2 days ago" is
  // "2 gün önce" in Turkish without a message key per unit.
  const formatter = useFormatter();
  const made = parseUtc(project.config.created_at);
  // One fetch, two uses: the still the card shows at rest and the video
  // it plays on hover are the same signed grant.
  const [media, setMedia] = useState<MediaUrl | null>(null);
  const [posterBroken, setPosterBroken] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const hoverTimer = useRef<number | null>(null);
  const [confirming, setConfirming] = useState(false);
  const id = project.config.id;
  const complete = project.status === "complete";
  // An extraction has no video of its own. Without this the card offered
  // a play triangle and called it "Captioned", both of which describe the
  // clips rather than the thing being clicked.
  const clipCount = project.clip_project_ids?.length ?? 0;

  useEffect(() => {
    // An extraction has no media to ask for; the request would 404 and
    // the catch below would swallow it, which is a round trip to learn
    // something already known.
    if (!complete || clipCount > 0) return;
    let cancelled = false;
    getMediaUrl(id)
      .then((fetched) => {
        if (!cancelled) setMedia(fetched);
      })
      // Projects rendered before posters existed have none. The gradient
      // placeholder below is the whole fallback.
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [id, complete, clipCount]);

  // Nothing is left running when the card scrolls out of a virtualised
  // list or the user navigates mid-hover.
  useEffect(() => () => clearTimer(hoverTimer), []);

  const startPreview = useCallback(() => {
    if (!complete || clipCount > 0 || !previewsAreWelcome()) return;
    clearTimer(hoverTimer);
    // Long enough that crossing the grid to reach something else does not
    // start five videos on the way past; short enough that stopping on a
    // card feels like it answered.
    hoverTimer.current = window.setTimeout(async () => {
      // The grant is short-lived by design. A tab left open over lunch
      // would otherwise hover into a dead URL and show nothing, which
      // reads as a broken card rather than an expired token.
      if (media && media.expires_at * 1000 < Date.now() + 5_000) {
        try {
          setMedia(await getMediaUrl(id));
        } catch {
          return;
        }
      }
      setPreviewing(true);
    }, PREVIEW_DELAY_MS);
  }, [complete, clipCount, media, id]);

  const stopPreview = useCallback(() => {
    clearTimer(hoverTimer);
    setPreviewing(false);
  }, []);

  const isUpload = project.config.source === "upload";
  const poster = posterBroken ? null : (media?.poster_url ?? null);

  return (
    <div
      className="group relative flex flex-col gap-2.5"
      onPointerEnter={startPreview}
      onPointerLeave={stopPreview}
    >
      <Link
        href={`/project/${id}`}
        // Lifted on hover, and the picture pushes past the frame from the
        // inside. Colour alone could not say which of eight dark posters
        // the pointer was on — the card that moves is the one you are
        // pointing at, which is the whole job. Two pixels and three
        // percent: enough to register, not enough to look like a toy.
        className="relative block aspect-[9/16] overflow-hidden rounded-md border border-border bg-surface transition-all duration-300 hover:border-border-strong hover:shadow-xl hover:shadow-black/40 motion-safe:hover:-translate-y-0.5"
      >
        {poster ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={poster}
            alt=""
            className="animate-fade-in h-full w-full object-cover transition-transform duration-500 ease-out motion-safe:group-hover:scale-[1.03]"
            onError={() => setPosterBroken(true)}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-surface-raised to-background">
            {project.status === "rendering" ? (
              <Loader2 size={20} className="animate-spin text-accent" />
            ) : project.status === "failed" ? (
              <TriangleAlert size={20} className="text-red-400/70" />
            ) : clipCount ? (
              <Scissors size={20} className="text-white/20" />
            ) : (
              <Play size={20} className="text-white/20" />
            )}
          </div>
        )}

        {/* Over the still rather than instead of it: the poster keeps
            the frame filled while the first bytes arrive, so the card
            never blinks to black on the way into the preview. */}
        {previewing && media && (
          <video
            src={media.url}
            className="animate-fade-in absolute inset-0 h-full w-full object-cover"
            autoPlay
            muted
            loop
            playsInline
            preload="none"
          />
        )}

        {/* Only where it differentiates.
            Generated is what most of this library is, so marking it marks
            everything: eight identical chips that carry no information
            and sit over the one part of the card that does, the picture.
            Clips and captioned uploads are the exceptions, so those are
            the ones that get said out loud — the same rule the status
            badge below already follows by only appearing when the status
            is not "complete". */}
        {(clipCount > 0 || isUpload) && (
          <Badge
            tone="neutral"
            className="absolute left-2 top-2 flex items-center gap-1 border-white/10 bg-black/60 px-2 py-0.5 text-[10px] text-white/70 backdrop-blur"
          >
            {clipCount ? <Scissors size={9} /> : <Upload size={9} />}
            {clipCount ? t("badge.clips", { count: clipCount }) : t("badge.captioned")}
          </Badge>
        )}

        {/* Says the card plays, before the hover preview proves it.
            Only where there is something to play: an extraction holds no
            video of its own, and a render that failed has none either.
            Bottom-right rather than centred — the centre of the frame is
            usually the speaker's face, and the caption sits at the
            bottom-left. */}
        {complete && clipCount === 0 && (
          <span
            aria-hidden
            className="absolute bottom-2 right-2 flex h-7 w-7 items-center justify-center rounded-full border border-white/15 bg-black/55 text-white/80 backdrop-blur transition-all duration-200 group-hover:border-white/25 group-hover:bg-black/70 group-hover:text-white"
          >
            <Play size={11} className="translate-x-[1px] fill-current" />
          </span>
        )}

        {project.status !== "complete" && (
          <Badge
            tone="neutral"
            className={clsx(
              "absolute right-2 top-2 px-2 py-0.5 text-[10px] backdrop-blur",
              project.status === "failed"
                ? "border-red-500/30 bg-red-500/15 text-red-300"
                : "border-white/10 bg-black/60 text-white/70"
            )}
          >
            {t(`status.${project.status}`)}
          </Badge>
        )}
      </Link>

      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-xs font-medium">{project.config.topic}</p>
          {/* When it was made and how long it is — the two things you
              browse a library by, and the two the card never showed. The
              language moves to the title attribute: the thumbnail is
              already covered in it. */}
          <p
            className="mt-0.5 font-mono text-[10px] text-white/35"
            title={project.config.language.toUpperCase()}
          >
            {[
              made && formatter.relativeTime(made),
              project.duration_s != null && clock(project.duration_s),
              project.config.aspect_ratio,
              project.credits_cost > 0 && t("credits", { count: project.credits_cost }),
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>

        <button
          type="button"
          onClick={() => (confirming ? onDelete(id) : setConfirming(true))}
          onBlur={() => setConfirming(false)}
          aria-label={confirming ? t("confirmDelete") : t("delete")}
          className={clsx(
            // Revealed on hover on a pointer device, always visible on a
            // touch one — there is no hover on a phone, so hiding it there
            // makes deleting a project impossible rather than tidy. The
            // padding is the tap target, not decoration.
            "shrink-0 rounded-md p-2.5 transition-all duration-200",
            confirming
              ? "bg-red-500/20 text-red-400"
              : "text-white/40 hover:text-red-400 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100"
          )}
        >
          <Trash2 size={13} />
        </button>
      </div>

      {confirming && (
        <p className="text-[10px] leading-tight text-red-400/80">
          {t("deleteWarning")}
        </p>
      )}
    </div>
  );
}

/**
 * The backend stores `datetime.utcnow()` and serialises it without an
 * offset. JavaScript reads an ISO string with no zone as *local* time, so
 * a video made a minute ago reads as three hours old in Istanbul and
 * "in 5 hours" in São Paulo. Appending the Z the server omits is the
 * whole fix.
 */
function parseUtc(value: string | undefined): Date | null {
  if (!value) return null;
  const zoned = /[Zz]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`;
  const date = new Date(zoned);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** m:ss. Seconds are the unit here — every video in this product is
 *  shorter than an hour by construction. */
function clock(seconds: number): string {
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/** How long the pointer has to stay on a card before it plays. */
const PREVIEW_DELAY_MS = 400;

function clearTimer(ref: { current: number | null }) {
  if (ref.current !== null) {
    window.clearTimeout(ref.current);
    ref.current = null;
  }
}

/**
 * Whether a hover preview is wanted here at all.
 *
 * A finger is not a cursor: `pointerenter` fires on the tap that is
 * already opening the project, so on a phone this would start a video
 * nobody sees. And an autoplaying clip is motion — someone who asked the
 * OS for less of it gets the still, which is the same rule the grid
 * backdrop and the caption drift already follow.
 */
function previewsAreWelcome(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  if (!window.matchMedia("(hover: hover)").matches) return false;
  return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
