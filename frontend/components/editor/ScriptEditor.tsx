"use client";

import { useShortPulseStore } from "@/lib/store";

/**
 * Topic/script input. Users either type a topic (LLM writes the script)
 * or paste a raw script directly (LLM only segments it into scenes and
 * writes visual prompts — voiceover lines are left untouched).
 */
export function ScriptEditor() {
  const { draft, setDraft } = useShortPulseStore();

  return (
    <div className="flex flex-col gap-4">
      <div>
        <label className="mb-1.5 block text-sm font-medium text-white/70">Topic</label>
        <input
          value={draft.topic}
          onChange={(e) => setDraft({ topic: e.target.value })}
          placeholder="e.g. 3 psychology tricks that make people trust you instantly"
          className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none focus:border-accent"
        />
      </div>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-white/70">
          Raw script <span className="text-white/40">(optional — skips AI scriptwriting)</span>
        </label>
        <textarea
          value={draft.rawScript}
          onChange={(e) => setDraft({ rawScript: e.target.value })}
          placeholder="Paste your own voiceover script here if you already have one..."
          rows={6}
          className="w-full resize-none rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none focus:border-accent"
        />
      </div>
    </div>
  );
}
