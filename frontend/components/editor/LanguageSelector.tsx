"use client";

import { LANGUAGE_OPTIONS, type LanguageCode } from "@/lib/types";
import { useShortPulseStore } from "@/lib/store";

export function LanguageSelector() {
  const { draft, setDraft } = useShortPulseStore();

  return (
    <select
      value={draft.language}
      onChange={(e) => setDraft({ language: e.target.value as LanguageCode })}
      className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none transition-colors focus:border-accent"
    >
      {LANGUAGE_OPTIONS.map((option) => (
        <option key={option.code} value={option.code}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
