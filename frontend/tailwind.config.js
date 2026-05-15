/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    extend: {
      colors: {
        ink: "#0A0A0A",
        muted: "#94A3B8",
        secondary: "#475569",
        surface: "#F8F9FA",
        line: "#E2E8F0",
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
      animation: {
        "fade-up": "fadeUp 0.5s ease-out forwards",
        marquee: "marquee 30s linear infinite",
      },
      keyframes: {
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
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
