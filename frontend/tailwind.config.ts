import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#0b0b0f",
        surface: "#15151c",
        "surface-hover": "#1d1d26",
        "surface-raised": "#1a1a22",
        border: "#26262f",
        "border-strong": "#36363f",
        accent: "#7c5cff",
        "accent-hover": "#8f73ff",
        // Second hue for the pulse/waveform motif — used sparingly (logo,
        // one hero highlight, CTA glow), never as a wall-to-wall gradient.
        pulse: "#2dd4bf",
        "pulse-hover": "#45e0cc",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      backgroundImage: {
        "accent-gradient": "linear-gradient(135deg, #7c5cff 0%, #5b8cff 55%, #2dd4bf 100%)",
        "radial-fade": "radial-gradient(circle at top, rgba(124,92,255,0.16), transparent 60%)",
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
