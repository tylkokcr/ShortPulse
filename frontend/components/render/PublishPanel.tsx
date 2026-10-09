"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  Eye,
  Loader2,
  Send,
  Sparkles,
} from "lucide-react";
import clsx from "clsx";
import { useLocale, useTranslations } from "next-intl";
import {
  approvePost,
  getProjectPosts,
  getSocialConnections,
  publishProject,
  suggestPostCopy,
} from "@/lib/api";
import { Link } from "@/i18n/navigation";
import type { Project, SocialConnection, SocialPost } from "@/lib/types";
import { PLATFORM_ICONS as ICONS, PLATFORM_LABELS as LABELS, isComingSoon } from "@/lib/platforms";
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
// The names a project gets when nobody named it, which are no title.
const GENERIC_NAMES = new Set(["beat edit", "uploaded video"]);

/** A project name as a starting title: a file name as words, a generic
 *  name as nothing. */
function readableName(topic: string): string {
  const name = topic
    .replace(/\.(mp4|mov|m4v|webm|mkv)$/i, "")
    .replace(/\s*\(\d+\)$/, "")
    .replace(/_+/g, " ")
    .trim();
  return GENERIC_NAMES.has(name.toLowerCase()) ? "" : name.slice(0, 100);
}

export function PublishPanel({ project }: { project: Project }) {
  const [connections, setConnections] = useState<SocialConnection[] | null>(null);
  const t = useTranslations("app.publish");
  const [posts, setPosts] = useState<SocialPost[]>([]);
  const [available, setAvailable] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const copy = project.script?.post;
  const locale = useLocale();
  const [title, setTitle] = useState(copy?.title ?? readableName(project.config.topic));
  const [description, setDescription] = useState(copy?.description ?? "");
  const [tags, setTags] = useState((copy?.hashtags ?? []).map((h) => `#${h}`).join(" "));
  const [suggesting, setSuggesting] = useState(false);
  const [copied, setCopied] = useState(false);

  const projectId = project.config.id;

  const refresh = useCallback(async () => {
    try {
      const [conns, existing] = await Promise.all([
        getSocialConnections(),
        getProjectPosts(projectId),
      ]);
      // A connection to a platform that is switched off cannot post, so
      // it is not offered as somewhere to post to.
      setConnections(conns.filter((c) => !isComingSoon(c.platform)));
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
        <h3 className="text-sm font-semibold">{t("title")}</h3>
        <p className="text-xs leading-relaxed text-white/40">{t("noneIntro")}</p>
        <Link href="/connections" className="mt-1">
          <Button size="sm" variant="secondary">
            {t("connectAccount")}
          </Button>
        </Link>
      </Card>
    );
  }

  const hashtags = tags
    .split(/[\s,]+/)
    .map((h) => h.replace(/^#/, "").trim())
    .filter(Boolean)
    .slice(0, 15);

  async function suggest() {
    setSuggesting(true);
    setError(null);
    try {
      const s = await suggestPostCopy(projectId, locale);
      if (s.title) setTitle(s.title);
      if (s.description) setDescription(s.description);
      if (s.hashtags.length) setTags(s.hashtags.map((h) => `#${h}`).join(" "));
    } catch {
      setError(t("errors.suggest"));
    } finally {
      setSuggesting(false);
    }
  }

  async function post(connection: SocialConnection) {
    setBusy(connection.id);
    setError(null);
    setCopied(false);
    if (connection.platform === "tiktok") {
      // TikTok takes the video as a draft in the app's inbox and no text
      // with it (see backend social/tiktok.py), so the words go to the
      // clipboard — written now, while the click still counts as one.
      const text = [title.trim(), description.trim(), hashtags.map((h) => `#${h}`).join(" ")]
        .filter(Boolean)
        .join("\n\n");
      navigator.clipboard
        ?.writeText(text)
        .then(() => setCopied(true))
        .catch(() => undefined);
    }
    try {
      await publishProject({
        project_id: projectId,
        connection_id: connection.id,
        title: title.trim(),
        description: description.trim(),
        hashtags,
      });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.start"));
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
      setError(t("errors.approve"));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="flex flex-col gap-4">
      <h3 className="text-sm font-semibold">{t("title")}</h3>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <label className="text-xs font-medium text-white/50" htmlFor="post-title">
            {t("fieldTitle")}
          </label>
          <button
            type="button"
            onClick={suggest}
            disabled={suggesting}
            className="flex items-center gap-1 rounded border border-border px-2 py-0.5 text-[11px] text-white/60 hover:border-accent hover:text-white disabled:opacity-50"
          >
            {suggesting ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}
            {t("suggest")}
          </button>
        </div>
        <input
          id="post-title"
          value={title}
          maxLength={100}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={t("titlePlaceholder")}
          className="rounded-lg border border-border bg-black/30 px-3 py-2 text-sm text-white placeholder:text-white/25 focus:border-accent focus:outline-none"
        />
        <label className="mt-1 text-xs font-medium text-white/50" htmlFor="post-description">
          {t("fieldDescription")}
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
            {t("stockNotice")}
          </p>
        )}
        <label className="mt-1 text-xs font-medium text-white/50" htmlFor="post-tags">
          {t("fieldTags")}
        </label>
        <input
          id="post-tags"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="#futbol #edit"
          className="rounded-lg border border-border bg-black/30 px-3 py-2 text-sm text-white placeholder:text-white/25 focus:border-accent focus:outline-none"
        />
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}
      {copied && <p className="text-xs text-live">{t("tiktokCopied")}</p>}

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
                  // TikTok takes no title (it goes to the clipboard); the
                  // others need one, and say so rather than just greying out.
                  disabled={busy !== null || (connection.platform !== "tiktok" && !title.trim())}
                  title={connection.platform !== "tiktok" && !title.trim() ? t("needsTitle") : undefined}
                  onClick={() => post(connection)}
                >
                  {busy === connection.id ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <Send size={13} />
                  )}
                  {t("post")}
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
  const t = useTranslations("app.publish");

  if (post.status === "awaiting_review") {
    return (
      <Button size="sm" variant="gradient" disabled={busy} onClick={onApprove}>
        {busy ? <Loader2 size={13} className="animate-spin" /> : <Eye size={13} />}
        {t("approve")}
      </Button>
    );
  }

  if (post.status === "queued" || post.status === "uploading") {
    return (
      <span className="flex items-center gap-1.5 text-xs text-white/40">
        <Loader2 size={13} className="animate-spin" />
        {post.status === "queued" ? t("queued") : t("uploading")}
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
        <span className="truncate">{post.error ?? t("failed")}</span>
      </span>
    );
  }

  return (
    <span className="flex items-center gap-1.5 text-xs text-white/50">
      <CheckCircle2 size={13} className="shrink-0 text-emerald-400" />
      {/* The honest answer to "why isn't my video public". An app that has
          not passed the platform's audit has its uploads forced private,
          and nothing in the API says so at the time. */}
      {post.privacy === "draft" ? (
        // TikTok takes a draft, not a post: it lands in the app's inbox
        // for the user to caption and publish themselves. Saying "draft"
        // alone reads as something went half-done, and there is no link
        // to offer — the inbox exists only inside the phone app.
        <span className="text-white/40">{t("tiktokInbox")}</span>
      ) : (
        post.privacy !== "public" && <span className="text-white/40">{post.privacy}</span>
      )}
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
          {t("view")}
          <ExternalLink size={11} />
        </a>
      )}
    </span>
  );
}
