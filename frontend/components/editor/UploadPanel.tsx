"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Captions,
  FileVideo,
  Frame,
  Palette,
  Scissors,
  TriangleAlert,
  Upload,
  Wand2,
} from "lucide-react";
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
import { CaptionPlacement } from "./CaptionPlacement";
import { ClipTemplateSelector } from "./ClipTemplateSelector";
import { FieldDisclosure } from "./FieldDisclosure";
import { templateById, type ClipTemplate } from "@/lib/clipTemplates";
import type { AspectRatio } from "@/lib/types";
import { CensorToggle } from "./CensorToggle";
import { captionStyleFor, presetById } from "@/lib/captionStyles";
import { UploadPreview } from "./UploadPreview";
import { TimelineRange } from "@/components/ui/TimelineRange";
import { SettingRow } from "./SettingRow";
import { SettingsDrawer } from "./SettingsDrawer";

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

/**
 * The shortest stretch clips can come out of, mirroring the server's
 * `clipping.MIN_SOURCE_S`.
 *
 * Duplicated rather than fetched, like the file-size cap above it: both
 * exist so a request that is certain to be refused is not made in the
 * first place, and both are refused again on arrival. The number moving
 * on the server without moving here costs a 422 with a written reason,
 * not a wrong render.
 */
const MIN_WINDOW_MS = 2 * 60 * 1000;

/**
 * The panels, in the order the decisions get made.
 *
 * Same shape as the generate tab's, and three of the four names are its
 * names — two tabs of one screen disagreeing about how settings work
 * reads as two products. `cut` is the one that only exists here: it holds
 * the questions that only mean something once the video is being cut into
 * clips, and the row is not drawn at all otherwise.
 */
const UPLOAD_GROUPS = [
  { id: "format", icon: Frame },
  { id: "cut", icon: Scissors },
  { id: "look", icon: Palette },
  { id: "finishing", icon: Wand2 },
] as const;

type UploadGroupId = (typeof UPLOAD_GROUPS)[number]["id"];

function formatSize(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return mb >= 1000 ? `${(mb / 1024).toFixed(1)}GB` : `${mb.toFixed(0)}MB`;
}

/**
 * What the extraction will cost, by the same arithmetic the server uses.
 *
 * `Math.ceil`, a floor of one: a part-minute is never free and the
 * shortest legal stretch still costs something. Without a measured
 * duration there is no window to price, and the server will read the
 * whole file — so the quote falls back to what it charges for that,
 * which it cannot know until it has probed. One credit is the floor
 * either way, and the honest thing to show before a length is known.
 */
function clipPrice(
  windowMs: [number, number],
  durationMs: number | null,
  secondsPerCredit: number
): number {
  const spanMs = durationMs === null ? 0 : Math.max(windowMs[1] - windowMs[0], 0);
  return Math.max(1, Math.ceil(spanMs / 1000 / secondsPerCredit));
}

