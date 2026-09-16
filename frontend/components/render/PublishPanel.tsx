"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  Eye,
  Loader2,
  Send,
} from "lucide-react";
import clsx from "clsx";
import {
  approvePost,
  getProjectPosts,
  getSocialConnections,
  publishProject,
} from "@/lib/api";
import type { Project, SocialConnection, SocialPost } from "@/lib/types";
import { PLATFORM_ICONS as ICONS, PLATFORM_LABELS as LABELS } from "@/lib/platforms";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

/**
 * Publish a finished video to a connected account.
 *
 * Only rendered once there is something to publish. Absent entirely on a
 * self-hosted install and on a deployment with no platforms configured —
 * getSocialConnections answers 503 there, which is read as "not available"
 * rather than surfaced as an error, because it isn't one.
 *
 * The copy is prefilled from what the scriptwriter wrote and stays
 * editable: the model produced it so that the automatic path always has
 * something to post with, not because it gets the last word.
 */
export function PublishPanel({ project }: { project: Project }) {
  const [connections, setConnections] = useState<SocialConnection[] | null>(null);
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [available, setAvailable] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const copy = project.script?.post;
  const [title, setTitle] = useState(copy?.title ?? "");
  const [description, setDescription] = useState(copy?.description ?? "");

  const projectId = project.config.id;

  const refresh = useCallback(async () => {
    try {
      const [conns, existing] = await Promise.all([
        getSocialConnections(),
        getProjectPosts(projectId),
      ]);
      setConnections(conns);
      setPosts(existing);
    } catch {
      // 503 on a deployment without publishing, 401 on a self-hosted one.
      // Neither is worth an error message about a feature that isn't there.
      setAvailable(false);
    }
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Anything still moving is polled. Uploads finish in seconds to minutes
  // and there is no socket for them — the render socket closes when the
  // render does, which is before any of this starts.
  const settling = posts.some((p) => p.status === "queued" || p.status === "uploading");
  useEffect(() => {
    if (!settling) return;
    const timer = setInterval(refresh, 4000);
    return () => clearInterval(timer);
  }, [settling, refresh]);

  if (!available || connections === null) return null;

  if (connections.length === 0) {
    return (
      <Card className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold">Publish this video</h3>
        <p className="text-xs leading-relaxed text-white/40">
          Connect a YouTube, Instagram or TikTok account and you can post a finished render
          straight from here.
        </p>
        <Link href="/connections" className="mt-1">
          <Button size="sm" variant="secondary">
            Connect an account
          </Button>
        </Link>
      </Card>
    );
  }

  async function post(connection: SocialConnection) {
    setBusy(connection.id);
    setError(null);
    try {
      await publishProject({
        project_id: projectId,
        connection_id: connection.id,
        title: title.trim(),
        description: description.trim(),
        hashtags: copy?.hashtags ?? [],
      });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't start publishing");
    } finally {
      setBusy(null);
    }
  }

  async function approve(post: SocialPost) {
    setBusy(post.id);
    try {
      await approvePost(post.id);
      await refresh();
    } catch {
      setError("Couldn't approve that post.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="flex flex-col gap-4">
      <h3 className="text-sm font-semibold">Publish this video</h3>

      <div className="flex flex-col gap-2">
        <label className="text-xs font-medium text-white/50" htmlFor="post-title">
          Title
        </label>
        <input
          id="post-title"
          value={title}
          maxLength={100}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="What this video is called"
          className="rounded-lg border border-border bg-black/30 px-3 py-2 text-sm text-white placeholder:text-white/25 focus:border-accent focus:outline-none"
        />
        <label className="mt-1 text-xs font-medium text-white/50" htmlFor="post-description">
          Description
        </label>
        <textarea
          id="post-description"
          value={description}
          maxLength={2200}
          rows={3}
          onChange={(e) => setDescription(e.target.value)}
          className="resize-y rounded-lg border border-border bg-black/30 px-3 py-2 text-sm text-white placeholder:text-white/25 focus:border-accent focus:outline-none"
        />
        {project.config.visual_mode === "stock_media" && (
          // Not a warning, a statement of what will happen. The credit is
          // a condition of the stock licence, so it is added whatever is
          // typed above — saying so is better than a user wondering where
          // the extra lines came from.
          <p className="text-xs text-white/30">
            The stock footage credits are added to the description automatically — the licence
            requires them.
          </p>
        )}
        {copy?.hashtags?.length ? (
          <p className="text-xs text-white/30">
            Hashtags: {copy.hashtags.map((h) => `#${h}`).join(" ")}
          </p>
        ) : null}
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}

      <div className="flex flex-col gap-2 border-t border-border pt-4">
        {connections.map((connection) => {
          const Icon = ICONS[connection.platform];
          const existing = posts.find((p) => p.platform === connection.platform);
          return (
            <div key={connection.id} className="flex items-center gap-2.5">
              <Icon size={16} className="shrink-0 text-white/40" />
              <span className="min-w-0 flex-1 truncate text-sm">
                {LABELS[connection.platform]}
              </span>
              {existing ? (
                <PostState
                  post={existing}
                  busy={busy === existing.id}
                  onApprove={() => approve(existing)}
                />
              ) : (
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={busy !== null || !title.trim()}
                  onClick={() => post(connection)}
                >
                  {busy === connection.id ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Send size={13} />
                  )}
                  Post
                </Button>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function PostState({
  post,
  busy,
  onApprove,
}: {
  post: SocialPost;
  busy: boolean;
  onApprove: () => void;
}) {
  if (post.status === "awaiting_review") {
    return (
      <Button size="sm" variant="gradient" disabled={busy} onClick={onApprove}>
        {busy ? <Loader2 size={13} className="animate-spin" /> : <Eye size={13} />}
        Approve
      </Button>
    );
  }

  if (post.status === "queued" || post.status === "uploading") {
    return (
      <span className="flex items-center gap-1.5 text-xs text-white/40">
        <Loader2 size={13} className="animate-spin" />
        {post.status === "queued" ? "Queued" : "Uploading"}
      </span>
    );
  }

  if (post.status === "failed") {
    return (
      <span
        title={post.error ?? undefined}
        className="flex max-w-[55%] items-center gap-1.5 text-xs text-red-400"
      >
        <AlertCircle size={13} className="shrink-0" />
        <span className="truncate">{post.error ?? "Failed"}</span>
      </span>
    );
  }

  return (
    <span className="flex items-center gap-1.5 text-xs text-white/50">
      <CheckCircle2 size={13} className="shrink-0 text-emerald-400" />
      {/* The honest answer to "why isn't my video public". An app that has
          not passed the platform's audit has its uploads forced private,
          and nothing in the API says so at the time. */}
      {post.privacy !== "public" && <span className="text-white/40">{post.privacy}</span>}
      {post.url && (
        <a
          href={post.url}
          target="_blank"
          rel="noreferrer"
          className={clsx(
            "flex items-center gap-1 underline underline-offset-2",
            "hover:text-white"
          )}
        >
          View
          <ExternalLink size={11} />
        </a>
      )}
    </span>
  );
}
