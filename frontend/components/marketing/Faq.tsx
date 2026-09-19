import { ChevronDown } from "lucide-react";
import { useTranslations } from "next-intl";

/**
 * Answers are drawn from the README and the code, not from what would be
 * convenient to claim — including the ones that cost us the sale (no
 * auto-posting, no voice cloning, no commercial Japanese voice).
 *
 * That property has to survive translation, which is why the structure
 * is here and only the sentences are in the catalogue: the shape of the
 * FAQ is a product decision, and a translator changing which questions
 * get asked would be changing what the page admits to.
 */
const GROUPS = [
  { key: "videos", items: ["output", "duration", "languages", "script", "posting", "ownership"] },
  { key: "billing", items: ["pricing", "expiry", "failure", "freeTier"] },
  { key: "selfHosting", items: ["diy", "local", "roughEdges"] },
] as const;

export function Faq({ signupCredits }: { signupCredits: number }) {
  const t = useTranslations("faq");

  return (
    <section id="faq" className="mx-auto max-w-4xl scroll-mt-20 px-6 py-16">
      <div className="mb-8 flex flex-col gap-2">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">
          {t("eyebrow")}
        </span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{t("title")}</h2>
      </div>

      <div className="flex flex-col gap-8">
        {GROUPS.map((group) => (
          <div key={group.key} className="flex flex-col gap-2">
            <h3 className="mb-1 font-mono text-xs uppercase tracking-widest text-white/35">
              {t(`groups.${group.key}`)}
            </h3>
            {group.items.map((item) => (
              // <details> gives us an accordion with keyboard support and
              // no JavaScript, and its contents stay findable by in-page
              // search even while collapsed.
              <details
                key={item}
                className="group rounded-lg border border-border bg-surface transition-colors hover:border-border-strong"
              >
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3 text-sm font-medium marker:hidden">
                  {t(`items.${item}.q`)}
                  <ChevronDown
                    size={16}
                    className="shrink-0 text-white/40 transition-transform duration-200 group-open:rotate-180"
                  />
                </summary>
                <p className="px-4 pb-4 text-sm leading-relaxed text-white/50">
                  {/* Only the free-tier answer takes a value, and it is the
                      grant the server actually reports rather than a number
                      written into the copy. */}
                  {t(`items.${item}.a`, { credits: signupCredits })}
                </p>
              </details>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
