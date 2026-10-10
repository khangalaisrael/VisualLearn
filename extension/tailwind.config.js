/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{ts,tsx,html}"],
  // Dark mode is a class on <html>, set by src/shared/theme.ts (System / Light / Dark).
  darkMode: "selector",
  theme: {
    extend: {
      // Neutral and tint steps come from CSS variables (src/sidepanel/index.css)
      // so dark mode swaps the palette without touching the components.
      colors: {
        slate: { 50: "rgb(var(--slate-50) / <alpha-value>)", 100: "rgb(var(--slate-100) / <alpha-value>)", 200: "rgb(var(--slate-200) / <alpha-value>)", 300: "rgb(var(--slate-300) / <alpha-value>)", 400: "rgb(var(--slate-400) / <alpha-value>)", 500: "rgb(var(--slate-500) / <alpha-value>)", 600: "rgb(var(--slate-600) / <alpha-value>)", 700: "rgb(var(--slate-700) / <alpha-value>)", 800: "rgb(var(--slate-800) / <alpha-value>)", 900: "rgb(var(--slate-900) / <alpha-value>)" },
        indigo: { 50: "rgb(var(--indigo-50) / <alpha-value>)", 100: "rgb(var(--indigo-100) / <alpha-value>)", 200: "rgb(var(--indigo-200) / <alpha-value>)" },
        red: { 50: "rgb(var(--red-50) / <alpha-value>)", 100: "rgb(var(--red-100) / <alpha-value>)", 200: "rgb(var(--red-200) / <alpha-value>)" },
        amber: { 50: "rgb(var(--amber-50) / <alpha-value>)", 100: "rgb(var(--amber-100) / <alpha-value>)", 200: "rgb(var(--amber-200) / <alpha-value>)" },
        violet: { 50: "rgb(var(--violet-50) / <alpha-value>)", 100: "rgb(var(--violet-100) / <alpha-value>)", 200: "rgb(var(--violet-200) / <alpha-value>)" },
      },
      spacing: {
        // Default sidebar width per docs/VisionLearn_Premium_UI_Guide.md
        sidebar: "380px",
      },
      borderRadius: {
        sm: "8px",
        md: "12px",
        lg: "16px",
      },
      fontFamily: {
        // Typography tokens per VisionLearn_Premium_UI_Guide.md.
        // Self-hosted (@fontsource-variable/inter, @fontsource/jetbrains-mono)
        // rather than a CDN link — extension pages run under a strict CSP
        // that blocks remote font/script fetches.
        sans: ["'Inter Variable'", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        // "Shadows: subtle only" per the guide — slate-tinted, not pure
        // black, so elevation reads as a lift off the page rather than a
        // generic drop-shadow.
        subtle: "0 1px 2px 0 rgb(15 23 42 / 0.04), 0 2px 8px -2px rgb(15 23 42 / 0.08)",
      },
    },
  },
  plugins: [],
};
