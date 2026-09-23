"use client";

import clsx from "clsx";
import { useTranslations } from "next-intl";
import type { RenderStage } from "@/lib/types";

const STAGES: RenderStage[] = [
  "script_generation",
  "audio_synthesis",
  "transcription",
  "visual_generation",
  "subtitle_generation",
  "assembly",
  "done",
];

function stageOrder(stage: RenderStage | undefined): number {
  if (!stage) return -1;
  return STAGES.indexOf(stage);
}

export function Timeline({ currentStage }: { currentStage: RenderStage | undefined }) {
  const t = useTranslations("app.timeline");
  const currentIndex = stageOrder(currentStage);
  const failed = currentStage === "failed";

  return (
    <div className="flex items-center gap-1">
      {STAGES.map((stage, i) => {
        const isComplete = !failed && currentIndex > i;
        const isActive = !failed && currentIndex === i;
        return (
          <div key={stage} className="flex flex-1 flex-col items-center gap-1.5">
            <div
              className={clsx(
                "h-1.5 w-full rounded-full transition-colors",
                isComplete || isActive ? "bg-accent" : "bg-border",
                failed && currentIndex >= i && "bg-red-500"
              )}
            />
            <span className={clsx("text-[10px]", isActive ? "text-white" : "text-white/40")}>
              {t(stage)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
