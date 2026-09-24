"use client";

import { useMemo, useRef, useState } from "react";
import {
  Check,
  Loader2,
  Plus,
  Rows2,
  Trash2,
  Type,
  TriangleAlert,
  Upload,
} from "lucide-react";
import clsx from "clsx";
import { useTranslations } from "next-intl";
import { editProject, uploadSecondaryClip } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import type {
  CaptionTrack,
  Layout,
  Project,
  SubtitleStyle,
  TextOverlay,
  Word,
} from "@/lib/types";
import { CaptionPlacement } from "@/components/editor/CaptionPlacement";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

/**
 * Correct what the video says, and add text of your own.
 *
 * Applying is a server round trip rather than a client-side render,
 * because the burned-in result is the product and an approximation of it
 * would be a second implementation to keep in sync. It is affordable
 * because an edit replays only the burn-in pass — seconds, not minutes,
 * and no credits.
 *
 * Captions are grouped into the same lines the renderer chunks them into,
 * so a line here is a line on screen. Editing one splits the replacement
 * back across its words and keeps their timings, which is what preserves
 * the word-by-word highlight.
 */
interface Line {
  words: Word[];
  startMs: number;
  text: string;
}

function toLines(track: CaptionTrack): Line[] {
  const perLine = track.style.max_words_per_line;
  const lines: Line[] = [];
  for (let i = 0; i < track.words.length; i += perLine) {
    const words = track.words.slice(i, i + perLine);
    if (words.length === 0) continue;
    lines.push({
      words,
      startMs: words[0].start_ms,
      text: words.map((w) => w.text).join(" "),
    });
  }
  return lines;
}

/**
 * Put edited text back onto the original timings.
 *
 * The words carry timestamps measured from the audio; retyping the line
 * must not throw those away. When the word count matches, each word keeps
 * its own timing. When it doesn't — a word split in two, or two merged —
 * the line's span is divided evenly, which is approximate but keeps the
 * captions in sync with the speech either side of it.
 */
function toWords(line: Line, text: string): Word[] {
  const parts = text.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return [];
  if (parts.length === line.words.length) {
    return parts.map((part, i) => ({ ...line.words[i], text: part }));
  }
  const start = line.words[0].start_ms;
  const end = line.words[line.words.length - 1].end_ms;
  const step = (end - start) / parts.length;
  return parts.map((part, i) => ({
    text: part,
    start_ms: Math.round(start + step * i),
    end_ms: Math.round(start + step * (i + 1)),
    confidence: null,
  }));
}

/**
 * A new, empty caption line at the end of the track.
 *
 * Words carry the timings, so a line invented in the UI still needs one to
 * exist at all. It is given a second and a half after whatever currently
 * ends last, which puts it after the speech rather than on top of it — and
 * the timecode is editable through the same reflow every other line goes
 * through once applied.
 *
 * Adding was always *possible* by typing extra words into an existing line
 * and letting the chunker redistribute them, but nothing on screen said
 * so, which is indistinguishable from it being impossible.
 */
function blankLine(lines: Line[], placeholder: string): Line {
  const last = lines[lines.length - 1]?.words.at(-1);
  const start = last ? last.end_ms + 200 : 0;
  return {
    words: [{ text: placeholder, start_ms: start, end_ms: start + 1500, confidence: null }],
    startMs: start,
    text: placeholder,
  };
}

const CLIP_TYPES = "video/mp4,video/quicktime,video/webm,video/x-matroska";

/** A filled area inside a layout diagram. Grey until its tile is chosen,
 *  then the accent — the diagram itself carries the selection, not just a
 *  border around it. The seam between two stacked halves is a 2px gap
 *  rather than a drawn line: without it the split frame filled edge to
 *  edge and was indistinguishable from the full one. */
const FRAME_BLOCK =
  "bg-white/[0.14] transition-colors duration-200 group-data-[selected]:bg-accent/70";

