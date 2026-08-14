/**
 * Occupies the slot where competitors put a customer-logo or testimonial
 * marquee. ShortPulse has no users to quote yet, and inventing quotes on a
 * page whose whole argument is "check our claims" would be the one lie
 * that discredits everything above it. What is verifiable today is the
 * stack — every name below is a dependency you can read in
 * requirements.txt, package.json or the engines, so this strip is social
 * proof that survives being fact-checked.
 *
 * Replace it with real testimonials once there are real users to ask.
 */
const STACK = [
  { name: "Ollama", role: "local LLM runtime" },
  { name: "Llama 3", role: "scene scripting" },
  { name: "Piper", role: "neural voiceover" },
  { name: "faster-whisper", role: "word-level timing" },
  { name: "Stable Diffusion XL", role: "image generation" },
  { name: "RealVisXL", role: "photoreal stills" },
  { name: "LTX-Video", role: "text-to-video" },
  { name: "FFmpeg", role: "assembly & encoding" },
  { name: "libass", role: "burned-in captions" },
  { name: "Pexels", role: "stock footage" },
  { name: "FastAPI", role: "render API" },
  { name: "Next.js", role: "this interface" },
];

export function BuiltOn() {
  return (
    <section className="border-y border-border/60 py-10">
      <p className="mb-6 text-center font-mono text-xs uppercase tracking-widest text-white/35">
        Built on open source you can audit
      </p>

      {/* overflow-hidden for the same reason as Examples: the mask fades the
          edges but does not clip, so the w-max track's width would otherwise
          become the page's horizontal scroll. */}
      <div className="relative overflow-hidden motion-reduce:overflow-x-auto [mask-image:linear-gradient(to_right,transparent,black_8%,black_92%,transparent)]">
        <div className="flex w-max gap-3 animate-marquee hover:[animation-play-state:paused] motion-reduce:animate-none">
          {[false, true].map((isClone) =>
            STACK.map((item) => (
              <div
                key={`${item.name}-${isClone}`}
                aria-hidden={isClone || undefined}
                className="flex shrink-0 items-baseline gap-2 rounded-full border border-border bg-surface px-4 py-2"
              >
                <span className="text-sm font-medium text-white/80">{item.name}</span>
                <span className="whitespace-nowrap text-[11px] text-white/35">{item.role}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  );
}
