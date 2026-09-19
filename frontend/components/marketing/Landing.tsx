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

// Numbers a visitor reads as being about *this* service, so nothing here
// may depend on how the deployment happens to be configured. "3 visual
// engines" was true of the repository and false of the site the moment
// ai_video was refused here — and this component is static, with no way
// to know. Art styles are in the code and the same everywhere.
const statsFor = (signupCredits: number) => [
  { value: "9", label: "languages" },
  { value: "6", label: "art styles" },
  { value: String(signupCredits), label: "free credits" },
  { value: "MIT", label: "licensed" },
];

const PIPELINE = [
  { icon: FileText, title: "Script", detail: "Ollama (local) or OpenAI breaks your topic into scenes" },
  // Nine, and it has to stay tied to LANGUAGE_OPTIONS: the stat above and
  // the feature card below both say nine because that is what the picker
  // offers, and this line said ten. Japanese is the one it was counting —
  // deliberately dropped, because Piper ships no licensed voice for it.
  { icon: Mic, title: "Voiceover", detail: "Piper voices, fully local, 9 languages" },
  { icon: Captions, title: "Captions", detail: "faster-whisper times every word for karaoke-style burn-in" },
  { icon: ImageIcon, title: "Visuals", detail: "AI stills or free stock footage; local text-to-video when you self-host" },
  { icon: Film, title: "Assemble", detail: "FFmpeg mixes ducked music and renders the final .mp4" },
];

const FEATURES = [
  {
    icon: Lock,
    title: "Runs on your machine",
    detail:
      "Self-host it and scripting, voiceover, transcription, visuals and rendering all execute locally — only stock footage touches the network. The hosted service trades that away deliberately: it has no GPU, so the script and the AI stills come from paid APIs.",
  },
  {
    icon: Captions,
    title: "Word-synced captions",
    detail: "faster-whisper gives word-level timing, so captions highlight one word at a time instead of dumping a full line.",
  },
  {
    icon: Globe,
    title: "9 languages",
    detail: "Script, voiceover and subtitles generate natively in English, Turkish, Spanish, German, Arabic and more.",
  },
  {
    icon: Music,
    title: "Auto-ducked music",
    detail: "Background music sidechain-ducks under the voiceover automatically — no manual mixing.",
  },
  {
    icon: ImageIcon,
    title: "Photoreal stills or real footage",
    detail: "A RealVisXL still per scene with a Ken Burns move over it, or a matching Pexels clip. Self-hosting with a GPU adds local text-to-video, which this service doesn't run.",
  },
  {
    icon: Sparkles,
    title: "Branded outro card",
    detail: "An optional closing card rendered locally with Pillow, so the last frame is your call-to-action, not a diffusion guess.",
  },
];

const COMPARISON = [
  // "nothing", not "$0": this is our own price and the deployment charges
  // euros, so a dollar sign here is the same defect 8a1d635 removed from
  // the pricing cards. Worded rather than formatted because this table is
  // static copy with no access to the server's currency — and free costs
  // the same in every currency.
  { label: "What you pay", us: "Per video, or nothing self-hosted", them: "$20–50/mo, posted or not" },
  { label: "Idle months", us: "Cost nothing", them: "Billed anyway" },
  { label: "Source code", us: "MIT, fully readable", them: "Closed" },
  { label: "Where it runs", us: "Your machine, or ours", them: "Their servers only" },
  { label: "Customization", us: "Edit prompts, swap models freely", them: "Locked to their pipeline" },
  { label: "Unused credits", us: "Never expire", them: "Reset every month" },
];

const LIMITATIONS = [
  // Rewritten against a side-by-side of both modes on the same topic
  // rather than from memory. The old wording — "mangles faces, hands and
  // any on-screen text, so it suits objects and scenery far better than
  // people" — described local diffusion, and stopped being true when
  // fast_hybrid moved to RealVisXL over an API: faces came back the
  // strongest thing in the frame. Talking the paid mode down on the
  // strength of an observation about a backend this service no longer
  // runs is worse than saying nothing.
  "AI stills draw faces convincingly and extremities badly — hands, feet and full-body shots are where a frame falls apart, so the script engine keeps people in close and medium shots. Legible text is beyond the model entirely: it cannot write a label, a sign or a book cover.",
  "ai_video (local text-to-video) only runs where you supply the GPU. It is not available on this hosted service: renting one costs more per video than the mode is priced at, so we would rather not offer it than offer it badly.",
  "Small local LLMs occasionally under-count scenes; the script engine retries and drops malformed ones rather than failing the render.",
  "Stock footage is a closest-match, not a guarantee — Pexels clips can be loosely related to the scene.",
];