/**
 * One layout option, drawn as the frame it produces.
 *
 * Renders as a <button> or, when given onFile, as a <label> around a
 * hidden file input — same box either way, because the tile that means
 * "split screen" and the tile that means "give me the clip that makes
 * split screen possible" are the same choice at two stages, and drawing
 * them differently would make it look like two features.
 *
 * The 9:16 mini-frame is deliberately plain: two flat blocks at 7% white.
 * It is a diagram of where the picture goes, not a thumbnail, and any
 * more detail in it would start to look like a preview of the render.
 */
function LayoutTile({
  label,
  selected,
  busy,
  onClick,
  onFile,
  accept,
  children,
}: {
  label: string;
  selected: boolean;
  busy?: boolean;
  onClick?: () => void;
  onFile?: (file: File | null) => void;
  accept?: string;
  children: React.ReactNode;
}) {
  const body = (
    <>
      <span className="relative block aspect-[9/16] w-9 overflow-hidden rounded-[4px] border border-white/10 bg-black/50">
        {busy ? (
          <Loader2 size={12} className="absolute inset-0 m-auto animate-spin text-white/40" />
        ) : (
          children
        )}
      </span>
      <span className="text-xs">{label}</span>
    </>
  );

  const className = clsx(
    "group flex cursor-pointer flex-col items-center gap-2 rounded-lg border px-3 py-3",
    "transition-[border-color,background-color,color] duration-200",
    selected
      ? "border-accent/60 bg-accent/[0.08] text-white"
      : "border-border text-white/50 hover:border-border-strong hover:text-white/70",
    busy && "pointer-events-none opacity-60",
    "focus-within:border-accent/60 focus-visible:border-accent/60 focus-visible:outline-none"
  );

  if (onFile) {
    return (
      <label className={className} data-selected={selected || undefined}>
        {body}
        <input
          type="file"
          accept={accept}
          className="sr-only"
          onChange={(e) => onFile(e.target.files?.[0] ?? null)}
        />
      </label>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      data-selected={selected || undefined}
      className={className}
    >
      {body}
    </button>
  );
}

function timecode(ms: number): string {
  const total = Math.max(Math.round(ms / 1000), 0);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function EditPanel({
  project,
  onApplied,
  onSeek,
  currentTime = 0,
  videoDurationS = 0,
}: {
  project: Project;
  onApplied: (project: Project) => void;
  onSeek?: (seconds: number) => void;
  /** Where the player is, in seconds. Drawn on each overlay's timeline so
   *  the span can be placed against what is actually on screen rather
   *  than against a number. */
  currentTime?: number;
  /** The video's real length, measured by the player. 0 before its header
   *  has loaded. */
  videoDurationS?: number;
}) {
  const t = useTranslations("app.edit");
  const track = project.edit?.captions ?? project.captions ?? null;

  // An edit replays the burn-in and overwrites final.mp4 in place, leaving
  // the project "complete" and its id unchanged — so nothing in the player
  // has any reason to fetch a new URL, and it keeps showing the video from
  // before the edit. The user reads that as the edit having done nothing
  // and reloads the page, which is the only thing that ever worked.
  // Re-rolling a scene already bumped this; applying an edit did not.
  const bumpVideoVersion = useShortPulseStore((s) => s.bumpVideoVersion);

  const [lines, setLines] = useState<Line[]>(() => (track ? toLines(track) : []));
  // Placement is part of the style the burn-in reads, so changing it here
  // is the same one-pass re-render an edited word is — not a re-run.
  const [position, setPosition] = useState<SubtitleStyle["position"]>(
    () => track?.style.position ?? "bottom_third"
  );
  const [fontSize, setFontSize] = useState<number>(() => track?.style.font_size ?? 84);
  const [overlays, setOverlays] = useState<TextOverlay[]>(project.edit?.overlays ?? []);
  const [layout, setLayout] = useState<Layout>(project.edit?.layout ?? "full");
  const [secondary, setSecondary] = useState<string | null>(
    project.edit?.secondary_path ?? null
  );
  const [uploadingClip, setUploadingClip] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // How long the timelines are.
  //
  // The player's own reading, or the last caption word until it arrives.
  // Deliberately NOT the script's total_duration_s: that is what was
  // asked of the model, and the audio does not come out at that length —
  // on the project this was first tried against the script said 32s and
  // the render was 26.6s, so a handle dragged to the right-hand end of
  // the track landed five seconds past the last frame.
  //
  // Overlays already stored past the end still widen the track. They are
  // wrong, but drawing them off the end would make them invisible and
  // therefore unfixable, which is worse than showing a long track.
  const durationMs = useMemo(() => {
    const measured = videoDurationS * 1000;
    const lastWord = track?.words.at(-1)?.end_ms ?? 0;
    const overlayEnd = overlays.reduce((max, o) => Math.max(max, o.end_ms), 0);
    return Math.max(measured || lastWord, overlayEnd, 1000);
  }, [videoDurationS, track, overlays]);

  const original = useMemo(() => (track ? toLines(track) : []), [track]);
  const dirty =
    // Length first: deleting the *last* line leaves every remaining index
    // matching, so a per-index comparison alone would call it unchanged
    // and leave Apply disabled on a real edit.
    lines.length !== original.length ||
    lines.some((line, i) => line.text !== original[i]?.text) ||
    JSON.stringify(overlays) !== JSON.stringify(project.edit?.overlays ?? []) ||
    layout !== (project.edit?.layout ?? "full") ||
    position !== track?.style.position ||
    fontSize !== track?.style.font_size;

  if (!track) {
    return (
      <Card className="text-sm text-white/40">
        {t("notEditable")}
      </Card>
    );
  }

  // Attaching a clip is its own round trip, not part of Apply: the file
  // has to reach the server before a split render can reference it, and
  // picking one is itself the statement that you want the split layout.
  async function attachClip(file: File | null) {
    if (!file) return;
    setUploadingClip(true);
    setError(null);
    try {
      const updated = await uploadSecondaryClip(project.config.id, file);
      setSecondary(updated.edit?.secondary_path ?? null);
      setLayout("split_v");
      onApplied(updated);
      bumpVideoVersion();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.clip"));
    } finally {
      setUploadingClip(false);
    }
  }

  async function apply() {
    setApplying(true);
    setError(null);
    setApplied(false);
    try {
      const words = lines.flatMap((line) => toWords(line, line.text));
      const updated = await editProject(project.config.id, {
        captions: { words, style: { ...track!.style, position, font_size: fontSize } },
        overlays,
        layout,
      });
      onApplied(updated);
      bumpVideoVersion();
      // Re-derive from what came back rather than keeping what was typed.
      // Lines are chunks of N words, so shortening one line pulls words up
      // from the next and reflows everything after it — the panel has to
      // show the arrangement the video now has, not the one that produced
      // it.
      const applied = updated.edit?.captions ?? updated.captions;
      if (applied) {
        setLines(toLines(applied));
        setPosition(applied.style.position);
        setFontSize(applied.style.font_size);
      }
      setApplied(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.apply"));
    } finally {
      setApplying(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <span className="h-3 w-px bg-accent" />
          <h3 className="text-sm font-semibold text-white/80">{t("captions")}</h3>
          <span className="ml-auto font-mono text-[10px] text-white/30">
            {t("lineCount", { count: lines.length })}
          </span>
          <button
            type="button"
            onClick={() => setLines((current) => [...current, blankLine(current, t("newLine"))])}
            className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] text-white/60 transition-colors hover:border-accent/50 hover:text-white"
          >
            <Plus size={11} />
            {t("addLine")}
          </button>
        </div>

        <CaptionPlacement
          className="border-b border-border pb-3"
          position={position}
          fontSize={fontSize}
          onChange={(next) => {
            setPosition(next.position);
            setFontSize(next.fontSize);
          }}
        />

        <div className="flex max-h-[340px] flex-col gap-1 overflow-y-auto pr-1">
          {lines.map((line, i) => (
            <div key={i} className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => onSeek?.(line.startMs / 1000)}
                className="shrink-0 font-mono text-[10px] text-white/30 transition-colors hover:text-accent"
              >
                {timecode(line.startMs)}
              </button>
              <input
                value={line.text}
                onChange={(e) =>
                  setLines((current) =>
                    current.map((l, j) => (j === i ? { ...l, text: e.target.value } : l))
                  )
                }
                className={clsx(
                  "min-w-0 flex-1 rounded-md border bg-background px-2.5 py-1.5 text-xs transition-colors",
                  line.text !== original[i]?.text
                    ? "border-accent/50 text-white"
                    : "border-border text-white/70 hover:border-border-strong"
                )}
              />
              {/* Emptying the field already drops the line — toWords returns
                  nothing for blank text — but that is a thing you have to
                  know rather than see. */}
              <button
                type="button"
                aria-label={t("deleteLine", { time: timecode(line.startMs) })}
                onClick={() => setLines((current) => current.filter((_, j) => j !== i))}
                className="shrink-0 rounded p-1 text-white/20 transition-colors hover:bg-white/5 hover:text-red-400"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      </Card>

      <Card className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Rows2 size={13} className="text-white/40" />
          <h3 className="text-sm font-semibold text-white/80">{t("layout")}</h3>
        </div>

        {/* Two portrait frames rather than two labelled buttons. The
            choice is about the shape of the picture, so the control shows
            the shape — you can tell them apart before reading either
            caption, which a row of text with a 14px icon on it never
            allowed. */}
        <div className="grid grid-cols-2 gap-2.5">
          <LayoutTile
            label={t("full")}
            selected={layout === "full"}
            onClick={() => setLayout("full")}
          >
            <span className={clsx("absolute inset-0 rounded-[3px]", FRAME_BLOCK)} />
          </LayoutTile>

          {/* With no clip attached this tile *is* the file picker, instead
              of being disabled above a separate dashed strip that had to
              be noticed. One control, and the thing it produces is the
              thing it is drawn as. */}
          <LayoutTile
            label={secondary ? t("split") : uploadingClip ? t("uploadingClip") : t("addClip")}
            selected={layout === "split_v"}
            busy={uploadingClip}
            {...(secondary
              ? { onClick: () => setLayout("split_v") }
              : { onFile: attachClip, accept: CLIP_TYPES })}
          >
            <span
              className={clsx("absolute inset-x-0 top-0 h-[calc(50%-1px)] rounded-t-[3px]", FRAME_BLOCK)}
            />
            <span
              className={clsx(
                "absolute inset-x-0 bottom-0 flex h-[calc(50%-1px)] items-center justify-center rounded-b-[3px]",
                secondary ? FRAME_BLOCK : "border-t border-dashed border-white/20"
              )}
            >
              {!secondary && !uploadingClip && <Upload size={11} className="text-white/35" />}
            </span>
          </LayoutTile>
        </div>

        {secondary && (
          <div className="flex items-center gap-2 text-[11px] text-white/35">
            <span className="min-w-0 flex-1">
              {t("splitNote")}
            </span>
            <label
              className={clsx(
                "shrink-0 cursor-pointer rounded-md border border-border px-2 py-1 text-white/50",
                "transition-colors hover:border-accent/50 hover:text-white",
                uploadingClip && "pointer-events-none opacity-60"
              )}
            >
              {uploadingClip ? t("uploadingClip") : t("replaceClip")}
              <input
                type="file"
                accept={CLIP_TYPES}
                className="hidden"
                onChange={(e) => attachClip(e.target.files?.[0] ?? null)}
              />
            </label>
          </div>
        )}
      </Card>

      <Card className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Type size={13} className="text-white/40" />
          <h3 className="text-sm font-semibold text-white/80">{t("overlays")}</h3>
          <button
            type="button"
            onClick={() =>
              setOverlays((current) => [
                ...current,
                {
                  text: t("newText"),
                  start_ms: 0,
                  end_ms: 3000,
                  position: "top",
                  font_size: 72,
                  color: "&H00FFFFFF",
                },
              ])
            }
            className="ml-auto flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] text-white/60 transition-colors hover:border-accent/50 hover:text-white"
          >
            <Plus size={11} />
            {t("addText")}
          </button>
        </div>

        {overlays.length === 0 ? (
          <p className="text-xs text-white/35">
            {t("overlaysEmpty")}
          </p>
        ) : (
          <div className="flex flex-col gap-2.5">
            {overlays.map((overlay, i) => (
              <div key={i} className="flex flex-col gap-1.5 rounded-lg border border-border p-2.5">
                <div className="flex items-center gap-2">
                  <input
                    value={overlay.text}
                    maxLength={200}
                    onChange={(e) =>
                      setOverlays((c) =>
                        c.map((o, j) => (j === i ? { ...o, text: e.target.value } : o))
                      )
                    }
                    className="min-w-0 flex-1 rounded-md border border-border bg-background px-2.5 py-1.5 text-xs"
                  />
                  <button
                    type="button"
                    onClick={() => setOverlays((c) => c.filter((_, j) => j !== i))}
                    aria-label={t("removeText")}
                    // p-2.5 rather than p-1: a 13px icon in 8px of padding
                    // is a 21px tap target, well under what a thumb hits.
                    className="shrink-0 rounded p-2.5 text-white/40 transition-colors hover:text-red-400"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
                <div className="flex items-center gap-2.5">
                  <PositionPicker
                    value={overlay.position}
                    onChange={(position) =>
                      setOverlays((c) => c.map((o, j) => (j === i ? { ...o, position } : o)))
                    }
                  />
                  <TimelineRange
                    startMs={overlay.start_ms}
                    endMs={overlay.end_ms}
                    durationMs={durationMs}
                    playheadMs={currentTime * 1000}
                    onChange={(start_ms, end_ms) =>
                      setOverlays((c) =>
                        c.map((o, j) => (j === i ? { ...o, start_ms, end_ms } : o))
                      )
                    }
                    onSeek={onSeek}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {error && (
        <p className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2.5 text-xs text-red-400">
          <TriangleAlert size={13} className="mt-0.5 shrink-0" />
          {error}
        </p>
      )}

      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] text-white/35">
          {applied && !dirty ? t("appliedNote") : t("freeNote")}
        </p>
        <Button onClick={apply} disabled={!dirty || applying} variant="gradient">
          {applying ? (
            <>
              <Loader2 size={15} className="animate-spin" />
              {t("rerendering")}
            </>
          ) : applied && !dirty ? (
            <>
              <Check size={15} />
              {t("applied")}
            </>
          ) : (
            t("apply")
          )}
        </Button>
      </div>
    </div>
  );
}

const POSITIONS = [
  { id: "top", y: "top-[3px]" },
  { id: "middle", y: "top-1/2 -translate-y-1/2" },
  { id: "bottom", y: "bottom-[3px]" },
] as const;

/**
 * Where the overlay sits in the frame.
 *
 * Three frames with the text bar drawn in place, instead of a native
 * <select> reading "Top". The choice is spatial and there are exactly
 * three of them, so a dropdown was hiding two thirds of a decision that
 * fits on one line — and a platform select is the one control on the page
 * the design cannot reach, which is most of why this corner looked older
 * than the rest of it.
 */
function PositionPicker({
  value,
  onChange,
}: {
  value: TextOverlay["position"];
  onChange: (position: TextOverlay["position"]) => void;
}) {
  const t = useTranslations("app.edit");

  return (
    <div className="flex items-center gap-1" role="radiogroup" aria-label={t("position")}>
      {POSITIONS.map((option) => {
        const selected = value === option.id;
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={t(option.id)}
            title={t(option.id)}
            onClick={() => onChange(option.id)}
            className={clsx(
              "relative h-7 w-[19px] shrink-0 overflow-hidden rounded-[3px] border",
              "transition-[border-color,background-color] duration-200",
              "focus-visible:outline-none focus-visible:border-accent",
              selected
                ? "border-accent/60 bg-accent/10"
                : "border-border bg-black/40 hover:border-border-strong"
            )}
          >
            <span
              className={clsx(
                "absolute inset-x-[3px] h-[3px] rounded-[1px] transition-colors duration-200",
                option.y,
                selected ? "bg-accent" : "bg-white/25"
              )}
            />
          </button>
        );
      })}
    </div>
  );
}

/** mm:ss.d — tenths, because that is the precision the control edits in
 *  and a burned-in title landing a tenth late is visible. */
function stamp(ms: number): string {
  const clamped = Math.max(ms, 0);
  const total = Math.floor(clamped / 1000);
  const tenths = Math.floor((clamped % 1000) / 100);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}.${tenths}`;
}

/** Nothing shorter than this is worth burning in, and it stops a handle
 *  dragged past its partner from inverting the span. */
const MIN_SPAN_MS = 200;
const STEP_MS = 100;

type Grab = { kind: "start" | "end" | "move"; grabMs: number };

/**
 * When the overlay is on screen, against the whole video.
 *
 * It replaces two number fields reading "from 0,0 s to 3,0 s". Those were
 * accurate and told you nothing: the question anyone actually has is
 * whether the title lands on the right moment, and a decimal cannot
 * answer that without playing the video and counting. Here the span is
 * drawn over the full duration with the playhead on the same track, so
 * the answer is the picture.
 *
 * Dragging is the primary control and the keyboard is not an afterthought
 * — each handle is a focusable slider that moves in tenths, a second with
 * shift — because a burned-in caption is exactly the kind of thing
 * somebody nudges frame by frame, and a drag alone cannot do that.
 */
function TimelineRange({
  startMs,
  endMs,
  durationMs,
  playheadMs,
  onChange,
  onSeek,
}: {
  startMs: number;
  endMs: number;
  durationMs: number;
  playheadMs: number;
  onChange: (startMs: number, endMs: number) => void;
  onSeek?: (seconds: number) => void;
}) {
  const t = useTranslations("app.edit");
  const trackRef = useRef<HTMLDivElement>(null);
  const [grab, setGrab] = useState<Grab | null>(null);

  const pct = (ms: number) => Math.min(Math.max(ms / durationMs, 0), 1) * 100;

  function msAt(clientX: number): number {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return 0;
    const ratio = Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1);
    return Math.round((ratio * durationMs) / STEP_MS) * STEP_MS;
  }

  function apply(kind: Grab["kind"], at: number, grabMs: number) {
    // Clamped to the video here rather than where the position comes
    // from: a drag is already bounded by the track it happens on, but
    // arrow keys are not, and an end held past the last frame stored a
    // span the render can never show.
    const inVideo = Math.min(Math.max(at, 0), durationMs);
    if (kind === "start") {
      onChange(Math.min(inVideo, endMs - MIN_SPAN_MS), endMs);
    } else if (kind === "end") {
      onChange(startMs, Math.max(inVideo, startMs + MIN_SPAN_MS));
    } else {
      // The whole span follows the pointer by the offset it was grabbed
      // at, so it does not jump its own width on the first movement, and
      // it stops at each end instead of being clipped by it.
      const span = endMs - startMs;
      const next = Math.min(Math.max(at - grabMs, 0), Math.max(durationMs - span, 0));
      onChange(next, next + span);
    }
  }

  // Takes the event rather than returning a handler: a factory called
  // during render puts the ref read inside a function the linter cannot
  // prove is deferred, and it is right to object — the deferral was an
  // accident of where the closure happened to be built.
  function startGrab(kind: Grab["kind"], event: React.PointerEvent) {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setGrab({ kind, grabMs: kind === "move" ? msAt(event.clientX) - startMs : 0 });
  }

  function onPointerMove(event: React.PointerEvent) {
    if (!grab) return;
    apply(grab.kind, msAt(event.clientX), grab.grabMs);
  }

  function endGrab(event: React.PointerEvent) {
    if (!grab) return;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    setGrab(null);
  }

  function nudge(kind: "start" | "end", event: React.KeyboardEvent) {
    const step = event.shiftKey ? 1000 : STEP_MS;
    const delta = event.key === "ArrowLeft" ? -step : event.key === "ArrowRight" ? step : 0;
    if (!delta) return;
    event.preventDefault();
    apply(kind, (kind === "start" ? startMs : endMs) + delta, 0);
  }

  const handle =
    "absolute top-0 h-full w-4 -translate-x-1/2 cursor-ew-resize touch-none rounded-full " +
    "after:absolute after:inset-y-1 after:left-1/2 after:w-[3px] after:-translate-x-1/2 " +
    "after:rounded-full after:bg-accent after:transition-colors " +
    "hover:after:bg-accent-hover focus-visible:outline-none focus-visible:after:bg-white";

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1">
      <div
        ref={trackRef}
        className="relative h-7 w-full rounded-md border border-border bg-black/40"
        onPointerMove={onPointerMove}
        onPointerUp={endGrab}
        onPointerCancel={endGrab}
      >
        {/* Drag anywhere on the span to move it. aria-hidden rather than a
            button: there is no keyboard equivalent for moving both ends at
            once, and the two sliders below already reach every value this
            reaches — announcing a control that cannot be operated is worse
            than announcing nothing. */}
        <span
          aria-hidden
          onPointerDown={(event) => startGrab("move", event)}
          className="absolute top-0 h-full cursor-grab touch-none rounded-[3px] border-y border-accent/50 bg-accent/20 active:cursor-grabbing"
          style={{ left: `${pct(startMs)}%`, width: `${pct(endMs) - pct(startMs)}%` }}
        />

        {/* Where the video is, drawn over the span rather than under it.
            Under looked tidier until you noticed it vanished exactly when
            the playhead entered the span — which is the one moment it
            answers something, because that is the text being on screen. */}
        <span
          aria-hidden
          className="pointer-events-none absolute top-0 h-full w-px bg-white/70"
          style={{ left: `${pct(playheadMs)}%` }}
        />

        <span
          role="slider"
          tabIndex={0}
          aria-label={t("start")}
          aria-valuemin={0}
          aria-valuemax={Math.round(durationMs / 1000)}
          aria-valuenow={startMs / 1000}
          aria-valuetext={stamp(startMs)}
          onPointerDown={(event) => startGrab("start", event)}
          onKeyDown={(event) => nudge("start", event)}
          className={handle}
          style={{ left: `${pct(startMs)}%` }}
        />
        <span
          role="slider"
          tabIndex={0}
          aria-label={t("end")}
          aria-valuemin={0}
          aria-valuemax={Math.round(durationMs / 1000)}
          aria-valuenow={endMs / 1000}
          aria-valuetext={stamp(endMs)}
          onPointerDown={(event) => startGrab("end", event)}
          onKeyDown={(event) => nudge("end", event)}
          className={handle}
          style={{ left: `${pct(endMs)}%` }}
        />
      </div>

      <div className="flex items-center gap-1 font-mono text-[10px] tabular-nums text-white/35">
        {/* Clicking a timecode seeks, the same as clicking one in the
            breakdown above — so checking the placement is one click
            rather than a scrub. */}
        <button
          type="button"
          onClick={() => onSeek?.(startMs / 1000)}
          className="rounded px-1 transition-colors hover:bg-surface-hover hover:text-white"
        >
          {stamp(startMs)}
        </button>
        <span className="text-white/20">→</span>
        <button
          type="button"
          onClick={() => onSeek?.(endMs / 1000)}
          className="rounded px-1 transition-colors hover:bg-surface-hover hover:text-white"
        >
          {stamp(endMs)}
        </button>
        <span className="ml-auto text-white/20">{stamp(durationMs)}</span>
      </div>
    </div>
  );
}
