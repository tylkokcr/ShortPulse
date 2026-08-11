import type { Config } from "tailwindcss";

/**
 * The palette is monochrome plus one accent, on purpose.
 *
 * The previous one — violet accent, violet-to-teal gradient, a radial glow
 * behind the hero, gradient text on the headline — is the exact set of
 * choices every generated landing page arrives with, and a tool whose
 * whole pitch is "look at what it actually produced" cannot afford to look
 * auto-generated. So: no gradients as decoration, no glow, and colour used
 * only where it means something.
 *
 * The greys are true neutrals rather than the usual blue-tinted near-black.
 * Blue-black reads as a UI kit; neutral reads as a tool.
 */
const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#0a0a0a",
        surface: "#121212",
        "surface-hover": "#1a1a1a",
        "surface-raised": "#161616",
        border: "#242424",
        "border-strong": "#383838",
        // Signal orange. One accent, used for the thing you should look at
        // and nothing else — the record-light association is doing real
        // work for a video tool, which violet never did.
        accent: "#ff5c1a",
        "accent-hover": "#ff7438",
        // Reserved for state that is genuinely live: a render in flight, a
        // socket connected. Never decoration.
        live: "#4ade80",
      },
      fontFamily: {
        // Archivo over Inter: still a neutral grotesk, but with enough
        // width and character in the caps that a headline doesn't read as
        // the default of every framework starter.
        sans: ["var(--font-archivo)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        // Pairs with a track whose children are duplicated exactly once:
        // travelling half its width lands on the copy, so the reset is
        // invisible.
        marquee: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.5s cubic-bezier(0.16, 1, 0.3, 1) both",
        "fade-in": "fade-in 0.4s ease-out both",
        marquee: "marquee 70s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