export function UploadPanel({
  onAsideOpenChange,
}: {
  /** Told when this tab's settings drawer opens or closes, so the shell
   *  can give it a column of its own on a wide enough window. The panel
   *  owns the drawer because it owns every value in it; the shell only
   *  needs to know whether one is showing. */
  onAsideOpenChange?: (open: boolean) => void;
}) {
  const t = useTranslations("studio.upload");
  // The credit line and the free-install line are shared with the
  // generate tab, so they live one level up rather than twice.
  const ts = useTranslations("studio");
  // The group names are the generate tab's, shared deliberately — see
  // UPLOAD_GROUPS.
  const tg = useTranslations("studio.groups");
  const router = useRouter();
  const { draft, setDraft, credits } = useShortPulseStore();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Local rather than in the draft store: the target language is a
  // property of this one action, not of a project that outlives it.
  const [dubLanguage, setDubLanguage] = useState("");
  const [censor, setCensor] = useState(false);
  const [focus, setFocus] = useState("");
  // Nothing is lit until the user picks one. A template is a shortcut,
  // not a default that silently applied.
  const [template, setTemplate] = useState<string | null>(null);
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>("9:16");
  // Zero means "caption it whole". The two are mutually exclusive — the
  // API refuses both together rather than quietly doing one — so choosing
  // either clears the other here instead of letting the server say no
  // after the file has been uploaded.
  const [clipCount, setClipCount] = useState(0);
  // Null until the browser has read the file's header, and again if it
  // cannot: `null` means "no window", not "zero seconds".
  const [durationMs, setDurationMs] = useState<number | null>(null);
  // The whole file until the user says otherwise. Sent as two concrete
  // numbers either way — the server resolves them against its own probe,
  // which is the only duration that decides anything.
  const [windowMs, setWindowMs] = useState<[number, number]>([0, 0]);
  const [drawerGroup, setDrawerGroup] = useState<UploadGroupId | null>(null);

  const asideOpen = drawerGroup !== null;
  useEffect(() => {
    onAsideOpenChange?.(asideOpen);
    // Leaving the tab with a panel open would otherwise keep the margin.
    return () => onAsideOpenChange?.(false);
  }, [asideOpen, onAsideOpenChange]);

  // Quoted from the table the API serves, which is the one the backend
  // charges from — the panel used to print "1 credit" whatever was
  // chosen, which was wrong about a dub and about every clip count.
  //
  // An extraction is the one price that is not in the table, because it
  // depends on how much of the source is read. The table publishes the
  // rate and this runs the same sum `credits.clip_cost` does. Both halves
  // move together or the panel promises a number the server will not
  // charge.
  const secondsPerCredit = credits?.pricing?.["upload:clip_seconds_per_credit"] ?? 120;
  const price = clipCount
    ? clipPrice(windowMs, durationMs, secondsPerCredit)
    : (credits?.pricing?.[dubLanguage ? "upload:dub" : "upload:caption"] ?? 1);

  function choose(next: File | null) {
    setError(null);
    if (!next) return;
    // Checked here as well as on the server so a 200MB upload isn't sent
    // over a phone connection just to be refused at the end of it.
    if (next.size > MAX_BYTES) {
      setError(`That file is ${formatSize(next.size)}. The limit is 200MB.`);
      return;
    }
    // Belongs to the old file. Cleared here rather than in an effect so
    // the control disappears with the video it described, instead of
    // sitting on a stale length until the new header is read.
    setDurationMs(null);
    setWindowMs([0, 0]);
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
          // `captionStyleFor`, not the preset's own style: the placement
          // control writes position and size onto the draft, and reading
          // the preset directly threw both away. The same line had the
          // same shape of bug once before — it used to hardcode Classic —
          // which is why the composed style now has exactly one home.
          subtitles: captionStyleFor(draft),
          censorProfanity: censor,
          clipGuidance: focus,
          aspectRatio,
          // Only when there is a real one to send. Without a measured
          // duration the pair would be [0, 0], which is not "the whole
          // video" — it is an empty window the server would refuse.
          ...(clipCount > 0 && durationMs !== null
            ? { clipFromS: windowMs[0] / 1000, clipToS: windowMs[1] / 1000 }
            : {}),
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

  /**
   * Going back to "caption it whole" gives up the frame with it.
   *
   * The tile grid dims the non-vertical looks, but a look picked while
   * clips were on stays picked — and the API refuses a frame on a caption
   * job, which would be a 422 arriving after a 200MB upload. The caption
   * style stays exactly as it is: a template is a shortcut, so only the
   * part that is no longer on offer is taken back.
   */
  function dropFrameChoice() {
    if (aspectRatio === "9:16") return;
    setAspectRatio("9:16");
    setTemplate(null);
  }

  function applyTemplate(picked: ClipTemplate) {
    setTemplate(picked.id);
    setAspectRatio(picked.aspectRatio);
    // Written onto the draft, not held here: the caption pickers below
    // read from the draft, so this is what makes the tile and the
    // fine-tune controls agree instead of quietly disagreeing.
    setDraft({
      captionPreset: picked.captionPreset,
      captionPosition: picked.captionPosition,
      captionFontSize: picked.captionFontSize,
    });
  }


  // The fields, by group. Plain JSX for the same reason the generate tab
  // uses it: every control here already reads what it needs from this
  // component's state or the draft, so there is nothing to thread.
  // What each row says it is set to, so the four of them read as the
  // whole configuration without opening anything.
  const summaries: Record<UploadGroupId, string> = {
    format: draft.language.toUpperCase(),
    cut:
      durationMs !== null && (windowMs[1] - windowMs[0]) < durationMs
        ? `${clock(windowMs[0])}–${clock(windowMs[1])}`
        : t("cutWholeSummary"),
    look: [template ? templateById(template).name : t("lookCustom"), draft.captionPreset]
      .filter(Boolean)
      .join(" · "),
    finishing: censor ? ts("censor.summaryOn") : ts("censor.summaryOff"),
  };

  const GROUP_FIELDS: Record<UploadGroupId, React.ReactNode> = {
    format: (
      <>
        <div>
          <label className="mb-1.5 block text-sm font-medium text-white/70">{t("spokenLanguage")}</label>
          <LanguageSelector />
          <p className="mt-1.5 text-xs text-white/40">{t("spokenLanguageHint")}</p>
        </div>
      </>
    ),
    cut: (
      <>
        {/* Only when there is a length to take a stretch out of, and
            only when there is something to take. A browser that will not
            say how long the file is (a stream, a container it has to
            seek to measure) gets no control and sends no window — the
            server then reads the whole thing, exactly as before. */}
        {clipCount > 0 && durationMs !== null && durationMs > MIN_WINDOW_MS && (
          <div>
            <span className="mb-1.5 block text-sm font-medium text-white/70">
              {t("window")}
            </span>
            <TimelineRange
              startMs={windowMs[0]}
              endMs={windowMs[1]}
              durationMs={durationMs}
              minSpanMs={MIN_WINDOW_MS}
              onChange={(start, end) => setWindowMs([start, end])}
              labels={{ start: t("windowStart"), end: t("windowEnd") }}
            />
            <p className="mt-1.5 text-xs text-white/40">
              {t("windowHint", {
                minutes: Math.round(MIN_WINDOW_MS / 60000),
                perCredit: Math.round(secondsPerCredit / 60),
              })}
            </p>
          </div>
        )}
        {/* Only with clips: there is nothing for it to steer otherwise,
            and a field that silently does nothing is worse than one that
            is not there. */}
        {clipCount > 0 && (
          <div>
            <label
              htmlFor="clip-focus"
              className="mb-1.5 block text-sm font-medium text-white/70"
            >
              {t("focus")}
            </label>
            <input
              id="clip-focus"
              value={focus}
              maxLength={300}
              onChange={(event) => setFocus(event.target.value)}
              placeholder={t("focusPlaceholder")}
              className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none transition-colors focus:border-accent"
            />
            <p className="mt-1.5 text-xs text-white/40">{t("focusHint")}</p>
          </div>
        )}
      </>
    ),
    look: (
      <>
        <ClipTemplateSelector
          selected={template}
          onSelect={applyTemplate}
          framesAllowed={clipCount > 0}
        />
      
        {/* Behind its own value, as on the generate tab: eleven preset
            tiles and a placement control is the biggest block in this
            panel, and the template above has usually just answered it. */}
        <FieldDisclosure label={t("captionStyle")} value={draft.captionPreset}>
          <CaptionStyleSelector />
          {/* Here too, not only on the generate tab. The draft is shared,
              so the placement chosen there already applied to an upload —
              it was just invisible on the panel it applied to, which is
              how it went unnoticed that the value was being dropped. */}
          <CaptionPlacement
            className="mt-3"
            position={draft.captionPosition}
            fontSize={draft.captionFontSize ?? presetById(draft.captionPreset).style.font_size}
            onChange={({ position, fontSize }) =>
              setDraft({ captionPosition: position, captionFontSize: fontSize })
            }
          />
        </FieldDisclosure>
      </>
    ),
    // Here as well as in the generate tab: somebody captioning their own
    // recording is the case this matters most for — they cannot re-write
    // what was already said.
    finishing: <CensorToggle checked={censor} onChange={setCensor} />,
  };

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
          <label className="mb-1.5 block text-sm font-medium text-white/70">{t("clips")}</label>
          <div className="flex flex-wrap gap-2">
            {[0, 2, 3, 4, 5].map((count) => (
              <button
                key={count}
                type="button"
                onClick={() => {
                  setClipCount(count);
                  if (count) setDubLanguage("");
                  else dropFrameChoice();
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

        {/* Everything past the file and what to do with it. Four rows
            where there used to be six expanded sections and 2238px of
            scroll — the same trade the generate tab made, and the same
            rule: a row says what it is set to, and the drawer is where
            you change it. */}
        <div className="flex flex-col gap-2">
          {UPLOAD_GROUPS.map((group) => {
            // Nothing in it applies until the video is being cut up, and
            // a row that opens an empty panel is worse than no row.
            if (group.id === "cut" && clipCount === 0) return null;
            return (
              <SettingRow
                key={group.id}
                icon={group.icon}
                title={tg(group.id)}
                summary={summaries[group.id]}
                open={drawerGroup === group.id}
                onClick={() => setDrawerGroup(group.id)}
              />
            );
          })}
        </div>
      </Card>

      <SettingsDrawer
        open={drawerGroup !== null}
        onClose={() => setDrawerGroup(null)}
        icon={UPLOAD_GROUPS.find((g) => g.id === drawerGroup)?.icon}
        title={drawerGroup ? tg(drawerGroup) : ""}
      >
        {drawerGroup && GROUP_FIELDS[drawerGroup]}
      </SettingsDrawer>

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

      <UploadPreview
        file={file}
        aspectRatio={aspectRatio}
        captionPosition={draft.captionPosition}
        onDuration={(seconds) => {
          const ms = seconds === null ? null : Math.round(seconds * 1000);
          setDurationMs(ms);
          // Defaults to the whole file, so a user who never touches the
          // control gets what they got before it existed.
          setWindowMs([0, ms ?? 0]);
        }}
      />
    </div>
  );
}

/** m:ss, for the window summary on the row. */
function clock(ms: number): string {
  const total = Math.round(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}
