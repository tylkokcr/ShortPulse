"use client";

import { useMemo, useState } from "react";
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
import { editProject, uploadSecondaryClip } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import type { CaptionTrack, Layout, Project, TextOverlay, Word } from "@/lib/types";
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
function blankLine(lines: Line[]): Line {
  const last = lines[lines.length - 1]?.words.at(-1);
  const start = last ? last.end_ms + 200 : 0;
  return {
    words: [{ text: "New line", start_ms: start, end_ms: start + 1500, confidence: null }],
    startMs: start,
    text: "New line",
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
}: {
  project: Project;
  onApplied: (project: Project) => void;
  onSeek?: (seconds: number) => void;
}) {
  const track = project.edit?.captions ?? project.captions ?? null;

  // An edit replays the burn-in and overwrites final.mp4 in place, leaving
  // the project "complete" and its id unchanged — so nothing in the player
  // has any reason to fetch a new URL, and it keeps showing the video from
  // before the edit. The user reads that as the edit having done nothing
  // and reloads the page, which is the only thing that ever worked.
  // Re-rolling a scene already bumped this; applying an edit did not.
  const bumpVideoVersion = useShortPulseStore((s) => s.bumpVideoVersion);

  const [lines, setLines] = useState<Line[]>(() => (track ? toLines(track) : []));
  const [overlays, setOverlays] = useState<TextOverlay[]>(project.edit?.overlays ?? []);
  const [layout, setLayout] = useState<Layout>(project.edit?.layout ?? "full");
  const [secondary, setSecondary] = useState<string | null>(
    project.edit?.secondary_path ?? null
  );
  const [uploadingClip, setUploadingClip] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const original = useMemo(() => (track ? toLines(track) : []), [track]);
  const dirty =
    // Length first: deleting the *last* line leaves every remaining index
    // matching, so a per-index comparison alone would call it unchanged
    // and leave Apply disabled on a real edit.
    lines.length !== original.length ||
    lines.some((line, i) => line.text !== original[i]?.text) ||
    JSON.stringify(overlays) !== JSON.stringify(project.edit?.overlays ?? []) ||
    layout !== (project.edit?.layout ?? "full");

  if (!track) {
    return (
      <Card className="text-sm text-white/40">
        This video was rendered before captions became editable. Re-render it to correct the
        text.
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
      setError(err instanceof Error ? err.message : "Could not attach the clip");
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
        captions: { words, style: track!.style },
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
      if (applied) setLines(toLines(applied));
      setApplied(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not apply the edit");
    } finally {
      setApplying(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <span className="h-3 w-px bg-accent" />
          <h3 className="text-sm font-semibold text-white/80">Captions</h3>
          <span className="ml-auto font-mono text-[10px] text-white/30">
            {lines.length} lines
          </span>
          <button
            type="button"
            onClick={() => setLines((current) => [...current, blankLine(current)])}
            className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] text-white/60 transition-colors hover:border-accent/50 hover:text-white"
          >
            <Plus size={11} />
            Add line
          </button>
        </div>

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
                aria-label={`Delete line at ${timecode(line.startMs)}`}
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
          <h3 className="text-sm font-semibold text-white/80">Layout</h3>
        </div>

        {/* Two portrait frames rather than two labelled buttons. The
            choice is about the shape of the picture, so the control shows
            the shape — you can tell them apart before reading either
            caption, which a row of text with a 14px icon on it never
            allowed. */}
        <div className="grid grid-cols-2 gap-2.5">
          <LayoutTile
            label="Full frame"
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
            label={secondary ? "Split screen" : uploadingClip ? "Uploading…" : "Add a clip"}
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
              The narration stays on top and keeps the soundtrack; the bottom clip is muted
              and loops if it&apos;s shorter.
            </span>
            <label
              className={clsx(
                "shrink-0 cursor-pointer rounded-md border border-border px-2 py-1 text-white/50",
                "transition-colors hover:border-accent/50 hover:text-white",
                uploadingClip && "pointer-events-none opacity-60"
              )}
            >
              {uploadingClip ? "Uploading…" : "Replace"}
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
          <h3 className="text-sm font-semibold text-white/80">Text on screen</h3>
          <button
            type="button"
            onClick={() =>
              setOverlays((current) => [
                ...current,
                {
                  text: "New text",
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
            Add
          </button>
        </div>

        {overlays.length === 0 ? (
          <p className="text-xs text-white/35">
            Titles, labels, a punchline — drawn by the same engine as the captions, so it
            matches.
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
                    aria-label="Remove"
                    // p-2.5 rather than p-1: a 13px icon in 8px of padding
                    // is a 21px tap target, well under what a thumb hits.
                    className="shrink-0 rounded p-2.5 text-white/40 transition-colors hover:text-red-400"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-[10px] text-white/40">
                  <PositionPicker
                    value={overlay.position}
                    onChange={(position) =>
                      setOverlays((c) => c.map((o, j) => (j === i ? { ...o, position } : o)))
                    }
                  />
                  <TimeField
                    label="from"
                    ms={overlay.start_ms}
                    onChange={(ms) =>
                      setOverlays((c) => c.map((o, j) => (j === i ? { ...o, start_ms: ms } : o)))
                    }
                  />
                  <TimeField
                    label="to"
                    ms={overlay.end_ms}
                    onChange={(ms) =>
                      setOverlays((c) => c.map((o, j) => (j === i ? { ...o, end_ms: ms } : o)))
                    }
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
          {applied && !dirty ? "Applied — the video above is the new one." : "Free · a few seconds"}
        </p>
        <Button onClick={apply} disabled={!dirty || applying} variant="gradient">
          {applying ? (
            <>
              <Loader2 size={15} className="animate-spin" />
              Re-rendering
            </>
          ) : applied && !dirty ? (
            <>
              <Check size={15} />
              Applied
            </>
          ) : (
            "Apply and re-render"
          )}
        </Button>
      </div>
    </div>
  );
}

const POSITIONS = [
  { id: "top", label: "Top", y: "top-[3px]" },
  { id: "middle", label: "Middle", y: "top-1/2 -translate-y-1/2" },
  { id: "bottom", label: "Bottom", y: "bottom-[3px]" },
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
  return (
    <div className="flex items-center gap-1" role="radiogroup" aria-label="Position">
      {POSITIONS.map((option) => {
        const selected = value === option.id;
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={option.label}
            title={option.label}
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

function TimeField({
  label,
  ms,
  onChange,
}: {
  label: string;
  ms: number;
  onChange: (ms: number) => void;
}) {
  return (
    <label className="flex items-center gap-1.5 rounded-md border border-border bg-black/30 py-1 pl-2 pr-1.5 transition-colors focus-within:border-accent/50">
      {label}
      <input
        type="number"
        min={0}
        step={0.1}
        value={(ms / 1000).toFixed(1)}
        onChange={(e) => onChange(Math.max(Math.round(Number(e.target.value) * 1000), 0))}
        // Borderless inside the labelled pill: the box around it is the
        // field, so a second box around just the digits was one frame too
        // many in a row that already carries three of them.
        className="w-9 bg-transparent text-right text-[11px] text-white/80 focus:outline-none"
      />
      s
    </label>
  );
}
