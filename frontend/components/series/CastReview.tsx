"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Loader2, Pause, Play, RefreshCw, Users } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  approveCast,
  castPortraitUrl,
  editCastMember,
  getCastVoices,
  getStreamToken,
} from "@/lib/api";
import type { CastMember, CastVoice, Project } from "@/lib/types";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

// The server's cap on faces drawn again (api/routes/projects.py).
const MAX_REDRAWS = 4;

/**
 * The people of a new story, before the episode is made.
 *
 * A first episode stops once its script is written and its cast is drawn
 * (ProjectConfig.review_cast): these are the faces and voices of forty
 * shots, and of every episode after it, so they are worth a look while
 * changing one costs a minute rather than a whole render.
 */
export function CastReview({
  project,
  onChange,
}: {
  project: Project;
  onChange: (project: Project) => void;
}) {
  const t = useTranslations("app.castReview");
  const id = project.config.id;
  const cast = project.script?.cast ?? [];
  const [token, setToken] = useState<string | null>(null);
  const [voices, setVoices] = useState<CastVoice[]>([]);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const redrawsLeft = MAX_REDRAWS - (project.config.cast_redraws ?? 0);

  useEffect(() => {
    getStreamToken(id).then((s) => setToken(s.token)).catch(() => setToken(null));
    getCastVoices(id).then(setVoices).catch(() => setVoices([]));
  }, [id]);

  async function approve() {
    setApproving(true);
    setError(null);
    try {
      onChange(await approveCast(id));
    } catch {
      setError(t("approveFailed"));
      setApproving(false);
    }
  }

  return (
    <Card className="flex flex-col gap-4 p-4">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <Users size={15} className="text-accent" />
          <h2 className="text-sm font-semibold">{t("title")}</h2>
        </div>
        <p className="text-xs leading-relaxed text-white/50">{t("intro")}</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {cast.map((member) => (
          <MemberCard
            key={member.name}
            projectId={id}
            member={member}
            token={token}
            voices={voices}
            redrawsLeft={redrawsLeft}
            onChange={onChange}
          />
        ))}
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="gradient" onClick={approve} disabled={approving}>
          {approving ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
          {t("approve")}
        </Button>
        <span className="text-xs text-white/40">{t("approveNote")}</span>
      </div>
    </Card>
  );
}

function MemberCard({
  projectId,
  member,
  token,
  voices,
  redrawsLeft,
  onChange,
}: {
  projectId: string;
  member: CastMember;
  token: string | null;
  voices: CastVoice[];
  redrawsLeft: number;
  onChange: (project: Project) => void;
}) {
  const t = useTranslations("app.castReview");
  const [look, setLook] = useState(member.look);
  const [busy, setBusy] = useState<"voice" | "look" | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Bumped after a redraw, so the browser fetches the new picture.
  const [version, setVersion] = useState(0);
  const [playing, setPlaying] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null);

  useEffect(() => () => audio.current?.pause(), []);

  // "Woman 2", not the account's internal names, and the voices that fit
  // this person first.
  const labelled = useMemo(() => {
    const counts: Record<string, number> = {};
    return voices.map((v) => {
      counts[v.kind] = (counts[v.kind] ?? 0) + 1;
      return { ...v, label: t("voiceLabel", { kind: t(`kinds.${v.kind}`), n: counts[v.kind] }) };
    });
  }, [voices, t]);
  const current = labelled.find((v) => v.voice_id === member.voice_id);

  function preview() {
    if (playing) {
      audio.current?.pause();
      setPlaying(false);
      return;
    }
    if (!current?.preview_url) return;
    audio.current?.pause();
    audio.current = new Audio(current.preview_url);
    audio.current.onended = () => setPlaying(false);
    audio.current.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
  }

  async function save(edit: { voice_id?: string; look?: string }, kind: "voice" | "look") {
    setBusy(kind);
    setError(null);
    audio.current?.pause();
    setPlaying(false);
    try {
      onChange(await editCastMember(projectId, member.name, edit));
      if (kind === "look") setVersion((v) => v + 1);
    } catch (err) {
      const text = err instanceof Error ? err.message : "";
      setError(text.startsWith("429") ? t("redrawLimit") : t(kind === "look" ? "redrawFailed" : "voiceFailed"));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex gap-3 rounded-lg border border-border p-3">
      <div className="relative aspect-[3/4] w-24 shrink-0 overflow-hidden rounded-md bg-white/[0.03]">
        {token && (
          // A signed, private picture: the optimiser would need the token
          // and would cache what is about to be redrawn.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={castPortraitUrl(projectId, member.name, token, version)}
            alt={member.name}
            className="h-full w-full object-cover"
          />
        )}
        {busy === "look" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-black/60 text-[10px] text-white/70">
            <Loader2 size={16} className="animate-spin" />
            {t("drawing")}
          </div>
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div>
          <p className="text-sm font-semibold">{member.name}</p>
          {member.role && <p className="truncate text-[11px] text-white/45">{member.role}</p>}
        </div>

        {labelled.length > 0 && (
          <div className="flex items-center gap-1.5">
            <select
              aria-label={t("voice")}
              value={member.voice_id ?? ""}
              disabled={busy !== null}
              onChange={(e) => save({ voice_id: e.target.value }, "voice")}
              className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2 py-1 text-xs"
            >
              {!current && <option value={member.voice_id ?? ""}>{t("voiceCurrent")}</option>}
              {labelled.map((v) => (
                <option key={v.voice_id} value={v.voice_id}>
                  {v.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={preview}
              disabled={!current?.preview_url}
              aria-label={t("listen")}
              title={t("listen")}
              className="rounded-md border border-border p-1.5 text-white/60 transition-colors hover:text-white disabled:opacity-30"
            >
              {playing ? <Pause size={12} /> : <Play size={12} />}
            </button>
          </div>
        )}

        <label className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wide text-white/35">{t("look")}</span>
          <textarea
            value={look}
            onChange={(e) => setLook(e.target.value)}
            rows={3}
            maxLength={300}
            disabled={busy !== null}
            className="resize-none rounded-md border border-border bg-surface px-2 py-1.5 text-xs leading-relaxed"
          />
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={busy !== null || redrawsLeft <= 0 || look.trim().length < 3 || look.trim() === member.look}
            onClick={() => save({ look: look.trim() }, "look")}
          >
            <RefreshCw size={12} />
            {t("redraw")}
          </Button>
          <span className="text-[10px] text-white/35">{t("redrawsLeft", { count: Math.max(redrawsLeft, 0) })}</span>
        </div>
        {error && <p className="text-[11px] text-red-400">{error}</p>}
      </div>
    </div>
  );
}
