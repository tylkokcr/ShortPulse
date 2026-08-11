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
import { SiteHeader } from "@/components/layout/SiteHeader";
import { LogoMark } from "@/components/ui/Logo";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Reveal } from "@/components/ui/Reveal";
import { LoginPanel } from "@/components/auth/LoginScreen";
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

const STATS = [
  { value: "9", label: "languages" },
  { value: "3", label: "visual engines" },
  { value: "15", label: "free credits" },
  { value: "MIT", label: "licensed" },
];

const PIPELINE = [
  { icon: FileText, title: "Script", detail: "Ollama (local) or OpenAI breaks your topic into scenes" },
  { icon: Mic, title: "Voiceover", detail: "Piper voices, fully local, 10 languages" },
  { icon: Captions, title: "Captions", detail: "faster-whisper times every word for karaoke-style burn-in" },
  { icon: ImageIcon, title: "Visuals", detail: "AI stills, local text-to-video, or free stock footage" },
  { icon: Film, title: "Assemble", detail: "FFmpeg mixes ducked music and renders the final .mp4" },
];

const FEATURES = [
  {
    icon: Lock,
    title: "Runs on your machine",
    detail:
      "Scripting, voiceover, transcription, visuals and rendering all execute locally. Only the optional stock-footage mode touches the network.",
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
    title: "Three visual engines",
    detail: "Photoreal diffusion, real Pexels footage, or local text-to-video — with automatic fallback if a GPU isn't available.",
  },
  {
    icon: Sparkles,
    title: "Branded outro card",
    detail: "An optional closing card rendered locally with Pillow, so the last frame is your call-to-action, not a diffusion guess.",
  },
];

const COMPARISON = [
  { label: "What you pay", us: "Per video, or $0 self-hosted", them: "$20–50/mo, posted or not" },
  { label: "Idle months", us: "Cost nothing", them: "Billed anyway" },
  { label: "Source code", us: "MIT, fully readable", them: "Closed" },
  { label: "Where it runs", us: "Your machine, or ours", them: "Their servers only" },
  { label: "Customization", us: "Edit prompts, swap models freely", them: "Locked to their pipeline" },
  { label: "Unused credits", us: "Never expire", them: "Reset every month" },
];

const LIMITATIONS = [
  "The examples above use stock footage for a reason: the AI-stills mode mangles faces, hands and any on-screen text, so it suits objects and scenery far better than people.",
  "ai_video (local text-to-video) is real but slow — treat it as experimental without a dedicated GPU.",
  "Small local LLMs occasionally under-count scenes; the script engine retries and drops malformed ones rather than failing the render.",
  "Stock footage is a closest-match, not a guarantee — Pexels clips can be loosely related to the scene.",
];

export function Landing() {
  return (
    <div className="relative min-h-screen bg-radial-fade">
      {/* Decorative layer, not the content wrapper — mask-image masks an
          element's entire rendered content, children included, so it can't
          live on anything that also has to show real content beneath it. */}
      <div className="bg-grid pointer-events-none absolute inset-x-0 top-0 -z-10 h-[640px]" aria-hidden />

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
            <a href="#sign-in">
              <Button variant="secondary" size="sm">
                Sign in
              </Button>
            </a>
          </>
        }
      />

      {/* Hero */}
      <section className="mx-auto grid max-w-6xl gap-12 px-6 pb-20 pt-16 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:pt-24">
        <div className="flex flex-col gap-6">
          <Badge tone="accent" className="w-fit">
            Open source · self-hosted or hosted
          </Badge>
          <h1 className="text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl">
            Turn a topic into a <span className="text-gradient">ready-to-post</span> vertical video.
          </h1>
          <p className="max-w-lg text-lg leading-relaxed text-white/60">
            Script, voiceover, word-synced captions, visuals and music — assembled by a pipeline you
            can actually read. Pay per video or self-host it for nothing. No subscription either way.
          </p>

          <dl className="grid grid-cols-4 gap-4 border-t border-border pt-6">
            {STATS.map((stat) => (
              <div key={stat.label} className="flex flex-col gap-1">
                <dt className="sr-only">{stat.label}</dt>
                <dd className="font-mono text-xl font-medium text-white sm:text-2xl">{stat.value}</dd>
                <span className="text-xs text-white/40">{stat.label}</span>
              </div>
            ))}
          </dl>

          <div className="flex flex-wrap items-center gap-3 pt-2">
            <a href="#sign-in">
              <Button variant="gradient" size="lg">
                Start creating
              </Button>
            </a>
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              <Button variant="outline" size="lg">
                <Github size={18} />
                View source
              </Button>
            </a>
          </div>
        </div>

        <div className="flex flex-col items-center gap-6">
          <PreviewMock />
          <LoginPanel className="w-full max-w-sm" />
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
              <Card key={step.title} interactive className="flex flex-col gap-3 bg-grain">
                <div className="flex items-center justify-between">
                  <step.icon size={20} className="text-accent" />
                  <span className="font-mono text-xs text-white/30">0{i + 1}</span>
                </div>
                <h3 className="text-sm font-semibold">{step.title}</h3>
                <p className="text-xs leading-relaxed text-white/50">{step.detail}</p>
              </Card>
            ))}
          </div>
        </section>
      </Reveal>

      {/* Features */}
      <Reveal>
        <section className="mx-auto max-w-6xl px-6 py-16">
          <SectionHeading eyebrow="What's built in" title="Everything short-form video needs, none of it gated" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((feature) => (
              <Card key={feature.title} className="flex flex-col gap-3">
                <feature.icon size={20} className="text-pulse" />
                <h3 className="text-sm font-semibold">{feature.title}</h3>
                <p className="text-xs leading-relaxed text-white/50">{feature.detail}</p>
              </Card>
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
                        <Check size={14} className="text-pulse" />
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
        <Faq />
      </Reveal>

      {/* Final CTA */}
      <Reveal>
        <section className="mx-auto max-w-3xl px-6 py-20 text-center">
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            Start with 15 credits. No card, no trial timer.
          </h2>
          <p className="mx-auto mt-3 max-w-md text-white/50">
            That&apos;s five finished videos to judge it by. Buy more only if it earns it — or clone
            the repo and run the whole thing on your own hardware for nothing.
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <a href="#sign-in">
              <Button variant="gradient" size="lg">
                Start creating
              </Button>
            </a>
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              <Button variant="outline" size="lg">
                <Github size={18} />
                Read the code
              </Button>
            </a>
          </div>
        </section>
      </Reveal>

      <footer className="border-t border-border/60 px-6 py-8">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 sm:flex-row">
          <LogoMark className="h-6 w-6 opacity-60" />
          <p className="text-xs text-white/30">MIT licensed · No tracking, no dark patterns.</p>
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
