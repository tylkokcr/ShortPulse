"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  FileText,
  Palette,
  Clock,
  Music as MusicIcon,
  Wand2,
  ArrowRight,
  Coins,
  ChevronRight,
  Upload,
} from "lucide-react";
import clsx from "clsx";
import { Link, useRouter } from "@/i18n/navigation";
import { createProject, InsufficientCreditsError } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { AppShell } from "@/components/layout/AppShell";
import { ScriptEditor } from "@/components/editor/ScriptEditor";
import { DurationSelector } from "@/components/editor/DurationSelector";
import { LanguageSelector } from "@/components/editor/LanguageSelector";
import { OutroToggle } from "@/components/editor/OutroToggle";
import { CensorToggle } from "@/components/editor/CensorToggle";
import { VisualSelector } from "@/components/visual/VisualSelector";
import { CaptionStyleSelector } from "@/components/editor/CaptionStyleSelector";
import { CaptionPlacement } from "@/components/editor/CaptionPlacement";
import { presetById } from "@/lib/captionStyles";
import { ArtStyleSelector } from "@/components/editor/ArtStyleSelector";
import { NegativePrompt } from "@/components/editor/NegativePrompt";
import { AspectRatioSelector } from "@/components/editor/AspectRatioSelector";
import { MusicSelector } from "@/components/editor/MusicSelector";
import { VoiceSelector } from "@/components/editor/VoiceSelector";
import { RenderSummary } from "@/components/editor/RenderSummary";
import { UploadPanel } from "@/components/editor/UploadPanel";
import { StartFromExample } from "@/components/editor/StartFromExample";
import { SettingsDrawer } from "@/components/editor/SettingsDrawer";
import { RequireAuth } from "@/components/auth/RequireAuth";

export default function HomePage() {
  return (
    <RequireAuth>
      <CreateVideo />
    </RequireAuth>
  );
}

type Mode = "generate" | "upload";

/** The emphasised span inside a heading. `t.rich` hands the tag's contents
 *  back as chunks, which keeps the accented word *inside* the sentence —
 *  the alternative is splitting each heading into three keys and asking a
 *  translator to keep the word order the English happened to have. */
const accent = (chunks: React.ReactNode) => (
  <span className="text-accent-emphasis">{chunks}</span>
);

/** The four groups the drawer holds, in the order it stacks them. The
 *  rows on the page and the sections inside the panel are drawn from
 *  this one list, so a group cannot exist in the summary and not in the
 *  panel it claims to open. */
const GROUPS = [
  { id: "look", icon: Palette },
  { id: "length", icon: Clock },
  { id: "audio", icon: MusicIcon },
  { id: "finishing", icon: Wand2 },
] as const;

type GroupId = (typeof GROUPS)[number]["id"];

