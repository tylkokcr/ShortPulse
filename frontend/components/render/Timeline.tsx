"use client";

import clsx from "clsx";
import type { RenderStage } from "@/lib/types";

const STAGES: { key: RenderStage; label: string }[] = [
  { key: "script_generation", label: "Script" },
  { key: "audio_synthesis", label: "Voiceover" },
  { key: "transcription", label: "Timing" },
  { key: "visual_generation", label: "Visuals" },
  { key: "subtitle_generation", label: "Subtitles" },
  { key: "assembly", label: "Render" },
  { key: "done", label: "Done" },
];

function stageOrder(stage: RenderStage | undefined): number {
  if (!stage) return -1;
  return STAGES.findIndex((s) => s.key === stage);
}

export function Timeline({ currentStage }: { currentStage: RenderStage | undefined }) {
  const currentIndex = stageOrder(currentStage);
  const failed = currentStage === "failed";

  return (
    <div className="flex items-center gap-1">
      {STAGES.map((stage, i) => {
        const isComplete = !failed && currentIndex > i;
        const isActive = !failed && currentIndex === i;
        return (
          <div key={stage.key} className="flex flex-1 flex-col items-center gap-1.5">
            <div
              className={clsx(
                "h-1.5 w-full rounded-full transition-colors",
                isComplete || isActive ? "bg-accent" : "bg-border",
                failed && currentIndex >= i && "bg-red-500"
              )}
            />
            <span className={clsx("text-[10px]", isActive ? "text-white" : "text-white/40")}>
              {stage.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
