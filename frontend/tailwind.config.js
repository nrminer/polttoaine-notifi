/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ink: "rgb(var(--c-ink) / <alpha-value>)",
        muted: "rgb(var(--c-muted) / <alpha-value>)",
        secondary: "rgb(var(--c-secondary) / <alpha-value>)",
        surface: "rgb(var(--c-surface) / <alpha-value>)",
        line: "rgb(var(--c-line) / <alpha-value>)",
        signalUp: "#ff8b6e",
        signalUpBg: "#3a1812",
        signalDown: "#7fd7b2",
        signalDownBg: "#15362b",
        brand: "#ffb000",
        brandHover: "#d98d00",
        accent: "#8fb3c7",
        nordDark: "#10100e",
        cycleStable: "#7fd7b2",
        cycleRising: "#ffb000",
        cyclePeak: "#ff8b6e",
        cycleFalling: "#8fb3c7",
        recommendWait: "#7fd7b2",
        recommendBuy: "#8fb3c7",
        recommendNeutral: "#999482",
      },
      fontFamily: {
        display: ['"Saira Condensed"', "sans-serif"],
        body: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "monospace"],
      },
      fontSize: {
        hero: ["4rem", { lineHeight: "1", letterSpacing: "0", fontWeight: "900" }],
        "hero-sm": ["3rem", { lineHeight: "1", letterSpacing: "0", fontWeight: "900" }],
      },
      letterSpacing: {
        tightest: "0",
      },
      boxShadow: {
        card: "var(--shadow-card)",
        "card-hover": "var(--shadow-card-hover)",
        "glow-brand": "0 0 0 2px rgb(255 176 0 / 0.45)",
        "glow-accent": "0 0 0 2px rgb(143 179 199 / 0.40)",
        "inner-brand": "inset 0 0 0 1px rgb(255 176 0 / 0.28)",
      },
      animation: {
        "fade-up": "fadeUp 0.5s steps(5, end) forwards",
        "fade-in": "fadeIn 0.3s steps(3, end) forwards",
        marquee: "marquee 30s linear infinite",
      },
      keyframes: {
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        marquee: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
      },
    },
  },
  plugins: [],
};
