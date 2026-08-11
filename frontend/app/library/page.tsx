"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { FolderOpen, Loader2, Plus } from "lucide-react";
import { deleteProject, listProjects } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { AccountBar } from "@/components/auth/AccountBar";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { ProjectCard } from "@/components/library/ProjectCard";

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

function Library() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load projects"));
  }, []);

  const handleDelete = useCallback(async (id: string) => {
    // Removed from the list first: the request is authoritative, but
    // waiting on a round trip to acknowledge a click the user already
    // confirmed makes the page feel broken.
    setProjects((current) => current?.filter((p) => p.config.id !== id) ?? null);
    try {
      await deleteProject(id);
    } catch {
      // Put it back — it is still there on the server.
      setProjects(await listProjects());
    }
  }, []);

  return (
    <div className="relative min-h-screen">
      <SiteHeader right={<AccountBar />} showLibrary />

      <main className="mx-auto max-w-6xl px-6 pb-24 pt-10">
        <div className="animate-fade-up flex flex-wrap items-end justify-between gap-4">
          <div>
            <span className="font-mono text-xs uppercase tracking-widest text-accent">Library</span>
            <h1 className="mt-1.5 text-3xl font-semibold tracking-tight">Your videos</h1>
            <p className="mt-2 text-sm text-white/50">
              {projects === null
                ? "Loading..."
                : projects.length === 0
                  ? "Nothing here yet."
                  : `${projects.length} project${projects.length === 1 ? "" : "s"}`}
            </p>
          </div>
          <Link href="/">
            <Button variant="gradient">
              <Plus size={16} />
              New video
            </Button>
          </Link>
        </div>

        {error && (
          <p className="mt-8 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            {error}
          </p>
        )}

        {projects === null && !error && (
          <div className="mt-20 flex justify-center">
            <Loader2 size={22} className="animate-spin text-white/30" />
          </div>
        )}

        {projects?.length === 0 && (
          <div className="animate-fade-up mt-20 flex flex-col items-center gap-4 text-center">
            <FolderOpen size={32} className="text-white/20" />
            <div>
              <p className="text-sm font-medium">No projects yet</p>
              <p className="mt-1 max-w-sm text-sm text-white/40">
                Generate one from a topic, or upload a video you already have and let it write the
                captions.
              </p>
            </div>
            <Link href="/">
              <Button variant="gradient">
                Start one
                <Plus size={16} />
              </Button>
            </Link>
          </div>
        )}

        {projects && projects.length > 0 && (
          <div className="animate-fade-up mt-8 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 lg:grid-cols-5">
            {projects.map((project) => (
              <ProjectCard key={project.config.id} project={project} onDelete={handleDelete} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
