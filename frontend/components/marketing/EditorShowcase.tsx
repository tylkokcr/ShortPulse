import { MousePointerClick, Clock, Copy, Waves } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

/**
 * Shows the project page you land on after a render.
 *
 * The scene list below is the real script from the "Why honey never
 * spoils" example in the marquee — same hook, same voiceover lines, same
 * per-scene durations — so this is a reproduction of a real result rather
 * than invented copy dressed up as a screenshot.
 */
const SCENES = [
  { line: "It's because of its unique acidity level.", seconds: 4.0 },
  { line: "Honey's pH level is naturally acidic, around 3.2 to 4.5.", seconds: 4.0 },
  { line: "This acidity creates an environment where mold and bacteria can't thrive.", seconds: 3.0 },
  { line: "Additionally, honey's sugar content is so high that it dehydrates any microorganisms.", seconds: 4.0 },
];

const CAPABILITIES = [
  { icon: MousePointerClick, text: "Click any scene to jump the video to it" },
  { icon: Waves, text: "The playing scene highlights itself as it goes" },
  { icon: Clock, text: "Per-scene timing, straight from the word-level transcript" },
  { icon: Copy, text: "Footage credits collected for you, with a copy button" },
];

export function EditorShowcase() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-16">
      <div className="mb-8 flex flex-col gap-2">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">The editor</span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Every scene, lined up against the video
        </h2>
        <p className="max-w-xl text-sm text-white/50">
          When a render finishes you get the whole breakdown next to the player — what the voice
          says, how long each scene runs, and where it sits in the timeline.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_300px] lg:items-start">
        <Card className="flex flex-col gap-3 bg-surface-raised">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-white/70">Scene breakdown</h3>
            <Badge tone="pulse">Playing</Badge>
          </div>

          <p className="rounded-lg border border-accent/30 bg-accent/10 p-3 text-sm">
            <span className="font-medium text-accent">Hook: </span>
            Honey, the ultimate superfood, is surprisingly eternal!
          </p>

          {SCENES.map((scene, i) => (
            <div
              key={scene.line}
              className={`rounded-lg border p-3 text-left ${
                i === 1 ? "border-accent bg-accent/10" : "border-border"
              }`}
            >
              <div className="mb-1 flex items-center justify-between text-xs text-white/40">
                <span>Scene {i + 1}</span>
                <span>{scene.seconds.toFixed(1)}s</span>
              </div>
              <p className="text-sm text-white/70">{scene.line}</p>
            </div>
          ))}
        </Card>

        <div className="flex flex-col gap-4">
          <div className="mx-auto w-full max-w-[220px] overflow-hidden rounded-xl border border-border-strong bg-black">
            <video
              src="/examples/honey.mp4"
              poster="/examples/honey.jpg"
              muted
              loop
              playsInline
              autoPlay
              className="aspect-[9/16] w-full object-cover"
            />
          </div>

          <ul className="flex flex-col gap-2.5">
            {CAPABILITIES.map((item) => (
              <li key={item.text} className="flex items-start gap-2 text-xs text-white/50">
                <item.icon size={14} className="mt-0.5 shrink-0 text-pulse" />
                {item.text}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
