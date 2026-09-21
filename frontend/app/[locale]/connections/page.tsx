"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";
import clsx from "clsx";
import {
  disconnectSocial,
  getSocialConnections,
  getSocialPlatforms,
  setAutoPublish,
  startSocialConnect,
} from "@/lib/api";
import type { SocialConnection, SocialPlatform } from "@/lib/types";
import { PLATFORM_ICONS, PLATFORM_LABELS } from "@/lib/platforms";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/auth/RequireAuth";

/**
 * What the OAuth callback can report.
 *
 * It arrives as a redirect with a query parameter rather than as a thrown
 * error, because a human is looking at the screen having just pressed
 * Allow — the same reason the sign-in panel reads its failures out of the
 * URL. "Cancelled" is deliberately not phrased as a failure: pressing
 * Cancel worked exactly as intended.
 */
const CONNECT_ERRORS: Record<string, string> = {
  cancelled: "Connecting was cancelled. Nothing changed.",
  expired: "That took too long and the connection attempt expired. Try again.",
  unavailable: "Publishing isn't set up on this deployment yet.",
  failed: "Couldn't finish connecting that account. Try again.",
};

export default function ConnectionsPage() {
  return (
    <RequireAuth>
      <Connections />
    </RequireAuth>
  );
}

function Connections() {
  const [platforms, setPlatforms] = useState<SocialPlatform[] | null>(null);
  const [connections, setConnections] = useState<SocialConnection[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [available, connected] = await Promise.all([
      getSocialPlatforms(),
      getSocialConnections(),
    ]);
    setPlatforms(available.map((p) => p.id));
    setConnections(connected);
  }, []);

  useEffect(() => {
    // Read the callback's verdict before anything else, and clear it from
    // the address bar so a refresh doesn't re-report a failure the user
    // has since fixed.
    const params = new URLSearchParams(window.location.search);
    const error = params.get("error");
    if (error) {
      setNotice(CONNECT_ERRORS[error] ?? CONNECT_ERRORS.failed);
      window.history.replaceState(null, "", window.location.pathname);
    }
    load().catch((err) =>
      setNotice(err instanceof Error ? err.message : "Couldn't load your connections")
    );
  }, [load]);

  async function connect(platform: SocialPlatform) {
    setBusy(platform);
    try {
      const { url } = await startSocialConnect(platform);
      // The rule is about mutating module-scope state. Assigning
      // location.href is a browser navigation, and leaving this page for
      // the provider is the whole point of the function.
      // eslint-disable-next-line react-hooks/immutability
      window.location.href = url;
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Couldn't start connecting");
      setBusy(null);
    }
  }

  async function toggle(connection: SocialConnection) {
    // Optimistic: the toggle is the whole interaction, and waiting a round
    // trip to move a switch reads as a broken switch.
    const next = !connection.auto_publish;
    setConnections((current) =>
      current?.map((c) => (c.id === connection.id ? { ...c, auto_publish: next } : c)) ?? null
    );
    try {
      await setAutoPublish(connection.id, next);
    } catch {
      setConnections((current) =>
        current?.map((c) =>
          c.id === connection.id ? { ...c, auto_publish: connection.auto_publish } : c
        ) ?? null
      );
      setNotice("Couldn't save that. Try again.");
    }
  }

  async function remove(connection: SocialConnection) {
    setBusy(connection.id);
    try {
      await disconnectSocial(connection.id);
      setConnections((current) => current?.filter((c) => c.id !== connection.id) ?? null);
    } catch {
      setNotice("Couldn't disconnect that account.");
    } finally {
      setBusy(null);
    }
  }

  const unconnected = (platforms ?? []).filter(
    (p) => !(connections ?? []).some((c) => c.platform === p)
  );

  return (
    <AppShell section="Connections">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">Publishing</span>
        <h1 className="mt-1.5 text-3xl font-semibold tracking-tight">Connected accounts</h1>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-white/50">
          Publish a finished video straight to the places it was made for. Connecting an account
          lets you post with one click — turning on automatic posting sends each finished render
          without asking.
        </p>

        {notice && (
          <div className="mt-6 rounded-md border border-border-strong bg-surface px-4 py-3 text-sm text-white/70">
            {notice}
          </div>
        )}

        {platforms === null ? (
          <div className="mt-10 flex items-center gap-2 text-sm text-white/40">
            <Loader2 size={15} className="animate-spin" />
            Loading...
          </div>
        ) : platforms.length === 0 ? (
          <Card className="mt-8 text-sm text-white/50">
            Publishing isn&apos;t configured on this install. Self-hosted copies can set up their
            own platform credentials — see the README.
          </Card>
        ) : (
          <div className="mt-8 flex flex-col gap-3">
            {(connections ?? []).map((connection) => (
              <ConnectionRow
                key={connection.id}
                connection={connection}
                busy={busy === connection.id}
                onToggle={() => toggle(connection)}
                onRemove={() => remove(connection)}
              />
            ))}

            {unconnected.map((platform) => {
              const Icon = PLATFORM_ICONS[platform];
              return (
                <Card key={platform} className="flex items-center gap-3">
                  <Icon size={18} className="shrink-0 text-white/40" />
                  <span className="flex-1 text-sm font-medium">{PLATFORM_LABELS[platform]}</span>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => connect(platform)}
                    disabled={busy !== null}
                  >
                    {busy === platform ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Plus size={14} />
                    )}
                    Connect
                  </Button>
                </Card>
              );
            })}
          </div>
        )}
    </AppShell>
  );
}

