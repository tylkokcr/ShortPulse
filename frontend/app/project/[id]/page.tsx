"use client";

import Link from "next/link";
import { use, useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { useShortPulseStore } from "@/lib/store";
import { Card } from "@/components/ui/Card";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { AccountBar } from "@/components/auth/AccountBar";
import { RenderPreview } from "@/components/render/RenderPreview";
import { TranscriptPanel } from "@/components/render/TranscriptPanel";
import { StockCredits } from "@/components/render/StockCredits";

export default function ProjectPage(props: { params: Promise<{ id: string }> }) {
  // Next 15 made route params a promise. This is a client component, so it
  // unwraps with use() rather than await.
  const { id } = use(props.params);
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
    <div className="min-h-screen">
      <SiteHeader right={<AccountBar />} showLibrary />

      <main className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-10">
        <Link
          href="/"
          className="flex w-fit items-center gap-1.5 text-sm text-white/50 transition-colors hover:text-white"
        >
          <ArrowLeft size={14} />
          New video
        </Link>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
          <Card className="flex flex-col gap-4 animate-fade-up">
            <h3 className="text-sm font-medium text-white/70">Scene breakdown</h3>
            {!script ? (
              <p className="text-sm text-white/40">
                The AI scriptwriter is working on this — scenes will appear here once generated.
              </p>
            ) : (
              <TranscriptPanel script={script} currentTime={currentTime} onSeek={handleSeek} />
            )}
            {script && <StockCredits script={script} />}
          </Card>

          <RenderPreview projectId={id} videoRef={videoRef} onTimeUpdate={setCurrentTime} />
        </div>
      </main>
    </div>
  );
}
