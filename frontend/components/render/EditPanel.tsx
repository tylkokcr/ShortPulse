"use client";

import { useMemo, useState } from "react";
import {
  Check,
  Loader2,
  Plus,
  Rows2,
  Square,
  Trash2,
  Type,
  TriangleAlert,
  Upload,
} from "lucide-react";
import clsx from "clsx";
import { editProject, uploadSecondaryClip } from "@/lib/api";
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
            </div>
          ))}
        </div>
      </Card>

      <Card className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Rows2 size={13} className="text-white/40" />
          <h3 className="text-sm font-semibold text-white/80">Layout</h3>
        </div>

        <div className="grid grid-cols-2 gap-2">
          {([
            { id: "full", label: "Full frame", icon: Square },
            { id: "split_v", label: "Split screen", icon: Rows2 },
          ] as const).map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setLayout(option.id)}
              disabled={option.id === "split_v" && !secondary}
              className={clsx(
                "flex items-center gap-2 rounded-lg border px-3 py-2 text-xs transition-colors duration-200",
                layout === option.id
                  ? "border-accent/50 bg-accent/10 text-white"
                  : "border-border text-white/50 hover:border-border-strong",
                option.id === "split_v" && !secondary && "cursor-not-allowed opacity-40"
              )}
            >
              <option.icon size={14} />
              {option.label}
            </button>
          ))}
        </div>

        <label
          className={clsx(
            "flex cursor-pointer items-center gap-2 rounded-lg border border-dashed border-border px-3 py-2 text-xs transition-colors hover:border-accent/40",
            uploadingClip && "pointer-events-none opacity-60"
          )}
        >
          <Upload size={13} className="shrink-0 text-white/40" />
          <span className="min-w-0 flex-1 truncate text-white/50">
            {uploadingClip
              ? "Uploading..."
              : secondary
                ? "Bottom clip attached — click to replace"
                : "Add a clip for the bottom half"}
          </span>
          <input
            type="file"
            accept="video/mp4,video/quicktime,video/webm,video/x-matroska"
            className="hidden"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setUploadingClip(true);
              setError(null);
              try {
                const updated = await uploadSecondaryClip(project.config.id, file);
                setSecondary(updated.edit?.secondary_path ?? null);
                setLayout("split_v");
                onApplied(updated);
              } catch (err) {
                setError(err instanceof Error ? err.message : "Could not attach the clip");
              } finally {
                setUploadingClip(false);
              }
            }}
          />
        </label>

        <p className="text-[11px] leading-relaxed text-white/30">
          The narration stays on top and keeps the soundtrack; the bottom clip is muted and
          loops if it&apos;s shorter.
        </p>
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
                    className="shrink-0 rounded p-1 text-white/25 transition-colors hover:text-red-400"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-[10px] text-white/40">
                  <select
                    value={overlay.position}
                    onChange={(e) =>
                      setOverlays((c) =>
                        c.map((o, j) =>
                          j === i ? { ...o, position: e.target.value as TextOverlay["position"] } : o
                        )
                      )
                    }
                    className="rounded border border-border bg-background px-1.5 py-1 text-white/70"
                  >
                    <option value="top">Top</option>
                    <option value="middle">Middle</option>
                    <option value="bottom">Bottom</option>
                  </select>
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
    <label className="flex items-center gap-1">
      {label}
      <input
        type="number"
        min={0}
        step={0.1}
        value={(ms / 1000).toFixed(1)}
        onChange={(e) => onChange(Math.max(Math.round(Number(e.target.value) * 1000), 0))}
        className="w-14 rounded border border-border bg-background px-1.5 py-1 text-white/70"
      />
      s
    </label>
  );
}
