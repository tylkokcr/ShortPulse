"use client";

import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import { ArrowLeft, ListTree, Pencil } from "lucide-react";
import clsx from "clsx";
import { useShortPulseStore } from "@/lib/store";
import { Card } from "@/components/ui/Card";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { AccountBar } from "@/components/auth/AccountBar";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { RenderPreview } from "@/components/render/RenderPreview";
import { TranscriptPanel } from "@/components/render/TranscriptPanel";
import { StockCredits } from "@/components/render/StockCredits";
import { EditPanel } from "@/components/render/EditPanel";
import { PublishPanel } from "@/components/render/PublishPanel";
import { getCredits, getProject, getStreamToken, regenerateScene, submitFeedback } from "@/lib/api";
import { InsufficientCreditsError } from "@/lib/api";
import type { Project } from "@/lib/types";

export default function ProjectPage(props: { params: Promise<{ id: string }> }) {
  // Next 15 made route params a promise. This is a client component, so it
  // unwraps with use() rather than await.
  const { id } = use(props.params);

  return (
    <RequireAuth>
      <Project id={id} />
    </RequireAuth>
  );
}

function Project({ id }: { id: string }) {
  const activeProject = useShortPulseStore((s) => s.activeProject);
  const bumpVideoVersion = useShortPulseStore((s) => s.bumpVideoVersion);
  const setCredits = useShortPulseStore((s) => s.setCredits);

  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [tab, setTab] = useState<"scenes" | "edit">("scenes");

  // The store only holds a project this tab created. Arriving from the
  // library — or reloading — has to fetch it, and that is also what makes
  // the caption track available to edit.
  const [project, setProject] = useState<Project | null>(activeProject);
  useEffect(() => {
    if (activeProject?.config.id === id) {
      setProject(activeProject);
      return;
    }
    getProject(id).then(setProject).catch(() => {});
  }, [id, activeProject]);

  // Read from the fetched project rather than the store: the store only
  // holds what this tab created, so arriving from the library or reloading
  // would otherwise show "the scriptwriter is working on this" for a video
  // that finished days ago.
  const script = project?.script;

  // Which scene is being re-drawn, and what went wrong last time.
  const [regeneratingIndex, setRegeneratingIndex] = useState<number | null>(null);
  const [regenerateError, setRegenerateError] = useState<string | null>(null);

  // One signed credential for every scene frame on the page. The <img>
  // elements cannot send a header, and minting one per row would be a
  // dozen round trips for a token that is already scoped to the project.
  const [thumbToken, setThumbToken] = useState<string | null>(null);
  useEffect(() => {
    if (project?.status !== "complete") return;
    getStreamToken(id).then((t) => setThumbToken(t.token)).catch(() => setThumbToken(null));
  }, [id, project?.status]);

  // Keyed for lookup by row. Scene-level verdicts only — the one with a
  // null index is the video as a whole and belongs elsewhere.
  const verdicts = new Map<number, NonNullable<Project["feedback"]>[number]>();
  let videoVerdict: NonNullable<Project["feedback"]>[number] | undefined;
  for (const f of project?.feedback ?? []) {
    if (f.scene_index === null) videoVerdict = f;
    else verdicts.set(f.scene_index, f);
  }

  async function handleFlag(index: number, reason: string, note: string) {
    try {
      setProject(
        await submitFeedback(id, {
          scene_index: index,
          rating: "down",
          reason,
          note: note || null,
        })
      );
    } catch {
      // Deliberately quiet. A failed complaint is not worth a second
      // error on top of whatever the user was already unhappy about, and
      // the re-roll below it still works.
    }
  }

  async function handleVerdict(rating: "up" | "down") {
    try {
      setProject(await submitFeedback(id, { rating }));
    } catch {
      // Same reasoning as a scene flag: a failed opinion is not worth an
      // error on top of whatever prompted it.
    }
  }

  async function handleRegenerate(index: number, prompt: string, negativePrompt: string) {
    setRegeneratingIndex(index);
    setRegenerateError(null);
    try {
      const updated = await regenerateScene(id, index, {
        prompt: prompt || null,
        negative_prompt: negativePrompt,
      });
      setProject(updated);
      // final.mp4 was overwritten in place and the project is still
      // "complete", so nothing else would tell the player to re-fetch it.
      bumpVideoVersion();
      // And the balance in the header is now a credit out of date.
      getCredits().then(setCredits).catch(() => {});
    } catch (err) {
      setRegenerateError(
        err instanceof InsufficientCreditsError
          ? `Not enough credits — you have ${err.balance} and this costs ${err.required}.`
          : "That didn't work. Nothing was charged; try again."
      );
    } finally {
      setRegeneratingIndex(null);
    }
  }

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
          <div className="animate-fade-up flex flex-col gap-4">
            <div className="inline-flex w-fit rounded-md border border-border bg-surface p-1">
              {([
                { id: "scenes", label: "Breakdown", icon: ListTree },
                { id: "edit", label: "Edit", icon: Pencil },
              ] as const).map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setTab(t.id)}
                  aria-pressed={tab === t.id}
                  className={clsx(
                    "flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all duration-200",
                    tab === t.id
                      ? "bg-surface-raised text-white shadow-sm"
                      : "text-white/50 hover:text-white/80"
                  )}
                >
                  <t.icon size={14} />
                  {t.label}
                </button>
              ))}
            </div>

            {tab === "scenes" ? (
              <Card className="flex flex-col gap-4 p-4">
                {!script ? (
                  <p className="text-sm text-white/40">
                    {project?.config.source === "upload"
                      ? "This video was uploaded, so it has no generated scenes — see the Edit tab for its captions."
                      : "The AI scriptwriter is working on this — scenes will appear here once generated."}
                  </p>
                ) : (
                  <>
                    {regenerateError && (
                      <p className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
                        {regenerateError}
                      </p>
                    )}
                    <TranscriptPanel
                      script={script}
                      currentTime={currentTime}
                      onSeek={handleSeek}
                      regenerate={{
                        canRegenerate: Boolean(project?.can_regenerate),
                        blockedReason: project?.regenerate_blocked_reason,
                        busyIndex: regeneratingIndex,
                        onRegenerate: handleRegenerate,
                      }}
                      feedback={{ verdicts, onFlag: handleFlag }}
                      projectId={id}
                      thumbToken={thumbToken}
                    />
                  </>
                )}
                {script && <StockCredits script={script} />}
              </Card>
            ) : project ? (
              <EditPanel project={project} onApplied={setProject} onSeek={handleSeek} />
            ) : (
              <Card className="text-sm text-white/40">Loading...</Card>
            )}
          </div>

          <div className="flex flex-col gap-4">
            <RenderPreview
              projectId={id}
              videoRef={videoRef}
              onTimeUpdate={setCurrentTime}
              verdict={{ current: videoVerdict, onSubmit: handleVerdict }}
            />
            {/* Only once there is a file to publish. Before that the panel
                would be offering to post a video that does not exist. */}
            {project?.status === "complete" && <PublishPanel project={project} />}
          </div>
        </div>
      </main>
    </div>
  );
}
