"use client";

import { Download, Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import { downloadUrl, getProject, subscribeToRenderProgress } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Timeline } from "./Timeline";

interface RenderPreviewProps {
  projectId: string;
  /** Shares the <video> element with a sibling TranscriptPanel so clicking
   * a scene can seek playback. Falls back to an internal ref when omitted. */
  videoRef?: RefObject<HTMLVideoElement>;
  onTimeUpdate?: (seconds: number) => void;
}

export function RenderPreview({ projectId, videoRef, onTimeUpdate }: RenderPreviewProps) {
  const { activeProject, setActiveProject, renderProgress, setRenderProgress } = useShortPulseStore();
  const internalVideoRef = useRef<HTMLVideoElement>(null);
  const resolvedVideoRef = videoRef ?? internalVideoRef;

  useEffect(() => {
    getProject(projectId).then(setActiveProject).catch(console.error);
    const unsubscribe = subscribeToRenderProgress(projectId, (progress) => {
      setRenderProgress(progress);
      if (progress.stage === "done" || progress.stage === "failed") {
        getProject(projectId).then(setActiveProject).catch(console.error);
      }
    });
    return unsubscribe;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const isDone = activeProject?.status === "complete";
  const isFailed = activeProject?.status === "failed" || renderProgress?.stage === "failed";

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-white/70">Render Preview</h3>
        {!isDone && !isFailed && renderProgress && (
          <span className="flex items-center gap-1.5 text-xs text-white/50">
            <Loader2 size={12} className="animate-spin" />
            {Math.round(renderProgress.progress_pct)}%
          </span>
        )}
      </div>

      <div className="mx-auto flex aspect-[9/16] w-full max-w-[280px] items-center justify-center overflow-hidden rounded-lg bg-black">
        {isDone && activeProject?.output_path ? (
          <video
            ref={resolvedVideoRef}
            src={downloadUrl(projectId)}
            controls
            autoPlay
            loop
            onTimeUpdate={(e) => onTimeUpdate?.(e.currentTarget.currentTime)}
            className="h-full w-full object-cover"
          />
        ) : isFailed ? (
          <p className="p-4 text-center text-xs text-red-400">
            {renderProgress?.error ?? activeProject?.error ?? "Render failed."}
          </p>
        ) : (
          <p className="p-4 text-center text-xs text-white/40">
            {renderProgress?.message ?? "Waiting to start..."}
          </p>
        )}
      </div>

      <Timeline currentStage={renderProgress?.stage} />

      {isDone && (
        <Button variant="secondary" onClick={() => window.open(downloadUrl(projectId), "_blank")}>
          <Download size={16} />
          Download .mp4
        </Button>
      )}
    </Card>
  );
}
