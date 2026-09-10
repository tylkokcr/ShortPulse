"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  FileText,
  Palette,
  Clock,
  Music as MusicIcon,
  Wand2,
  ArrowRight,
  Coins,
  ChevronDown,
  Upload,
} from "lucide-react";
import clsx from "clsx";
import { createProject, InsufficientCreditsError } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { ScriptEditor } from "@/components/editor/ScriptEditor";
import { DurationSelector } from "@/components/editor/DurationSelector";
import { LanguageSelector } from "@/components/editor/LanguageSelector";
import { OutroToggle } from "@/components/editor/OutroToggle";
import { VisualSelector } from "@/components/visual/VisualSelector";
import { CaptionStyleSelector } from "@/components/editor/CaptionStyleSelector";
import { ArtStyleSelector } from "@/components/editor/ArtStyleSelector";
import { NegativePrompt } from "@/components/editor/NegativePrompt";
import { AspectRatioSelector } from "@/components/editor/AspectRatioSelector";
import { MusicSelector } from "@/components/editor/MusicSelector";
import { VoiceSelector } from "@/components/editor/VoiceSelector";
import { RenderSummary } from "@/components/editor/RenderSummary";
import { UploadPanel } from "@/components/editor/UploadPanel";
import { AccountBar } from "@/components/auth/AccountBar";
import { RequireAuth } from "@/components/auth/RequireAuth";

export default function HomePage() {
  return (
    <RequireAuth>
      <CreateVideo />
    </RequireAuth>
  );
}

type Mode = "generate" | "upload";

function CreateVideo() {
  const router = useRouter();
  const { draft, toProjectConfig, credits } = useShortPulseStore();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("generate");

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
          ? `This render costs ${err.required} credits and you have ${err.balance}.`
          : err instanceof Error
            ? err.message
            : "Failed to create project"
      );
      setSubmitting(false);
    }
  }

  // Quoted from the same table the backend charges from, so the number
  // shown here is the number taken. Absent on a self-hosted install.
  const price = credits?.enabled
    ? credits.pricing[`${draft.visualMode}:${draft.videoLength}`]
    : undefined;

  const lengthLabel = { short: "Short", medium: "Medium", long: "Long" }[draft.videoLength];
  const musicLabel = draft.musicEnabled ? (draft.musicTrackId ?? "default track") : "off";
  // The id is a repo path; its second-to-last segment is the speaker name.
  const voiceLabel = draft.voiceId ? (draft.voiceId.split("/").at(-2) ?? "Voice") : "Default voice";

  return (
    <div className="relative min-h-screen">
      {/* Atmosphere over the heading, nothing over the controls — see
          .stars-quiet. The height ends around where the first section
          starts, so the form never has anything behind it. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[620px]">
        <div className="stars-field stars-quiet" aria-hidden>
          <div className="stars-a" />
          <div className="stars-b" />
          <div className="stars-c" />
        </div>
      </div>

      <SiteHeader right={<AccountBar />} showLibrary />

      <main className="mx-auto max-w-5xl px-6 pb-32 pt-10">
        <div className="animate-fade-up flex flex-wrap items-end justify-between gap-4">
          <div>
            <span className="font-mono text-xs uppercase tracking-widest text-accent">Studio</span>
            {mode === "generate" ? (
              <>
                <h1 className="mt-1.5 text-3xl font-semibold tracking-tight">
                  What&apos;s this <span className="text-accent-emphasis">video</span> about?
                </h1>
                <p className="mt-2 max-w-lg text-sm leading-relaxed text-white/50">
                  Give it a topic — everything below already has a sensible default, so you can hit
                  generate now and come back to fine-tune later.
                </p>
              </>
            ) : (
              <>
                <h1 className="mt-1.5 text-3xl font-semibold tracking-tight">
                  Caption a video you <span className="text-accent-emphasis">already have</span>.
                </h1>
                <p className="mt-2 max-w-lg text-sm leading-relaxed text-white/50">
                  Upload it and every spoken word gets timed and burned in — the same captions the
                  generator produces, on your own footage.
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

        {mode === "generate" && (

        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_280px] lg:items-start">
          <div className="flex flex-col gap-4">
            <Section
              icon={FileText}
              step={1}
              title="The idea"
              summary={draft.topic.trim() || "No topic yet"}
              defaultOpen
              delay={0}
            >
              <ScriptEditor />
            </Section>

            <Section
              icon={Palette}
              step={2}
              title="Look & language"
              summary={`${draft.aspectRatio} · ${draft.language.toUpperCase()} · ${draft.artStyle} · ${draft.captionPreset}`}
              defaultOpen
              delay={60}
            >
              <div className="flex flex-col gap-5">
                <Field label="Aspect ratio">
                  <AspectRatioSelector />
                </Field>
                <Field label="Language">
                  <LanguageSelector />
                </Field>
                <Field label="Visual style">
                  <VisualSelector />
                </Field>
                <Field label="Art style">
                  <ArtStyleSelector />
                </Field>
                <Field label="Keep out of frame">
                  <NegativePrompt />
                </Field>
                <Field label="Caption style">
                  <CaptionStyleSelector />
                </Field>
              </div>
            </Section>

            <Section
              icon={Clock}
              step={3}
              title="Length"
              summary={lengthLabel}
              delay={120}
            >
              <DurationSelector />
            </Section>

            <Section
              icon={MusicIcon}
              step={4}
              title="Audio"
              summary={`${voiceLabel} · music: ${musicLabel}`}
              delay={180}
            >
              <div className="flex flex-col gap-5">
                <Field label="Narrator voice">
                  <VoiceSelector />
                </Field>
                <Field label="Background music">
                  <MusicSelector />
                </Field>
              </div>
            </Section>

            <Section
              icon={Wand2}
              step={5}
              title="Finishing touches"
              summary={draft.outroEnabled ? "Outro card on" : "Outro card off"}
              delay={240}
            >
              <OutroToggle />
            </Section>

            {error && (
              <div className="flex flex-wrap items-center gap-3 rounded-md border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
                <span>{error}</span>
                {/* Telling someone they are short of credits without
                    offering the way to fix it is a dead end. */}
                {error.includes("credit") && (
                  <Link href="/credits" className="ml-auto">
                    <Button size="sm" variant="secondary">
                      Top up
                    </Button>
                  </Link>
                )}
              </div>
            )}
          </div>

          {/* Sticky so the cost and time estimate stay visible while the
              choices that change them are being made. */}
          <div className="animate-fade-up lg:sticky lg:top-24" style={{ animationDelay: "300ms" }}>
            <RenderSummary />
          </div>
        </div>
        )}
      </main>

      {/* Only the generate flow has a sticky action bar. The upload panel
          carries its own button, because its cost and its enabled state
          depend on a file rather than on the draft. */}
      {mode === "generate" && (
      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border/60 bg-background/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-4">
          <p className="hidden items-center gap-1.5 text-xs text-white/40 sm:flex">
            {price !== undefined ? (
              <>
                <Coins size={13} />
                <span className="text-white/70">
                  {price} credit{price === 1 ? "" : "s"}
                </span>
                · {credits?.balance ?? 0} remaining
              </>
            ) : (
              "Free · runs on this machine"
            )}
          </p>
          <Button
            onClick={handleGenerate}
            disabled={!canSubmit}
            variant="gradient"
            className="ml-auto w-full sm:w-auto"
          >
            {submitting ? (
              "Starting render..."
            ) : (
              <>
                Generate video
                <ArrowRight size={16} />
              </>
            )}
          </Button>
        </div>
      </div>
      )}
    </div>
  );
}

