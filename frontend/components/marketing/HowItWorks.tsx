import { PenLine, SlidersHorizontal, Download } from "lucide-react";
import { useTranslations } from "next-intl";
import { Card } from "@/components/ui/Card";

// Icons stay here, copy lives in the catalogue — the icon is a property
// of the step, the sentence is a property of the language.
const STEPS = [
  { key: "topic", icon: PenLine },
  { key: "look", icon: SlidersHorizontal },
  { key: "watch", icon: Download },
] as const;

export function HowItWorks() {
  const t = useTranslations("howItWorks");

  return (
    <section id="how-it-works" className="mx-auto max-w-6xl scroll-mt-20 px-6 py-16">
      <div className="mb-8 flex flex-col gap-2">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">{t("eyebrow")}</span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          {t("title")}
        </h2>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {STEPS.map((step, i) => (
          <Card key={step.key} interactive className="relative flex flex-col gap-3 overflow-hidden">
            {/* Oversized step numeral as texture rather than a label — the
                heading already says what the step is. */}
            <span className="pointer-events-none absolute -right-2 -top-6 font-mono text-7xl font-bold text-white/[0.04]">
              {i + 1}
            </span>
            <step.icon size={20} className="text-accent" />
            <h3 className="text-sm font-semibold">{t(`${step.key}.title`)}</h3>
            <p className="text-xs leading-relaxed text-white/50">{t(`${step.key}.detail`)}</p>
          </Card>
        ))}
      </div>
    </section>
  );
}
