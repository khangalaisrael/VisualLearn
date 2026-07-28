/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{ts,tsx,html}"],
  theme: {
    extend: {
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
