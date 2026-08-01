"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { useShortPulseStore } from "@/lib/store";
import { Card } from "@/components/ui/Card";
import { RenderPreview } from "@/components/render/RenderPreview";
import { TranscriptPanel } from "@/components/render/TranscriptPanel";

export default function ProjectPage({ params }: { params: { id: string } }) {
  const activeProject = useShortPulseStore((s) => s.activeProject);
  const script = activeProject?.script;

  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);

  function handleSeek(seconds: number) {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = seconds;
    video.play();
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 px-6 py-10">
      <Link href="/" className="flex items-center gap-1.5 text-sm text-white/50 hover:text-white">
        <ArrowLeft size={14} />
        New video
      </Link>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        <Card className="flex flex-col gap-4">
          <h3 className="text-sm font-medium text-white/70">Scene breakdown</h3>
          {!script ? (
            <p className="text-sm text-white/40">
              The AI scriptwriter is working on this — scenes will appear here once generated.
            </p>
          ) : (
            <TranscriptPanel script={script} currentTime={currentTime} onSeek={handleSeek} />
          )}
        </Card>

        <RenderPreview projectId={params.id} videoRef={videoRef} onTimeUpdate={setCurrentTime} />
      </div>
    </main>
  );
}
