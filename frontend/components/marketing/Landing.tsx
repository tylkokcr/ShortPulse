"use client";

import {
  FileText,
  Mic,
  Captions,
  Image as ImageIcon,
  Film,
  Music,
  Globe,
  Server,
  Lock,
  Coins,
  Check,
  X,
  Github,
  Sparkles,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { LogoMark } from "@/components/ui/Logo";
import { useSignupCredits } from "@/lib/signupCredits";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";
import { GridBackdrop } from "@/components/ui/GridBackdrop";
import { WaveFloor } from "./WaveFloor";
import { WordReveal } from "@/components/ui/WordReveal";
import { CountUp } from "@/components/ui/CountUp";
import { PhoneFrame } from "./PhoneFrame";
import { Examples } from "./Examples";
import { Pricing } from "./Pricing";
import { BuiltOn } from "./BuiltOn";
import { CaptionStyles } from "./CaptionStyles";
import { ArtStyles } from "./ArtStyles";
import { HowItWorks } from "./HowItWorks";
import { EditorShowcase } from "./EditorShowcase";
import { Faq } from "./Faq";

const REPO_URL = "https://github.com/tylkokcr/ShortPulse";

// Fragment ids are addresses, not copy — they stay English in every
// language so a link shared from the Turkish page still opens the
// right section of the German one.
const ANCHORS = {
  examples: "#examples",
  howItWorks: "#how-it-works",
  pricing: "#pricing",
  faq: "#faq",
} as const;

// Numbers a visitor reads as being about *this* service, so nothing here
// may depend on how the deployment happens to be configured. "3 visual
// engines" was true of the repository and false of the site the moment
// ai_video was refused here — and this component is static, with no way
// to know. Art styles are in the code and the same everywhere.
// Only the icon and the order live here now. The number in each stat is
// still code — "9" is tied to LANGUAGE_OPTIONS and a translator must not
// be able to change it, which is exactly what putting it in a catalogue
// would allow.
const STAT_VALUES = (signupCredits: number) => ["9", "6", String(signupCredits), "MIT"];
const STAT_KEYS = ["languages", "artStyles", "freeCredits", "licensed"] as const;

const PIPELINE_ICONS = [FileText, Mic, Captions, ImageIcon, Film];
const PIPELINE_KEYS = ["script", "voiceover", "captions", "visuals", "assemble"] as const;

const FEATURE_ICONS = [Lock, Captions, Globe, Music, ImageIcon, Sparkles];
const FEATURE_KEYS = [
  "local", "captions", "languages", "music", "stills", "outro",
] as const;

const COMPARISON_KEYS = [
  "price", "idle", "source", "where", "custom", "credits",
] as const;

const LIMITATION_KEYS = ["stills", "aiVideo", "llm", "stock"] as const;

export function Landing() {
  const signupCredits = useSignupCredits();
  const t = useTranslations("landing");
  const statValues = STAT_VALUES(signupCredits);

  return (
    <div className="relative min-h-screen">
      <GridBackdrop />

      <SiteHeader
        right={
          <>
            {(["examples", "howItWorks", "pricing", "faq"] as const).map((key) => (
              <a
                key={key}
                href={ANCHORS[key]}
                className="hidden text-sm text-white/50 transition-colors hover:text-white md:block"
              >
                {t(`nav.${key}`)}
              </a>
            ))}
            <Link href="/login">
              <Button variant="secondary" size="sm">
                {t("signIn")}
              </Button>
            </Link>
          </>
        }
      />

      {/* Hero */}
      <section className="mx-auto grid max-w-6xl gap-12 px-6 pb-20 pt-16 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:pt-24">
        <div className="flex flex-col gap-6">
          <Badge tone="accent" className="w-fit">
            {t("badge")}
          </Badge>
          <WordReveal className="text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl">
            {/* Rich rather than two strings: which words carry the accent
                colour is a property of the sentence, and a language that
                orders it differently has to be able to move the emphasis
                with the phrase. */}
            {t.rich("headline", {
              accent: (chunks) => <span className="text-accent-emphasis">{chunks}</span>,
            })}
          </WordReveal>
          <p className="max-w-lg text-lg leading-relaxed text-white/60">
            {t("sub")}
          </p>

          {/* Two across on a phone: four columns leaves ~73px each, which
              wraps "visual engines" onto two lines and makes the row read
              as noise rather than as four facts. */}
          <dl className="grid grid-cols-2 gap-4 border-t border-border pt-6 sm:grid-cols-4">
            {STAT_KEYS.map((key, i) => (
              <div key={key} className="flex flex-col gap-1">
                <dt className="sr-only">{t(`stats.${key}`)}</dt>
                <dd className="font-mono text-xl font-medium text-white sm:text-2xl">
                  <CountUp value={statValues[i]} />
                </dd>
                <span className="text-xs text-white/40">{t(`stats.${key}`)}</span>
              </div>
            ))}
          </dl>

          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Link href="/login">
              <Button variant="gradient" size="lg">
                {t("startCreating")}
              </Button>
            </Link>
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              <Button variant="outline" size="lg">
                <Github size={18} />
                {t("viewSource")}
              </Button>
            </a>
          </div>
        </div>

        {/* The sign-in card used to sit under this mock. It moved to
            /login when identity providers arrived: the browser leaves the
            app to visit Google or Facebook and has to come back to a page
            that can report what happened, and "the middle of the landing
            page" is not that place. */}
        <div className="flex justify-center">
          <PreviewMock />
        </div>
      </section>

      {/* Examples — real renders, placed before any further claims */}
      <Reveal id="examples" className="scroll-mt-20">
        <Examples />
      </Reveal>

      <BuiltOn />

      <Reveal>
        <HowItWorks />
      </Reveal>

      <Reveal>
        <ArtStyles />
      </Reveal>

      <Reveal>
        <CaptionStyles />
      </Reveal>

      <Reveal>
        <EditorShowcase />
      </Reveal>

      {/* Pipeline */}
      <Reveal>
        <section className="mx-auto max-w-6xl px-6 py-16">
          <SectionHeading eyebrow={t("pipeline.eyebrow")} title={t("pipeline.title")} />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {PIPELINE_KEYS.map((key, i) => {
              const Icon = PIPELINE_ICONS[i];
              return (
              <Reveal key={key} delay={i * 70} className="h-full">
                <Card interactive className="flex h-full flex-col gap-3 bg-grain">
                  <div className="flex items-center justify-between">
                    <Icon size={20} className="text-accent" />
                    <span className="font-mono text-xs text-white/30">0{i + 1}</span>
                  </div>
                  <h3 className="text-sm font-semibold">{t(`pipeline.${key}.title`)}</h3>
                  <p className="text-xs leading-relaxed text-white/50">{t(`pipeline.${key}.detail`)}</p>
                </Card>
              </Reveal>
              );
            })}
          </div>
        </section>
      </Reveal>

      {/* Features */}
      <Reveal>
        <section className="mx-auto max-w-6xl px-6 py-16">
          <SectionHeading eyebrow={t("features.eyebrow")} title={t("features.title")} />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURE_KEYS.map((key, i) => {
              const Icon = FEATURE_ICONS[i];
              return (
              <Reveal key={key} delay={(i % 3) * 70} className="h-full">
                <Card className="flex h-full flex-col gap-3">
                  <Icon size={20} className="text-white/40" />
                  <h3 className="text-sm font-semibold">{t(`features.${key}.title`)}</h3>
                  <p className="text-xs leading-relaxed text-white/50">{t(`features.${key}.detail`)}</p>
                </Card>
              </Reveal>
              );
            })}
          </div>
        </section>
      </Reveal>

      {/* Comparison */}
      <Reveal>
        <section className="mx-auto max-w-6xl px-6 py-16">
          <SectionHeading eyebrow={t("comparison.eyebrow")} title={t("comparison.title")} />
          <Card className="overflow-x-auto p-0">
            <table className="w-full min-w-[560px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-white/40">
                  <th className="px-5 py-3 font-medium"></th>
                  <th className="px-5 py-3 font-medium text-white/70">
                    <span className="inline-flex items-center gap-1.5">
                      <LogoMark className="h-4 w-4" /> ShortPulse
                    </span>
                  </th>
                  <th className="px-5 py-3 font-medium">{t("comparison.them")}</th>
                </tr>
              </thead>
              <tbody>
                {COMPARISON_KEYS.map((key) => (
                  <tr key={key} className="border-b border-border/60 last:border-0">
                    <td className="px-5 py-3.5 text-white/50">{t(`comparison.${key}.label`)}</td>
                    <td className="px-5 py-3.5 font-medium text-white">
                      <span className="inline-flex items-center gap-1.5">
                        <Check size={14} className="text-accent" />
                        {t(`comparison.${key}.us`)}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-white/40">
                      <span className="inline-flex items-center gap-1.5">
                        <X size={14} className="text-white/25" />
                        {t(`comparison.${key}.them`)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </section>
      </Reveal>

      {/* Pricing */}
      <Reveal className="scroll-mt-20">
        <Pricing />
      </Reveal>

      {/* Honesty / limitations */}
      <Reveal>
        <section className="mx-auto max-w-6xl px-6 py-16">
          <Card className="flex flex-col gap-5 border-border-strong bg-surface-raised sm:flex-row sm:items-start sm:gap-8">
            <div className="flex shrink-0 items-center gap-2 sm:w-56">
              <Server size={18} className="text-white/40" />
              <h3 className="text-sm font-semibold text-white/80">{t("limits.title")}</h3>
            </div>
            <div className="flex flex-col gap-2.5">
              <p className="text-sm text-white/50">
                {t("limits.intro")}
              </p>
              <ul className="flex flex-col gap-1.5">
                {LIMITATION_KEYS.map((key) => (
                  <li key={key} className="flex gap-2 text-sm text-white/50">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-white/30" />
                    {t(`limits.${key}`)}
                  </li>
                ))}
              </ul>
            </div>
          </Card>
        </section>
      </Reveal>

      <Reveal>
        <Faq signupCredits={signupCredits} />
      </Reveal>

      {/* Final CTA */}
      <Reveal>
        <section className="relative mx-auto max-w-3xl px-6 pb-32 pt-20 text-center">
          <WaveFloor />
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            {t("cta.title", { credits: signupCredits })}
          </h2>
          <p className="mx-auto mt-3 max-w-md text-white/50">
            {t("cta.sub")}
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <Link href="/login">
              <Button variant="gradient" size="lg">
                {t("startCreating")}
              </Button>
            </Link>
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              <Button variant="outline" size="lg">
                <Github size={18} />
                {t("cta.readCode")}
              </Button>
            </a>
          </div>
        </section>
      </Reveal>

      {/* Three items of very unequal width — a 24px mark, a sentence, a
          repo URL — and justify-between centres none of them. It centres
          the middle item in whatever slack the outer two leave, which
          coincides with the page centre only if those two are the same
          width. They aren't, so the tagline sat noticeably left of the
          Terms/Privacy row directly beneath it, which *is* centred: two
          lines that both look centred, disagreeing about where the centre
          is. Giving the outer two an equal flex basis fixes it at every
          width, because they then absorb the same share of the slack
          regardless of what they contain. */}
      <footer className="border-t border-border/60 px-6 py-8">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 sm:flex-row">
          <div className="flex justify-start sm:flex-1">
            <LogoMark className="h-6 w-6 opacity-60" />
          </div>

          <span className="text-center text-xs text-white/30">
            {t("footer.tagline")}
          </span>

          <div className="flex justify-end sm:flex-1">
            <a
              href={REPO_URL}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 text-xs text-white/40 hover:text-white/70"
            >
              <Github size={14} />
              github.com/tylkokcr/ShortPulse
            </a>
          </div>
        </div>

        <div className="mx-auto mt-5 flex max-w-6xl items-center justify-center gap-5 text-xs text-white/30">
          <Link href="/terms" className="transition-colors hover:text-white/60">
            {t("footer.terms")}
          </Link>
          <Link href="/privacy" className="transition-colors hover:text-white/60">
            {t("footer.privacy")}
          </Link>
        </div>
      </footer>
    </div>
  );
}

function SectionHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="mb-8 flex flex-col gap-2">
      <span className="font-mono text-xs uppercase tracking-widest text-accent">{eyebrow}</span>
      <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h2>
    </div>
  );
}

/**
 * The hero plays an actual render rather than a mockup — the product is a
 * video, so anything less than the real output would be arguing for it
 * instead of showing it. Muted and looping so it can autoplay at all;
 * browsers block sound without a gesture.
 *
 * It's shown inside a phone in a feed because that is the only place this
 * output is ever going to be watched, and a bare 9:16 rectangle on a
 * marketing page doesn't tell you whether the captions sit above the UI or
 * behind it. The frame answers that; see PhoneFrame on why the action rail
 * carries no numbers.
 */
function PreviewMock() {
  return (
    <div className="flex flex-col items-center gap-3">
      <PhoneFrame
        src="/examples/honey.mp4"
        poster="/examples/honey.jpg"
        caption="Why honey never spoils 🍯"
      />
      <div className="flex items-center gap-1.5">
        <Coins size={11} className="text-white/30" />
        <span className="font-mono text-[10px] text-white/30">
          stock_media · en · 24s · real render
        </span>
      </div>
    </div>
  );
}
