"use client";

import { Download, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import { getMediaUrl, getProject, subscribeToRenderProgress } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import type { RenderStage } from "@/lib/types";
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
  const [videoUrl, setVideoUrl] = useState<string | null>(null);

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

  // The video URL is signed and short-lived, so it can't be derived from
  // the project id — it has to be requested once the render is done.
  useEffect(() => {
    if (activeProject?.status !== "complete") return;
    getMediaUrl(projectId).then((m) => setVideoUrl(m.url)).catch(console.error);
  }, [projectId, activeProject?.status]);

  const isDone = activeProject?.status === "complete";
  const isFailed = activeProject?.status === "failed" || renderProgress?.stage === "failed";

  // Opening the page after a render has finished gets no progress events —
  // those only arrive over the WebSocket while it runs. Without this
  // fallback the timeline sits entirely grey on a completed project, as if
  // nothing had happened.
  const timelineStage: RenderStage | undefined =
    renderProgress?.stage ?? (isDone ? "done" : isFailed ? "failed" : undefined);

  // Mint a fresh link rather than reusing the one the player got: a page
  // left open outlives the token, and a download that 403s looks like the
  // video is gone.
  async function download() {
    try {
      const { download_url } = await getMediaUrl(projectId);
      window.open(download_url, "_blank");
    } catch (err) {
      console.error(err);
    }
  }

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
        {isDone && videoUrl ? (
          <video
            ref={resolvedVideoRef}
            src={videoUrl}
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
            {isDone
              ? // Render finished, but the signed URL is still being fetched.
                // "Waiting to start" here would say the opposite of the truth.
                "Loading video..."
              : (renderProgress?.message ?? "Waiting to start...")}
          </p>
        )}
      </div>

      <Timeline currentStage={timelineStage} />

      {isDone && (
        <Button variant="secondary" onClick={download}>
          <Download size={16} />
          Download .mp4
        </Button>
      )}
    </Card>
  );
}
