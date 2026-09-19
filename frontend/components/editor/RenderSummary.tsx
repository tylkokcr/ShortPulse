"use client";

import { Clock, Coins, Film, Layers, Ratio, TriangleAlert } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { useShortPulseStore } from "@/lib/store";
import type { AspectRatio, VideoLength, VisualMode } from "@/lib/types";
import { Card } from "@/components/ui/Card";
import { StudioPreview } from "./StudioPreview";

/**
 * Live quote for the render the form currently describes.
 *
 * Everything here is derived, never guessed at a different number than the
 * backend uses: the credit cost comes from the pricing table the API
 * serves (the same table it charges from), and the time estimates come
 * from measured runs recorded in `timings.json` on this hardware rather
 * than from a marketing round number.
 */

/** Mirrors `render_manager.resolution_for`, which pins the short edge to
 *  1080 rather than inflating the square case. */
const RESOLUTIONS: Record<AspectRatio, string> = {
  "9:16": "1080x1920",
  "1:1": "1080x1080",
  "16:9": "1920x1080",
};

/** Midpoint of the scene ranges the length presets ask the LLM for. */
const SCENES: Record<VideoLength, number> = { short: 5, medium: 9, long: 13 };
const SECONDS: Record<VideoLength, string> = {
  short: "15-25s",
  medium: "30-45s",
  long: "60s+",
};

/**
 * Seconds of wall clock per scene, measured on an Apple Silicon M-series
 * with 32GB: stock_media renders averaged ~45s for 5 scenes, fast_hybrid
 * took 390s for the same 5. ai_video is left out on purpose — it varied
 * too much to quote and is documented as impractical on this hardware.
 */
const SECONDS_PER_SCENE: Record<VisualMode, number | null> = {
  stock_media: 9,
  fast_hybrid: 78,
  ai_video: null,
};

function formatDuration(seconds: number): string {
  if (seconds < 90) return `~${Math.round(seconds / 5) * 5}s`;
  return `~${Math.round(seconds / 60)} min`;
}

export function RenderSummary() {
  const { draft, credits } = useShortPulseStore();

  const scenes = SCENES[draft.videoLength];
  const perScene = SECONDS_PER_SCENE[draft.visualMode];
  const cost = credits?.enabled
    ? credits.pricing[`${draft.visualMode}:${draft.videoLength}`]
    : undefined;

  const balance = credits?.balance ?? 0;
  const shortfall = cost !== undefined && cost > balance;

  return (
    <Card className="relative flex flex-col gap-4 overflow-hidden border-border-strong bg-surface-raised">
      {/* Faint accent bloom so the panel reads as the focal surface rather
          than another grey box in the column. */}
      <div className="pointer-events-none absolute -right-20 -top-24 h-48 w-48 rounded-full bg-accent/20 blur-3xl" />

      <div className="relative">
        <StudioPreview />
      </div>

      <div className="relative flex items-center gap-2 border-t border-border pt-4">
        <span className="h-3 w-px bg-accent" />
        <h2 className="text-sm font-semibold text-white/80">This render</h2>
      </div>

      <dl className="relative flex flex-col gap-3 text-sm">
        <Row icon={Ratio} label="Format">
          {draft.aspectRatio} · {RESOLUTIONS[draft.aspectRatio]}
        </Row>
        <Row icon={Film} label="Length">
          {SECONDS[draft.videoLength]}
        </Row>
        <Row icon={Layers} label="Scenes">
          ~{scenes}
        </Row>
        <Row icon={Clock} label="Render time">
          {perScene === null ? (
            <span className="text-amber-300/90">minutes per scene</span>
          ) : (
            formatDuration(perScene * scenes)
          )}
        </Row>
        {cost !== undefined && (
          <Row icon={Coins} label="Cost">
            <span className={shortfall ? "text-red-400" : "text-white"}>
              {cost} credit{cost === 1 ? "" : "s"}
            </span>
          </Row>
        )}
      </dl>

      {cost !== undefined && (
        <div className="relative flex items-center justify-between border-t border-border pt-3 text-xs">
          <span className="text-white/40">Balance after</span>
          <span className={shortfall ? "font-medium text-red-400" : "font-medium text-white/70"}>
            {balance - cost} credit{balance - cost === 1 ? "" : "s"}
          </span>
        </div>
      )}

      {shortfall && (
        <p className="relative flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-2.5 text-xs text-red-300">
          <TriangleAlert size={13} className="mt-0.5 shrink-0" />
          You have {balance}. Pick a cheaper visual style or a shorter length, or{" "}
          <Link href="/credits" className="underline underline-offset-2 hover:text-red-200">
            top up
          </Link>
          .
        </p>
      )}

      {perScene !== null && (
        <p className="relative text-[11px] leading-relaxed text-white/30">
          Timings measured on an Apple Silicon M-series, 32GB. Yours will differ — a dedicated GPU
          is considerably faster.
        </p>
      )}
    </Card>
  );
}

function Row({
  icon: Icon,
  label,
  children,
}: {
  icon: typeof Clock;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="flex items-center gap-2 text-white/50">
        <Icon size={14} className="text-white/30" />
        {label}
      </dt>
      <dd className="font-mono text-xs text-white/80">{children}</dd>
    </div>
  );
}