function CreateVideo() {
  const t = useTranslations("studio");
  const router = useRouter();
  const { draft, setDraft, toProjectConfig, credits } = useShortPulseStore();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("generate");
  // Which group the panel is scrolled to, and null for closed. One piece
  // of state rather than an open flag beside a selection: "open at
  // nothing" is not a state this can be in.
  const [drawerGroup, setDrawerGroup] = useState<GroupId | null>(null);

  const canSubmit =
    draft.topic.trim().length > 0 &&
    !submitting &&
    (draft.visualMode !== "ai_video" || draft.aiVideoAcknowledged);

  async function handleGenerate() {
    setSubmitting(true);
    setError(null);
    try {
      const project = await createProject(toProjectConfig());
      router.push(`/project/${project.config.id}`);
    } catch (err) {
      setError(
        err instanceof InsufficientCreditsError
          ? t("errors.insufficient", { required: err.required, balance: err.balance })
          : err instanceof Error
            ? err.message
            : t("errors.createFailed")
      );
      setSubmitting(false);
    }
  }

  // Quoted from the same table the backend charges from, so the number
  // shown here is the number taken. Absent on a self-hosted install.
  const price = credits?.enabled
    ? credits.pricing[`${draft.visualMode}:${draft.videoLength}`]
    : undefined;

  const lengthLabel = t(`length.${draft.videoLength}`);
  const musicLabel = draft.musicEnabled
    ? (draft.musicTrackId ?? t("summary.defaultTrack"))
    : t("summary.musicOff");
  // The id is a repo path; its second-to-last segment is the speaker name.
  const voiceLabel = draft.voiceId
    ? (draft.voiceId.split("/").at(-2) ?? t("summary.voiceFallback"))
    : t("summary.defaultVoice");

  // The fields themselves. Plain JSX rather than components per group:
  // every selector already reads the draft from the store, so there is
  // no state to thread and nothing here to re-render around.
  const GROUP_FIELDS: Record<GroupId, React.ReactNode> = {
    look: (
      <>
        <Field label={t("fields.aspectRatio")}>
          <AspectRatioSelector />
        </Field>
        <Field label={t("fields.language")}>
          <LanguageSelector />
        </Field>
        <Field label={t("fields.visualStyle")}>
          <VisualSelector />
        </Field>
        <Field label={t("fields.artStyle")}>
          <ArtStyleSelector />
        </Field>
        <Field label={t("fields.negativePrompt")}>
          <NegativePrompt />
        </Field>
        <Field label={t("fields.captionStyle")}>
          <CaptionStyleSelector />
          {/* Placement below the looks rather than beside them: you pick a
              style, then decide where it sits — and it survives changing
              your mind about the style. */}
          <CaptionPlacement
            className="mt-3"
            position={draft.captionPosition}
            fontSize={draft.captionFontSize ?? presetById(draft.captionPreset).style.font_size}
            onChange={({ position, fontSize }) =>
              setDraft({ captionPosition: position, captionFontSize: fontSize })
            }
          />
        </Field>
      </>
    ),
    length: <DurationSelector />,
    audio: (
      <>
        <Field label={t("fields.voice")}>
          <VoiceSelector />
        </Field>
        <Field label={t("fields.music")}>
          <MusicSelector />
        </Field>
      </>
    ),
    finishing: (
      <>
        <OutroToggle />
        <CensorToggle
          className="border-t border-border pt-4"
          checked={draft.censorProfanity}
          onChange={(censorProfanity) => setDraft({ censorProfanity })}
        />
      </>
    ),
  };

  const summaries: Record<GroupId, string> = {
    look: `${draft.aspectRatio} · ${draft.language.toUpperCase()} · ${draft.artStyle} · ${draft.captionPreset}`,
    length: lengthLabel,
    audio: t("summary.audio", { voice: voiceLabel, music: musicLabel }),
    finishing: [
      draft.outroEnabled ? t("summary.outroOn") : t("summary.outroOff"),
      draft.censorProfanity ? t("censor.summaryOn") : t("censor.summaryOff"),
    ].join(" · "),
  };

  return (
    <AppShell
      section="studio"
      asideOpen={mode === "generate" && drawerGroup !== null}
      aside={
        mode === "generate" ? (
          <SettingsDrawer
            open={drawerGroup !== null}
            onClose={() => setDrawerGroup(null)}
            icon={GROUPS.find((g) => g.id === drawerGroup)?.icon}
            title={drawerGroup ? t(`groups.${drawerGroup}`) : ""}
          >
            {/* One group, not all four stacked. The rows on the page are
                the list — they stay visible and clickable beside the open
                panel, so switching group is one click and the panel never
                holds 1900px of scroll to get past two sections nobody
                asked for. */}
            {drawerGroup && GROUP_FIELDS[drawerGroup]}
          </SettingsDrawer>
        ) : undefined
      }
      footer={
        // Only the generate flow has one. The upload panel carries its own
        // button, because its cost and its enabled state depend on a file
        // rather than on the draft.
        // Two rows on a phone, one on a desktop. The price used to be
        // `hidden sm:flex`, which put the button that spends credits on
        // the one screen size that never showed what it costs.
        mode === "generate" ? (
          <div className="mx-auto flex max-w-5xl flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:px-6 sm:py-4">
          <p className="flex items-center gap-1.5 text-xs text-white/40">
            {price !== undefined ? (
              <>
                <Coins size={13} />
                <span className="text-white/70">{t("cost.credits", { count: price })}</span>
                {t("cost.remaining", { balance: credits?.balance ?? 0 })}
              </>
            ) : (
              t("cost.free")
            )}
          </p>
          <Button
            onClick={handleGenerate}
            disabled={!canSubmit}
            variant="gradient"
            className="ml-auto w-full sm:w-auto"
          >
            {submitting ? (
              t("cta.generating")
            ) : (
              <>
                {t("cta.generate")}
                <ArrowRight size={16} />
              </>
            )}
          </Button>
        </div>
        ) : undefined
      }
    >
        <div className="animate-fade-up flex flex-wrap items-end justify-between gap-4">
          <div>
            {mode === "generate" ? (
              <>
                <h1 className="text-3xl font-semibold tracking-tight">
                  {t.rich("generate.title", { accent })}
                </h1>
                <p className="mt-2 max-w-lg text-sm leading-relaxed text-white/50">
                  {t("generate.intro")}
                </p>
              </>
            ) : (
              <>
                <h1 className="mt-1.5 text-3xl font-semibold tracking-tight">
                  {t.rich("upload.title", { accent })}
                </h1>
                <p className="mt-2 max-w-lg text-sm leading-relaxed text-white/50">
                  {t("upload.intro")}
                </p>
              </>
            )}
          </div>
        </div>

        <ModeTabs mode={mode} onChange={setMode} />

        {mode === "upload" && (
          // No max-width any more: the panel now brings its own second
          // column, so constraining it here would leave the preview
          // squeezed against the form.
          <div className="animate-fade-up mt-8">
            <UploadPanel />
          </div>
        )}

        {/* Only while the topic is empty, which is the only time it is an
            answer to anything. Once something is typed the row would be
            four videos sitting between the user and the button, offering
            to overwrite what they just wrote. */}
        {mode === "generate" && !draft.topic.trim() && (
          <div className="animate-fade-up mt-8">
            <StartFromExample />
          </div>
        )}

        {mode === "generate" && (

        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_280px] lg:items-start">
          <div className="flex flex-col gap-4">
            <Card className="animate-fade-up flex flex-col gap-4 border-border-strong bg-surface-raised">
              <div className="flex items-center gap-2">
                <FileText size={14} className="text-accent" />
                <h2 className="text-sm font-semibold text-white/80">{t("idea")}</h2>
              </div>
              <ScriptEditor />
            </Card>

            {/* Steps two to five used to be four more accordions in this
                column and the page was 2900px tall. They are refinements
                with working defaults, so the row states what it is set to
                and the panel is where you change it. */}
            <div className="animate-fade-up flex flex-col gap-2" style={{ animationDelay: "60ms" }}>
              {GROUPS.map((group) => (
                <SettingRow
                  key={group.id}
                  icon={group.icon}
                  title={t(`groups.${group.id}`)}
                  summary={summaries[group.id]}
                  open={drawerGroup === group.id}
                  onClick={() => setDrawerGroup(group.id)}
                />
              ))}
            </div>

            {error && (
              <div className="flex flex-wrap items-center gap-3 rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                <span>{error}</span>
                {/* Telling someone they are short of credits without
                    offering the way to fix it is a dead end. */}
                {error.includes("credit") && (
                  <Link href="/credits" className="ml-auto">
                    <Button size="sm" variant="secondary">
                      {t("cta.topUp")}
                    </Button>
                  </Link>
                )}
              </div>
            )}
          </div>

          {/* Sticky so the cost and time estimate stay visible while the
              choices that change them are being made. */}
          <div className="animate-fade-up lg:sticky lg:top-6" style={{ animationDelay: "300ms" }}>
            <RenderSummary />
          </div>
        </div>
        )}

    </AppShell>
  );
}

