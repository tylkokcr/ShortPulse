"use client";

import { useEffect, useState } from "react";
import { Loader2, Send } from "lucide-react";
import clsx from "clsx";
import { useTranslations } from "next-intl";
import { getTikTokCreator } from "@/lib/api";
import type { TikTokChoices, TikTokCreator, TikTokPrivacy } from "@/lib/types";
import { Button } from "@/components/ui/Button";

const MUSIC_POLICY = "https://www.tiktok.com/legal/page/global/music-usage-confirmation/en";
const BRANDED_POLICY = "https://www.tiktok.com/legal/page/global/bc-policy/en";

/**
 * A direct post to TikTok, the way TikTok requires it to be made.
 *
 * Every rule here is one of TikTok's conditions for the `video.publish`
 * scope (its Content Posting API UX guidelines), not a design choice:
 *
 *  - The account it goes to is shown, by name, before anything is sent.
 *  - Who can see it is chosen from the levels TikTok lists for this
 *    account, with nothing preselected; posting waits until one is picked.
 *  - Comments, duets and stitches start off and are switched on by the
 *    person; one the account has turned off in TikTok cannot be.
 *  - Commercial content is disclosed by the person: once disclosure is on,
 *    one of "your brand" and "branded content" must be ticked, the label
 *    TikTok will apply is said, and branded content cannot be private.
 *  - The music and branded-content terms are linked where the button is.
 *  - A video longer than the account may post is refused here, not after
 *    an upload.
 *
 * The draft path stays beside it for anyone who would rather finish the
 * post in the TikTok app.
 */
