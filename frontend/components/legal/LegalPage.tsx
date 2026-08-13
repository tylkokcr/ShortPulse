import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { SiteHeader } from "@/components/layout/SiteHeader";

/**
 * Shared shell for the terms, privacy and refund pages.
 *
 * These are drafts. They describe what this software actually does —
 * which data it stores, where, and what a purchase entitles you to — and
 * that part is accurate because it was written against the code. Whether
 * they satisfy a given jurisdiction is a question for a lawyer, and the
 * banner says so rather than letting the formatting imply otherwise.
 */
export function LegalPage({
  title,
  updated,
  children,
}: {
  title: string;
  updated: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen">
      <SiteHeader />
      <main className="mx-auto max-w-2xl px-6 pb-24 pt-10">
        <Link
          href="/"
          className="flex w-fit items-center gap-1.5 text-sm text-white/50 transition-colors hover:text-white"
        >
          <ArrowLeft size={14} />
          Back
        </Link>

        <h1 className="mt-6 text-3xl font-semibold tracking-tight">{title}</h1>
        <p className="label mt-2">Last updated {updated}</p>

        <div className="mt-4 rounded-md border border-accent/30 bg-accent/[0.06] p-3 text-xs leading-relaxed text-white/60">
          Draft, pending legal review. The facts about what the software does are accurate; the
          legal sufficiency of the wording is not something the author can vouch for.
        </div>

        <div className="legal mt-8 flex flex-col gap-6 text-sm leading-relaxed text-white/70">
          {children}
        </div>
      </main>
    </div>
  );
}

export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-base font-semibold text-white">{title}</h2>
      {children}
    </section>
  );
}

/**
 * A detail that is only true once the operator has been configured.
 *
 * Both legal pages have to state things — who the controller is, where
 * the data sits, whose law applies — that no source file can know. Left
 * to a placeholder they read as answered, which is the one outcome worse
 * than reading as blank: a published privacy policy naming a contact
 * nobody monitors is a promise the deployment cannot keep.
 */
export function OperatorFact({ value, missing }: { value?: string; missing: string }) {
  if (value) return <>{value}</>;
  return (
    <span className="rounded bg-amber-500/15 px-1 py-0.5 text-amber-300" title={missing}>
      [not published by this install]
    </span>
  );
}
