import { Scissors, Sparkles, Timer, Wallet } from "lucide-react";
import { useTranslations } from "next-intl";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

/**
 * Cutting a long recording into posts, shown as the studio doing it.
 *
 * Drawn rather than filmed, the same way `EditorShowcase` draws the
 * project page: a screen recording of this would be eight megabytes to
 * say what a hundred lines of markup say, and it would be stale the first
 * time a label changed. What is on the page below is the studio's own
 * controls at the moment the decision is made.
 *
 * Every number here is read off a real extraction rather than chosen to
 * look good — an eight-minute recording, the stretch from 4:00 to 7:30
 * picked with the timeline, and the clips that came back. The titles are
 * the model's own, which is the point of showing them: nobody wrote them.
 */
const SOURCE_SECONDS = 480;
const WINDOW = { from: 240, to: 450 };

/**
 * The clips that run produced, titles as the model wrote them.
 *
 * Three were asked for and two came back, which is left as it happened:
 * the transcript decides how many moments are actually in there, and
 * pretending otherwise would be inventing a third card. It is also the
 * reason an extraction is priced by the stretch it reads rather than per
 * clip — nobody pays for a third clip that was not there.
 */
const CLIPS_ASKED = 3;
const CLIPS = [
  { title: "Documentation Quality", seconds: 15 },
  { title: "Speed and Clarity", seconds: 12 },
];

const CAPABILITIES = [
  { key: "transcript", icon: Sparkles },
  { key: "window", icon: Timer },
  { key: "cost", icon: Wallet },
  { key: "library", icon: Scissors },
] as const;

/** m:ss, the way the studio's own timeline writes a position. */
function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function ClipShowcase() {
  const t = useTranslations("clips");
  const span = WINDOW.to - WINDOW.from;
  const left = (WINDOW.from / SOURCE_SECONDS) * 100;
  const width = (span / SOURCE_SECONDS) * 100;
  // The published rate, and the arithmetic the panel runs: a part of two
  // minutes is never free.
  const credits = Math.max(1, Math.ceil(span / 120));

  return (
    <section className="mx-auto max-w-6xl px-6 py-16">
      <div className="mb-8 flex flex-col gap-2">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">
          {t("eyebrow")}
        </span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{t("title")}</h2>
        <p className="max-w-xl text-sm text-white/50">{t("sub")}</p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_300px] lg:items-start">
        <Card className="flex flex-col gap-5 bg-surface-raised">
          {/* The chip row, at the moment three is chosen. */}
          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium text-white/70">{t("chips")}</span>
            <div className="flex flex-wrap gap-2">
              {[0, 2, 3, 4, 5].map((count) => (
                <span
                  key={count}
                  className={
                    count === CLIPS_ASKED
                      ? "rounded-lg border border-accent/60 bg-accent/[0.08] px-3 py-1.5 text-xs text-white"
                      : "rounded-lg border border-border px-3 py-1.5 text-xs text-white/40"
                  }
                >
                  {count === 0 ? t("chipWhole") : t("chipCount", { count })}
                </span>
              ))}
            </div>
          </div>

          {/* The timeline, with the stretch that was actually read. The
              bar is the source; the lit part is what Whisper was given. */}
          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium text-white/70">{t("window")}</span>
            <div className="relative h-7 w-full overflow-hidden rounded-md border border-border bg-black/40">
              <span
                className="absolute inset-y-0 rounded-[3px] border-y border-accent/50 bg-accent/20"
                style={{ left: `${left}%`, width: `${width}%` }}
              />
              <span
                className="absolute inset-y-0 w-[3px] -translate-x-1/2 rounded-full bg-accent"
                style={{ left: `${left}%` }}
              />
              <span
                className="absolute inset-y-0 w-[3px] -translate-x-1/2 rounded-full bg-accent"
                style={{ left: `${left + width}%` }}
              />
            </div>
            <div className="flex items-center gap-1 font-mono text-[10px] tabular-nums text-white/35">
              <span>{clock(WINDOW.from)}</span>
              <span className="text-white/20">→</span>
              <span>{clock(WINDOW.to)}</span>
              <span className="ml-auto text-white/20">{clock(SOURCE_SECONDS)}</span>
            </div>
          </div>

          <p className="flex flex-wrap items-center gap-2 border-t border-border pt-4 text-xs text-white/50">
            <Wallet size={13} className="text-accent" />
            {t("cost", { credits, span: clock(span) })}
          </p>
        </Card>

        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium text-white/70">{t("out")}</span>
            {CLIPS.map((clip) => (
              <div
                key={clip.title}
                className="flex items-center gap-3 rounded-lg border border-border bg-surface p-2.5"
              >
                <span className="flex h-11 w-[26px] shrink-0 items-center justify-center rounded-[3px] border border-border-strong bg-black/50">
                  <Scissors size={11} className="text-accent" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-medium">{clip.title}</span>
                  <span className="mt-0.5 block font-mono text-[10px] text-white/35">
                    0:{String(clip.seconds).padStart(2, "0")} · 9:16
                  </span>
                </span>
                <Badge tone="neutral" className="shrink-0 text-[10px]">
                  {t("captioned")}
                </Badge>
              </div>
            ))}
          </div>

          <ul className="flex flex-col gap-2.5">
            {CAPABILITIES.map((item) => (
              <li key={item.key} className="flex items-start gap-2 text-xs text-white/50">
                <item.icon size={14} className="mt-0.5 shrink-0 text-accent" />
                {t(`capabilities.${item.key}`)}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