export function Landing() {
  const signupCredits = useSignupCredits();
  const STATS = statsFor(signupCredits);

  return (
    <div className="relative min-h-screen">
      <GridBackdrop />

      <SiteHeader
        right={
          <>
            {[
              { href: "#examples", label: "Examples" },
              { href: "#how-it-works", label: "How it works" },
              { href: "#pricing", label: "Pricing" },
              { href: "#faq", label: "FAQ" },
            ].map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="hidden text-sm text-white/50 transition-colors hover:text-white md:block"
              >
                {link.label}
              </a>
            ))}
            <Link href="/login">
              <Button variant="secondary" size="sm">
                Sign in
              </Button>
            </Link>
          </>
        }
      />

      {/* Hero */}
      <section className="mx-auto grid max-w-6xl gap-12 px-6 pb-20 pt-16 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:pt-24">
        <div className="flex flex-col gap-6">
          <Badge tone="accent" className="w-fit">
            Open source · self-hosted or hosted
          </Badge>
          <WordReveal className="text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl">
            Turn a topic into a <span className="text-accent-emphasis">ready-to-post</span> vertical
            video.
          </WordReveal>
          <p className="max-w-lg text-lg leading-relaxed text-white/60">
            Script, voiceover, word-synced captions, visuals and music — assembled by a pipeline you
            can actually read. Pay per video or self-host it for nothing. No subscription either way.
          </p>

          {/* Two across on a phone: four columns leaves ~73px each, which
              wraps "visual engines" onto two lines and makes the row read
              as noise rather than as four facts. */}
          <dl className="grid grid-cols-2 gap-4 border-t border-border pt-6 sm:grid-cols-4">
            {STATS.map((stat) => (
              <div key={stat.label} className="flex flex-col gap-1">
                <dt className="sr-only">{stat.label}</dt>
                <dd className="font-mono text-xl font-medium text-white sm:text-2xl">
                  <CountUp value={stat.value} />
                </dd>
                <span className="text-xs text-white/40">{stat.label}</span>
              </div>
            ))}
          </dl>

          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Link href="/login">
              <Button variant="gradient" size="lg">
                Start creating
              </Button>
            </Link>
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              <Button variant="outline" size="lg">
                <Github size={18} />
                View source
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
          <SectionHeading eyebrow="Pipeline" title="Five local stages, one finished .mp4" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {PIPELINE.map((step, i) => (
              <Reveal key={step.title} delay={i * 70} className="h-full">
                <Card interactive className="flex h-full flex-col gap-3 bg-grain">
                  <div className="flex items-center justify-between">
                    <step.icon size={20} className="text-accent" />
                    <span className="font-mono text-xs text-white/30">0{i + 1}</span>
                  </div>
                  <h3 className="text-sm font-semibold">{step.title}</h3>
                  <p className="text-xs leading-relaxed text-white/50">{step.detail}</p>
                </Card>
              </Reveal>
            ))}
          </div>
        </section>
      </Reveal>

      {/* Features */}
      <Reveal>
        <section className="mx-auto max-w-6xl px-6 py-16">
          <SectionHeading eyebrow="What's built in" title="Everything short-form video needs, none of it gated" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((feature, i) => (
              <Reveal key={feature.title} delay={(i % 3) * 70} className="h-full">
                <Card className="flex h-full flex-col gap-3">
                  <feature.icon size={20} className="text-white/40" />
                  <h3 className="text-sm font-semibold">{feature.title}</h3>
                  <p className="text-xs leading-relaxed text-white/50">{feature.detail}</p>
                </Card>
              </Reveal>
            ))}
          </div>
        </section>
      </Reveal>

      {/* Comparison */}
      <Reveal>
        <section className="mx-auto max-w-6xl px-6 py-16">
          <SectionHeading eyebrow="Why not just subscribe" title="What changes when it's local and open" />
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
                  <th className="px-5 py-3 font-medium">Typical subscription tool</th>
                </tr>
              </thead>
              <tbody>
                {COMPARISON.map((row) => (
                  <tr key={row.label} className="border-b border-border/60 last:border-0">
                    <td className="px-5 py-3.5 text-white/50">{row.label}</td>
                    <td className="px-5 py-3.5 font-medium text-white">
                      <span className="inline-flex items-center gap-1.5">
                        <Check size={14} className="text-accent" />
                        {row.us}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-white/40">
                      <span className="inline-flex items-center gap-1.5">
                        <X size={14} className="text-white/25" />
                        {row.them}
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
              <h3 className="text-sm font-semibold text-white/80">Built to survive scrutiny</h3>
            </div>
            <div className="flex flex-col gap-2.5">
              <p className="text-sm text-white/50">
                Marketing pages hide the rough edges. Ours are in the README, in full — here are a
                few of them, so you know before you clone it:
              </p>
              <ul className="flex flex-col gap-1.5">
                {LIMITATIONS.map((item) => (
                  <li key={item} className="flex gap-2 text-sm text-white/50">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-white/30" />
                    {item}
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
            Start with {signupCredits} credits. No card, no trial timer.
          </h2>
          <p className="mx-auto mt-3 max-w-md text-white/50">
            That&apos;s enough to judge it by. Buy more only if it earns it — or clone
            the repo and run the whole thing on your own hardware for nothing.
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <Link href="/login">
              <Button variant="gradient" size="lg">
                Start creating
              </Button>
            </Link>
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              <Button variant="outline" size="lg">
                <Github size={18} />
                Read the code
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
            MIT licensed · No tracking, no dark patterns.
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
            Terms
          </Link>
          <Link href="/privacy" className="transition-colors hover:text-white/60">
            Privacy
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
