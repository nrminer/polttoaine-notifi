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
        signalUp: "#EF4444",
        signalUpBg: "#FEE2E2",
        signalDown: "#10B981",
        signalDownBg: "#D1FAE5",
        brand: "#002FA7",
        brandHover: "#002380",
        accent: "#FDE047",
        nordDark: "#0F172A",
      },
      fontFamily: {
        display: ['"Cabinet Grotesk"', '"Recoleta"', "ui-sans-serif", "system-ui"],
        body: ['"IBM Plex Sans"', "ui-sans-serif", "system-ui"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      letterSpacing: {
        tightest: "-0.04em",
      },
      boxShadow: {
        "card": "var(--shadow-card)",
        "card-hover": "var(--shadow-card-hover)",
        "glow-brand": "0 0 20px -4px rgb(0 47 167 / 0.35)",
        "glow-accent": "0 0 20px -4px rgb(253 224 71 / 0.40)",
        "inner-brand": "inset 0 0 0 1px rgb(0 47 167 / 0.20)",
      },
      animation: {
        "fade-up": "fadeUp 0.5s ease-out forwards",
        "fade-in": "fadeIn 0.3s ease-out forwards",
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
