"use client";

import { useCallback, useEffect, useState } from "react";
import clsx from "clsx";
import { FolderOpen, Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { deleteProject, listProjects } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { ProjectCard } from "@/components/library/ProjectCard";
import { ProjectCardSkeleton } from "@/components/library/ProjectCardSkeleton";
import { Reveal } from "@/components/ui/Reveal";

/**
 * Everything the signed-in user has made.
 *
 * The backend has stored projects per user since the Postgres store landed
 * — this is the first screen that reads them back. Which also means it is
 * the first place a render that failed weeks ago becomes visible, so
 * failures are shown rather than filtered out: a project that cost credits
 * and produced nothing is exactly what someone comes here to find.
 */
export default function LibraryPage() {
  return (
    <RequireAuth>
      <Library />
    </RequireAuth>
  );
}

/**
 * Newest first.
 *
 * Sorted here rather than in the query, because the ordering is a fact
 * about this screen: the list endpoint is also what the project page and
 * the clip list read, and neither wants its rows rearranged. `created_at`
 * is serialised without a zone, so it is compared as a string — which is
 * safe for exactly this format, where lexical order is chronological
 * order, and would not be the moment an offset appeared.
 */
function newestFirst(projects: Project[]): Project[] {
  return [...projects].sort((a, b) =>
    (b.config.created_at ?? "").localeCompare(a.config.created_at ?? "")
  );
}

/** Shared by the skeletons and the real cards: the placeholder only does
 *  its job if the grid it fills is the grid that replaces it. */
type Kind = "all" | "ai" | "uploads" | "edits";
const KINDS: Kind[] = ["all", "ai", "uploads", "edits"];

/** Which shelf a project sits on. An extraction and the clips cut from it
 *  are uploads; they started as a video someone brought. */
function kindOf(project: Project): Exclude<Kind, "all"> {
  if (project.config.source === "beat_edit") return "edits";
  if (project.config.source === "upload") return "uploads";
  return "ai";
}

const GRID = "mt-6 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 lg:grid-cols-5";

function Library() {
  const t = useTranslations("app.library");
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Kept in the address so a shelf survives going into a video and back,
  // and can be linked to. Read once on the first render, on the client.
  const [kind, setKind] = useState<Kind>(() => {
    if (typeof window === "undefined") return "all";
    const asked = new URLSearchParams(window.location.search).get("kind");
    return (KINDS as string[]).includes(asked ?? "") ? (asked as Kind) : "all";
  });
  function choose(next: Kind) {
    setKind(next);
    const url = new URL(window.location.href);
    if (next === "all") url.searchParams.delete("kind");
    else url.searchParams.set("kind", next);
    window.history.replaceState(null, "", url);
  }
  const shown = projects?.filter((p) => kind === "all" || kindOf(p) === kind) ?? null;
  const counts: Record<Kind, number> = {
    all: projects?.length ?? 0,
    ai: projects?.filter((p) => kindOf(p) === "ai").length ?? 0,
    uploads: projects?.filter((p) => kindOf(p) === "uploads").length ?? 0,
    edits: projects?.filter((p) => kindOf(p) === "edits").length ?? 0,
  };

  useEffect(() => {
    listProjects()
      .then((loaded) => setProjects(newestFirst(loaded)))
      .catch((err) => setError(err instanceof Error ? err.message : t("loadFailed")));
  }, [t]);

  const handleDelete = useCallback(async (id: string) => {
    // Removed from the list first: the request is authoritative, but
    // waiting on a round trip to acknowledge a click the user already
    // confirmed makes the page feel broken.
    setProjects((current) => current?.filter((p) => p.config.id !== id) ?? null);
    try {
      await deleteProject(id);
    } catch {
      // Put it back — it is still there on the server.
      setProjects(newestFirst(await listProjects()));
    }
  }, []);

  return (
    <AppShell section="library" wide>
        <div className="animate-fade-up flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{t("title")}</h1>
            <p className="mt-2 text-sm text-white/50">
              {projects === null
                ? t("loading")
                : projects.length === 0
                  ? t("none")
                  : t("count", { count: projects.length })}
            </p>
          </div>
          <Link href="/">
            <Button variant="gradient">
              <Plus size={16} />
              {t("newVideo")}
            </Button>
          </Link>
        </div>

        {/* Three shelves for three different things: videos made from a
            topic, videos someone brought (captioned, dubbed, cut into
            clips) and edits cut from their clips. One grid of all of
            them read as a pile. A shelf with nothing on it still shows,
            at zero, so the three are always the same three. */}
        {projects && projects.length > 0 && (
          <div
            role="tablist"
            aria-label={t("shelvesLabel")}
            className="mt-6 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none]"
          >
            {KINDS.map((option) => (
              <button
                key={option}
                type="button"
                role="tab"
                aria-selected={kind === option}
                onClick={() => choose(option)}
                className={clsx(
                  "flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-colors",
                  kind === option
                    ? "border-accent/60 bg-accent/[0.08] text-white"
                    : "border-border text-white/50 hover:border-border-strong hover:text-white/80"
                )}
              >
                {t(`shelves.${option}`)}
                <span className="font-mono text-[10px] text-white/35">{counts[option]}</span>
              </button>
            ))}
          </div>
        )}

        {error && (
          <p className="mt-8 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            {error}
          </p>
        )}

        {/* Ten, because that is two full rows at the widest column count
            and one screen's worth — enough to say "a grid of videos is
            coming", not so many that a library of three deals out a wall
            of boxes that were never there. */}
        {projects === null && !error && (
          <div className={GRID}>
            {Array.from({ length: 10 }, (_, i) => (
              <ProjectCardSkeleton key={i} />
            ))}
          </div>
        )}

        {projects?.length === 0 && (
          <div className="animate-fade-up mt-20 flex flex-col items-center gap-4 text-center">
            <FolderOpen size={32} className="text-white/20" />
            <div>
              <p className="text-sm font-medium">{t("emptyTitle")}</p>
              <p className="mt-1 max-w-sm text-sm text-white/40">
                {t("emptyBody")}
              </p>
            </div>
            <Link href="/">
              <Button variant="gradient">
                {t("startOne")}
                <Plus size={16} />
              </Button>
            </Link>
          </div>
        )}

        {shown && projects && projects.length > 0 && shown.length === 0 && (
          <p className="mt-12 text-center text-sm text-white/40">{t(`shelfEmpty.${kind}`)}</p>
        )}

        {shown && shown.length > 0 && (
          <div className={GRID}>
            {shown.map((project, i) => (
              // Staggered by column rather than by absolute index: a
              // library of eighty projects would otherwise have the last
              // one waiting four seconds. The row resets the delay, so
              // each row deals itself out as it scrolls into view.
              <Reveal key={project.config.id} delay={(i % 5) * 55}>
                <ProjectCard project={project} onDelete={handleDelete} />
              </Reveal>
            ))}
          </div>
        )}
    </AppShell>
  );
}