export function TikTokComposer({
  connectionId,
  caption,
  durationS,
  aiGenerated,
  busy,
  onPost,
  onDraft,
}: {
  connectionId: string;
  caption: string;
  durationS: number | null | undefined;
  aiGenerated: boolean;
  busy: boolean;
  onPost: (choices: TikTokChoices) => void;
  onDraft: () => void;
}) {
  const t = useTranslations("app.publish.tiktok");
  const [creator, setCreator] = useState<TikTokCreator | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [privacy, setPrivacy] = useState<TikTokPrivacy | "">("");
  const [allowComment, setAllowComment] = useState(false);
  const [allowDuet, setAllowDuet] = useState(false);
  const [allowStitch, setAllowStitch] = useState(false);
  const [disclose, setDisclose] = useState(false);
  const [brandOrganic, setBrandOrganic] = useState(false);
  const [brandContent, setBrandContent] = useState(false);

  useEffect(() => {
    let live = true;
    getTikTokCreator(connectionId)
      .then((info) => live && setCreator(info))
      .catch((err) => live && setLoadError(err instanceof Error ? err.message : ""));
    return () => {
      live = false;
    };
  }, [connectionId]);

  if (loadError !== null) {
    return (
      <div className="flex flex-col gap-2 rounded-lg border border-border bg-black/20 p-3">
        <p className="text-xs text-red-400">{t("loadFailed", { reason: loadError })}</p>
        <Button size="sm" variant="secondary" disabled={busy} onClick={onDraft}>
          {t("draft")}
        </Button>
      </div>
    );
  }
  if (creator === null) {
    return (
      <p className="flex items-center gap-2 text-xs text-white/40">
        <Loader2 size={12} className="animate-spin" />
        {t("loading")}
      </p>
    );
  }

  const tooLong =
    Boolean(durationS && creator.max_duration_s) && (durationS as number) > creator.max_duration_s;
  const brandedPrivate = brandContent && privacy === "SELF_ONLY";
  const disclosureIncomplete = disclose && !brandOrganic && !brandContent;
  const ready = privacy !== "" && !tooLong && !brandedPrivate && !disclosureIncomplete;
  const blocker = tooLong
    ? t("tooLong", { max: creator.max_duration_s })
    : privacy === ""
      ? t("needsPrivacy")
      : disclosureIncomplete
        ? t("pickOne")
        : brandedPrivate
          ? t("brandedNotPrivate")
          : null;

  const interactions = [
    { key: "comment", on: allowComment, set: setAllowComment, off: creator.comment_disabled },
    { key: "duet", on: allowDuet, set: setAllowDuet, off: creator.duet_disabled },
    { key: "stitch", on: allowStitch, set: setAllowStitch, off: creator.stitch_disabled },
  ] as const;

  const linkClass = "underline underline-offset-2 hover:text-white";
  const music = (chunks: React.ReactNode) => (
    <a href={MUSIC_POLICY} target="_blank" rel="noreferrer" className={linkClass}>
      {chunks}
    </a>
  );
  const branded = (chunks: React.ReactNode) => (
    <a href={BRANDED_POLICY} target="_blank" rel="noreferrer" className={linkClass}>
      {chunks}
    </a>
  );

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-black/20 p-3">
      <div className="flex items-center gap-2.5">
        {creator.avatar_url ? (
          // Served by TikTok for this account; small, and not worth the
          // optimiser's round trip.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={creator.avatar_url} alt="" className="h-7 w-7 rounded-full object-cover" />
        ) : null}
        <p className="text-xs text-white/70">
          {t.rich("postingAs", {
            name: () => (
              <span className="font-medium text-white">
                {creator.nickname || creator.username}
                {creator.username ? <span className="text-white/40"> @{creator.username}</span> : null}
              </span>
            ),
          })}
        </p>
      </div>

      <div className="flex flex-col gap-1">
        <span className="text-[11px] uppercase tracking-wide text-white/40">{t("caption")}</span>
        <p className="max-h-24 overflow-y-auto whitespace-pre-wrap rounded border border-border bg-black/30 px-2.5 py-2 text-xs text-white/70">
          {caption || "—"}
        </p>
      </div>

      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-white/60">{t("privacy")}</span>
        <select
          value={privacy}
          onChange={(e) => setPrivacy(e.target.value as TikTokPrivacy | "")}
          className="rounded-lg border border-border bg-black/30 px-2.5 py-2 text-sm text-white focus:border-accent focus:outline-none"
        >
          <option value="" disabled>
            {t("privacyPlaceholder")}
          </option>
          {creator.privacy_levels.map((level) => (
            <option key={level} value={level} disabled={brandContent && level === "SELF_ONLY"}>
              {t(`levels.${level}`)}
            </option>
          ))}
        </select>
      </label>

      <div className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-white/60">{t("allow")}</span>
        <div className="flex flex-wrap gap-x-4 gap-y-1.5">
          {interactions.map((item) => (
            <label
              key={item.key}
              className={clsx("flex items-center gap-1.5 text-xs", item.off ? "text-white/30" : "text-white/70")}
              title={item.off ? t("disabledByCreator") : undefined}
            >
              <input
                type="checkbox"
                checked={item.on && !item.off}
                disabled={item.off}
                onChange={(e) => item.set(e.target.checked)}
                className="accent-[rgb(var(--accent))]"
              />
              {t(`interactions.${item.key}`)}
              {item.off && <span className="text-[10px] text-white/30">({t("disabledByCreator")})</span>}
            </label>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2 border-t border-border pt-3">
        <label className="flex items-start gap-2 text-xs text-white/70">
          <input
            type="checkbox"
            checked={disclose}
            onChange={(e) => {
              setDisclose(e.target.checked);
              if (!e.target.checked) {
                setBrandOrganic(false);
                setBrandContent(false);
              }
            }}
            className="mt-0.5 accent-[rgb(var(--accent))]"
          />
          <span>
            <span className="font-medium text-white/80">{t("disclose")}</span>
            <span className="block text-[11px] text-white/40">{t("discloseHint")}</span>
          </span>
        </label>
        {disclose && (
          <div className="ml-5 flex flex-col gap-2">
            <label className="flex items-start gap-2 text-xs text-white/70">
              <input
                type="checkbox"
                checked={brandOrganic}
                onChange={(e) => setBrandOrganic(e.target.checked)}
                className="mt-0.5 accent-[rgb(var(--accent))]"
              />
              <span>
                {t("yourBrand")}
                <span className="block text-[11px] text-white/40">{t("yourBrandHint")}</span>
              </span>
            </label>
            <label className="flex items-start gap-2 text-xs text-white/70">
              <input
                type="checkbox"
                checked={brandContent}
                onChange={(e) => {
                  setBrandContent(e.target.checked);
                  if (e.target.checked && privacy === "SELF_ONLY") setPrivacy("");
                }}
                className="mt-0.5 accent-[rgb(var(--accent))]"
              />
              <span>
                {t("branded")}
                <span className="block text-[11px] text-white/40">{t("brandedHint")}</span>
              </span>
            </label>
            {(brandOrganic || brandContent) && (
              <p className="text-[11px] text-accent">
                {brandContent ? t("labelPaid") : t("labelPromo")}
              </p>
            )}
          </div>
        )}
      </div>

      {aiGenerated && <p className="text-[11px] text-white/40">{t("aigc")}</p>}

      <p className="text-[11px] leading-relaxed text-white/40">
        {brandContent
          ? t.rich("consentBranded", { music, branded })
          : t.rich("consent", { music })}
      </p>

      {blocker && <p className="text-[11px] text-white/50">{blocker}</p>}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="gradient"
          disabled={!ready || busy}
          onClick={() =>
            privacy &&
            onPost({
              privacy_level: privacy,
              allow_comment: allowComment && !creator.comment_disabled,
              allow_duet: allowDuet && !creator.duet_disabled,
              allow_stitch: allowStitch && !creator.stitch_disabled,
              brand_organic: disclose && brandOrganic,
              brand_content: disclose && brandContent,
            })
          }
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
          {t("post")}
        </Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={onDraft} title={t("draftHint")}>
          {t("draft")}
        </Button>
      </div>
    </div>
  );
}