/**
 * Two ways to get a captioned vertical video: describe one, or bring one.
 * Presented as a switch rather than two pages because the choice is the
 * first thing someone makes, and burying half the product behind a nav
 * link hides the half that needs no setup at all.
 */
function ModeTabs({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  const tabs: { id: Mode; label: string; icon: typeof FileText }[] = [
    { id: "generate", label: "Generate from a topic", icon: Wand2 },
    { id: "upload", label: "Caption my video", icon: Upload },
  ];

  return (
    <div className="animate-fade-up mt-6 inline-flex rounded-md border border-border bg-surface p-1">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onChange(tab.id)}
          aria-pressed={mode === tab.id}
          className={clsx(
            "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all duration-200",
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
function Section({
  icon: Icon,
  step,
  title,
  summary,
  children,
  defaultOpen = false,
  delay = 0,
}: {
  icon: typeof FileText;
  step: number;
  title: string;
  summary: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  delay?: number;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <Card
      className={clsx(
        "animate-fade-up relative overflow-hidden p-0 transition-all duration-300",
        open
          ? "border-border-strong bg-surface-raised shadow-lg shadow-black/20"
          : "hover:border-border-strong"
      )}
      style={{ animationDelay: `${delay}ms` }}
    >
      {/* Lit rail marks the section you're editing without shouting. */}
      <span
        aria-hidden
        className={clsx(
          "absolute inset-y-0 left-0 w-[2px] transition-opacity duration-300",
          open ? "bg-accent opacity-100" : "opacity-0"
        )}
      />

      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="group flex w-full items-center gap-3 px-5 py-4 text-left"
      >
        <span
          className={clsx(
            "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border font-mono text-[11px] transition-colors duration-200",
            open
              ? "border-accent/40 bg-accent/15 text-accent"
              : "border-border bg-background text-white/40 group-hover:text-white/70"
          )}
        >
          {step}
        </span>
        <Icon
          size={15}
          className={clsx(
            "shrink-0 transition-colors duration-200",
            open ? "text-accent" : "text-white/40 group-hover:text-white/70"
          )}
        />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold">{title}</span>
          {/* The closed row is the one people actually read — four of the
              five sections are closed at any moment — so the value it
              carries can't be fainter than the label above it. */}
          {!open && (
            <span className="mt-0.5 block truncate text-xs text-white/55">{summary}</span>
          )}
        </span>
        <ChevronDown
          size={16}
          className={clsx(
            "shrink-0 text-white/40 transition-transform duration-300",
            open && "rotate-180 text-accent"
          )}
        />
      </button>

      {open && <div className="animate-fade-in px-5 pb-5">{children}</div>}
    </Card>
  );
}
