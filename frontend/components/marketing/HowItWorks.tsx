import { PenLine, SlidersHorizontal, Download } from "lucide-react";
import { Card } from "@/components/ui/Card";

const STEPS = [
  {
    icon: PenLine,
    title: "Give it a topic",
    detail:
      "One line is enough — the LLM writes the scene breakdown, the hook and the call to action. Already have a script? Paste it and the AI only splits it into scenes.",
  },
  {
    icon: SlidersHorizontal,
    title: "Pick how it looks",
    detail:
      "Language, length, visual engine and caption style. The exact credit cost and an estimated render time are shown before you commit to anything.",
  },
  {
    icon: Download,
    title: "Watch it build, then post it",
    detail:
      "Progress streams live over a WebSocket, stage by stage. You get a 1080x1920 MP4 with burned-in captions and ducked music — yours to download, no watermark.",
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="mx-auto max-w-6xl scroll-mt-20 px-6 py-16">
      <div className="mb-8 flex flex-col gap-2">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">How it works</span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Three decisions, then it runs itself
        </h2>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {STEPS.map((step, i) => (
          <Card key={step.title} interactive className="relative flex flex-col gap-3 overflow-hidden">
            {/* Oversized step numeral as texture rather than a label — the
                heading already says what the step is. */}
            <span className="pointer-events-none absolute -right-2 -top-6 font-mono text-7xl font-bold text-white/[0.04]">
              {i + 1}
            </span>
            <step.icon size={20} className="text-accent" />
            <h3 className="text-sm font-semibold">{step.title}</h3>
            <p className="text-xs leading-relaxed text-white/50">{step.detail}</p>
          </Card>
        ))}
      </div>
    </section>
  );
}