function ConnectionRow({
  connection,
  busy,
  onToggle,
  onRemove,
}: {
  connection: SocialConnection;
  busy: boolean;
  onToggle: () => void;
  onRemove: () => void;
}) {
  const Icon = PLATFORM_ICONS[connection.platform];

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <Icon size={18} className="shrink-0 text-accent" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium">{PLATFORM_LABELS[connection.platform]}</div>
          {connection.display_name && (
            <div className="truncate text-xs text-white/40">{connection.display_name}</div>
          )}
        </div>
        <button
          type="button"
          onClick={onRemove}
          disabled={busy}
          aria-label="Disconnect"
          className="rounded p-1.5 text-white/30 transition-colors hover:bg-white/5 hover:text-red-400 disabled:opacity-40"
        >
          {busy ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
        </button>
      </div>

      <label className="flex cursor-pointer items-start gap-3 border-t border-border pt-4">
        <button
          type="button"
          role="switch"
          aria-checked={connection.auto_publish}
          onClick={onToggle}
          className={clsx(
            "relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors duration-200",
            connection.auto_publish ? "bg-accent" : "bg-white/15"
          )}
        >
          {/* left-0.5 rather than leaving it to the static position: a
              button centres its content, so an absolute knob with no left
              starts from the middle of the track. Translated from there it
              overran the right edge and pushed through the gap-3 into the
              label, which is what "automatically" was sitting under. The
              track is 36px and the knob 16px, so 2px each side and a 16px
              throw puts it flush at both ends. */}
          <span
            className={clsx(
              "absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white transition-transform duration-200",
              connection.auto_publish ? "translate-x-4" : "translate-x-0"
            )}
          />
        </button>
        <span className="text-sm">
          <span className="font-medium text-white/80">Post finished videos automatically</span>
          <span className="mt-0.5 block text-xs leading-relaxed text-white/40">
            {connection.auto_publish
              ? connection.has_published
                ? "Every render will be posted here as soon as it finishes."
                : "Your first post here still needs one click — it goes to the project page for you to approve, so you can see how it looks before handing over the keys."
              : "Off — you'll be asked each time. You can still post any video by hand."}
          </span>
        </span>
      </label>
    </Card>
  );
}
