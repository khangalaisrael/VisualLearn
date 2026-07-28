import { resolve } from "node:path";

import { crx } from "@crxjs/vite-plugin";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

import manifest from "./manifest.json";

// @crxjs/vite-plugin reads manifest.json, rewrites its source-file
// references (background.service_worker, content_scripts[].js,
// side_panel.default_path) into the built dist/ output, and handles the
// tricky MV3 bundling details by hand (content scripts must be
// self-contained scripts, not ES modules with shared chunks — a hand-rolled
// multi-entry Rollup config gets this subtly wrong).
export default defineConfig({
  plugins: [react(), crx({ manifest })],
  resolve: {
    alias: {
      "@shared": resolve(__dirname, "../shared"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
});
