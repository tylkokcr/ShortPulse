"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Sparkles } from "lucide-react";
import { createProject } from "@/lib/api";
import { useShortPulseStore } from "@/lib/store";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ScriptEditor } from "@/components/editor/ScriptEditor";
import { DurationSelector } from "@/components/editor/DurationSelector";
import { LanguageSelector } from "@/components/editor/LanguageSelector";
import { OutroToggle } from "@/components/editor/OutroToggle";
import { VisualSelector } from "@/components/visual/VisualSelector";

export default function HomePage() {
  const router = useRouter();
  const { draft, toProjectConfig } = useShortPulseStore();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit =
    draft.topic.trim().length > 0 &&
    !submitting &&
    (draft.visualMode !== "ai_video" || draft.aiVideoAcknowledged);

  async function handleGenerate() {
    setSubmitting(true);
    setError(null);
    try {
      const project = await createProject(toProjectConfig());
      router.push(`/project/${project.config.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-6 py-16">
      <div>
        <h1 className="text-2xl font-semibold">ShortPulse</h1>
        <p className="mt-1 text-sm text-white/50">
          Turn a topic or script into a ready-to-post vertical video — free, local, open source.
        </p>
      </div>

      <Card className="flex flex-col gap-6">
        <ScriptEditor />

        <div>
          <label className="mb-1.5 block text-sm font-medium text-white/70">Language</label>
          <LanguageSelector />
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-white/70">Video length</label>
          <DurationSelector />
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-white/70">Visual style</label>
          <VisualSelector />
        </div>

        <OutroToggle />

        {error && <p className="text-sm text-red-400">{error}</p>}

        <Button onClick={handleGenerate} disabled={!canSubmit}>
          <Sparkles size={16} />
          {submitting ? "Starting render..." : "Generate video"}
        </Button>
      </Card>
    </main>
  );
}
