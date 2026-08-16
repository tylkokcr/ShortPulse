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
import { RenderReport } from "./RenderReport";
import { VideoVerdict } from "./VideoVerdict";

interface RenderPreviewProps {
  projectId: string;
  /** Shares the <video> element with a sibling TranscriptPanel so clicking
   * a scene can seek playback. Falls back to an internal ref when omitted. */
  videoRef?: RefObject<HTMLVideoElement | null>;
  onTimeUpdate?: (seconds: number) => void;
  /** Asked once the video exists and can be watched. Omitted on a
   *  self-hosted install, where there is nobody to tell. */
  verdict?: {
    current?: import("@/lib/types").SceneFeedback;
    onSubmit: (rating: "up" | "down") => Promise<void>;
  };
}

export function RenderPreview({ projectId, videoRef, onTimeUpdate, verdict }: RenderPreviewProps) {
  const { activeProject, setActiveProject, renderProgress, setRenderProgress, videoVersion } =
    useShortPulseStore();
  const internalVideoRef = useRef<HTMLVideoElement>(null);
  const resolvedVideoRef = videoRef ?? internalVideoRef;
  const [videoUrl, setVideoUrl] = useState<string | null>(null);

  useEffect(() => {
    // Progress lives in a single global slot, so anything left over from
    // the last project would be read as this one's. Clearing on mount is
    // what stops a finished video showing another render's stage.
    setRenderProgress(null);
    getProject(projectId).then(setActiveProject).catch(console.error);

    const unsubscribe = subscribeToRenderProgress(projectId, (progress) => {
      if (progress.project_id !== projectId) return;
      setRenderProgress(progress);
      if (progress.stage === "done" || progress.stage === "failed") {
        getProject(projectId).then(setActiveProject).catch(console.error);
      }
    });
    return unsubscribe;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const status = activeProject?.status;

  /**
   * Poll while a render is in flight.
   *
   * The WebSocket is the fast path, not a guarantee: it can be opened
   * after the stage it would have reported, dropped by a proxy, or miss
   * the final message — and when that happened the page sat on "Waiting to
   * start" or froze mid-stepper for a video that had already finished,
   * with nothing to recover it but a manual reload.
   *
   * The project row is the authority, so this asks it directly until it
   * reaches a terminal state, then stops.
   */
  useEffect(() => {
    if (status !== "rendering" && status !== "draft") return;
    const timer = window.setInterval(() => {
      getProject(projectId).then(setActiveProject).catch(() => {});
    }, 5000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, status]);

  // The video URL is signed and short-lived, so it can't be derived from
  // the project id — it has to be requested once the render is done.
  //
  // `videoVersion` is in the dependencies because status is not enough:
  // an edit and a scene re-roll both overwrite final.mp4 in place and
  // leave the project complete, so without it the player keeps showing
  // the video from before the change and the user concludes it did
  // nothing.
  useEffect(() => {
    if (activeProject?.status !== "complete") return;
    getMediaUrl(projectId).then((m) => setVideoUrl(m.url)).catch(console.error);
  }, [projectId, activeProject?.status, videoVersion]);

  const isDone = status === "complete";
  const isFailed = status === "failed" || renderProgress?.stage === "failed";

  // The stored status wins over the socket, not the other way round. A
  // project that has finished has finished, whatever the last progress
  // message happened to say — reading the socket first left the stepper
  // parked on "Visuals" under a video that was already playing.
  const timelineStage: RenderStage | undefined = isDone
    ? "done"
    : isFailed
      ? "failed"
      : renderProgress?.stage;

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
    <Card className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <span className="label">{isDone ? "Output" : isFailed ? "Failed" : "Rendering"}</span>
        {isDone ? (
          <span className="flex items-center gap-1.5 font-mono text-[10px] text-live">
            <span className="h-1.5 w-1.5 bg-live" />
            ready
          </span>
        ) : !isFailed && renderProgress ? (
          <span className="flex items-center gap-1.5 font-mono text-[10px] text-white/50">
            <Loader2 size={11} className="animate-spin" />
            {Math.round(renderProgress.progress_pct)}%
          </span>
        ) : null}
      </div>

      {/* Squared off and edge to edge: the video is the product, so it gets
          the full width of the panel rather than sitting inset in a
          rounded well like a thumbnail. */}
      <div className="relative flex aspect-[9/16] w-full items-center justify-center overflow-hidden border border-border bg-black">
        {isDone && videoUrl ? (
          <video
            ref={resolvedVideoRef}
            src={videoUrl}
            controls
            autoPlay
            loop
            onTimeUpdate={(e) => onTimeUpdate?.(e.currentTarget.currentTime)}
            className="h-full w-full object-contain"
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
              : (renderProgress?.message ??
                // "draft" means accepted but not yet picked up by a
                // worker, which is a queue, not a stall — worth saying so
                // when renders run two at a time.
                (status === "draft" ? "Queued — waiting for a free worker..." : "Starting..."))}
          </p>
        )}
      </div>

      {/* While it runs, the stepper is the content. Once it is done, the
          stage list has nothing left to say and the report below says it
          better, so the stepper goes away rather than sitting there fully
          lit forever. */}
      {!isDone && <Timeline currentStage={timelineStage} />}

      {isDone && (
        <>
          <Button variant="secondary" onClick={download}>
            <Download size={16} />
            Download .mp4
          </Button>
          <RenderReport projectId={projectId} />
          {/* Under the report, not above the download: the video is what
              they came for, and the question is worth asking only once
              they have it. */}
          {verdict && (
            <VideoVerdict verdict={verdict.current} onSubmit={verdict.onSubmit} />
          )}
        </>
      )}
    </Card>
  );
}