/**
 * Two ways to get a captioned vertical video: describe one, or bring one.
 * Presented as a switch rather than two pages because the choice is the
 * first thing someone makes, and burying half the product behind a nav
 * link hides the half that needs no setup at all.
 */
function ModeTabs({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  const t = useTranslations("studio");
  const tabs: { id: Mode; label: string; icon: typeof FileText }[] = [
    { id: "generate", label: t("tabs.generate"), icon: Wand2 },
    // Names both things it does. Dubbing has been in here since it was
    // written — a language field inside this tab — and a tab promising
    // captions gave nobody a reason to open it and find out.
    { id: "upload", label: t("tabs.upload"), icon: Upload },
  ];

  return (
    // `flex` rather than `inline-flex` below sm so the two halves share the
    // width evenly instead of each wrapping its label onto a second line,
    // which is what "Generate from a topic" did at 390px.
    <div className="animate-fade-up mt-6 flex rounded-md border border-border bg-surface p-1 sm:inline-flex">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onChange(tab.id)}
          aria-pressed={mode === tab.id}
          className={clsx(
            "flex flex-1 items-center justify-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-[13px] font-medium transition-all duration-200 sm:flex-none sm:justify-start sm:px-4 sm:text-sm",
            mode === tab.id
              ? "bg-surface-raised text-white shadow-sm"
              : "text-white/50 hover:text-white/80"
          )}
        >
          <tab.icon size={15} />
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-white/70">{label}</label>
      {children}
    </div>
  );
}

/**
 * Collapsible step. Every section past the first two starts closed with
 * its current value in the header, so the form reads as a short summary
 * until you actually want to change something — the alternative is five
 * expanded panels of controls that mostly keep their defaults.
 */
/**
 * A setting group, as a line rather than a panel.
 *
 * Says what it is currently set to and opens the drawer at it. The
 * summary is the point: four of these stack into the height one closed
 * accordion used to take, and you can read the whole configuration
 * without opening anything.
 */
function SettingRow({
  icon: Icon,
  title,
  summary,
  open,
  onClick,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  summary: string;
  open: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={open}
      className={clsx(
        "group flex items-center gap-3 rounded-lg border px-4 py-3 text-left",
        "transition-[border-color,background-color] duration-200",
        open
          ? "border-accent/50 bg-accent/[0.06]"
          : "border-border hover:border-border-strong hover:bg-surface-hover"
      )}
    >
      <Icon size={14} className={clsx("shrink-0", open ? "text-accent" : "text-white/40")} />
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium">{title}</span>
        <span className="mt-0.5 block truncate text-xs text-white/40">{summary}</span>
      </span>
      <ChevronRight
        size={15}
        className={clsx(
          "shrink-0 transition-colors",
          open ? "text-accent" : "text-white/25 group-hover:text-white/50"
        )}
      />
    </button>
  );
}
