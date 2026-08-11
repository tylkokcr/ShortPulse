import { ChevronDown } from "lucide-react";

/**
 * Answers are drawn from the README and the code, not from what would be
 * convenient to claim — including the ones that cost us the sale (no
 * auto-posting, no voice cloning, no commercial Japanese voice).
 */
const GROUPS: { group: string; items: { q: string; a: string }[] }[] = [
  {
    group: "Videos",
    items: [
      {
        q: "What exactly do I get?",
        a: "A 1080x1920 MP4, H.264/AAC, with the voiceover, word-synced captions burned in, background music ducked under the voice, and an optional closing card. No watermark, on every plan including the free credits.",
      },
      {
        q: "How long does a render take?",
        a: "Measured on an Apple Silicon M-series: a short video with stock footage takes roughly 45 seconds end to end. The AI-stills mode takes about 78 seconds per scene, so ~7 minutes for a short. A dedicated GPU is considerably quicker.",
      },
      {
        q: "Which languages are supported?",
        a: "Nine: English, Turkish, Spanish, French, German, Portuguese, Arabic, Russian and Italian. Script, voiceover and subtitles are all produced in the language you pick. Japanese is missing because Piper ships no Japanese voice we can use commercially.",
      },
      {
        q: "Can I use my own script?",
        a: "Yes. Paste it and the LLM only splits it into scenes and writes the visual prompts — your wording reaches the voiceover untouched.",
      },
      {
        q: "Do you post to TikTok or YouTube for me?",
        a: "No. ShortPulse renders the file and hands it to you; publishing is still your job. If auto-posting is the feature you actually want, another tool will serve you better today.",
      },
      {
        q: "Do I own what I make?",
        a: "Yes. Download it and do what you like with it. When you use the stock-footage mode, credit the videographers in your post description — the project page collects the names and links for you, and Pexels' licence requires it.",
      },
    ],
  },
  {
    group: "Credits & billing",
    items: [
      {
        q: "How does pricing work?",
        a: "Credits, bought once. A render costs 1 credit with stock footage, 3 with AI stills and 10 with local text-to-video, doubled for medium length and tripled for long. You see the exact cost before you start it.",
      },
      {
        q: "Do credits expire?",
        a: "No. Nothing renews and nothing resets monthly — the ledger has no expiry, so credits sit there until you spend them.",
      },
      {
        q: "What if a render fails?",
        a: "The credits go back automatically. Refunds are tied to the project and can only happen once, so a failure can't leave you charged for a video you never got.",
      },
      {
        q: "Is there really a free tier?",
        a: "15 credits when you sign up, no card. That's five videos with AI stills, or fifteen with stock footage.",
      },
    ],
  },
  {
    group: "Self-hosting",
    items: [
      {
        q: "Can I run this myself instead?",
        a: "Yes, and it costs nothing. The whole thing is MIT — clone it, point it at your own Ollama and GPU, and there are no accounts, no credits and no limits. Credits exist only because the hosted instance runs on hardware somebody pays for.",
      },
      {
        q: "Is it genuinely local?",
        a: "Scripting, voiceover, transcription, image generation and rendering all run on your machine. The one stage that reaches the network is the stock-footage mode, which fetches from Pexels — pick another visual mode and it's offline after the first model download.",
      },
      {
        q: "What are the rough edges?",
        a: "The AI-stills mode mangles faces, hands and on-screen text. Local text-to-video needs a serious GPU to be practical. Small local LLMs sometimes return fewer scenes than asked. All of it is in the README's Known limitations section.",
      },
    ],
  },
];

export function Faq() {
  return (
    <section id="faq" className="mx-auto max-w-4xl scroll-mt-20 px-6 py-16">
      <div className="mb-8 flex flex-col gap-2">
        <span className="font-mono text-xs uppercase tracking-widest text-accent">FAQ</span>
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          The questions worth asking first
        </h2>
      </div>

      <div className="flex flex-col gap-8">
        {GROUPS.map((group) => (
          <div key={group.group} className="flex flex-col gap-2">
            <h3 className="mb-1 font-mono text-xs uppercase tracking-widest text-white/35">
              {group.group}
            </h3>
            {group.items.map((item) => (
              // <details> gives us an accordion with keyboard support and
              // no JavaScript, and its contents stay findable by in-page
              // search even while collapsed.
              <details
                key={item.q}
                className="group rounded-lg border border-border bg-surface transition-colors hover:border-border-strong"
              >
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3 text-sm font-medium marker:hidden">
                  {item.q}
                  <ChevronDown
                    size={16}
                    className="shrink-0 text-white/40 transition-transform duration-200 group-open:rotate-180"
                  />
                </summary>
                <p className="px-4 pb-4 text-sm leading-relaxed text-white/50">{item.a}</p>
              </details>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
