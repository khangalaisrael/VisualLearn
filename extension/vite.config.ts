import { resolve } from "node:path";

import { crx } from "@crxjs/vite-plugin";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

import baseManifest from "./manifest.json";

// `STORE_BUILD=1` builds the package uploaded to the Chrome Web Store
// (scripts/package-store.mjs). The store refuses a manifest with a "key": the
// key only pins the extension's ID for unpacked development builds, and the
// store assigns the published item its own ID.
// The store ID therefore needs its own "Chrome Extension" OAuth client for
// Google sign-in, passed in as STORE_OAUTH_CLIENT_ID (docs/CHROME_WEB_STORE.md).
const isStoreBuild = process.env.STORE_BUILD === "1";

function storeManifest({ key: _key, ...rest }: typeof baseManifest) {
  const clientId = process.env.STORE_OAUTH_CLIENT_ID;
  return clientId ? { ...rest, oauth2: { ...rest.oauth2, client_id: clientId } } : rest;
}

const manifest = isStoreBuild ? storeManifest(baseManifest) : baseManifest;

// @crxjs/vite-plugin reads manifest.json, rewrites its source-file
// references (background.service_worker, content_scripts[].js,
// side_panel.default_path) into the built dist/ output, and handles the
// tricky MV3 bundling details by hand (content scripts must be
// self-contained scripts, not ES modules with shared chunks — a hand-rolled
// multi-entry Rollup config gets this subtly wrong).
export default defineConfig({
  plugins: [react(), crx({ manifest })],
  build: {
    rollupOptions: {
      // Pages the manifest does not name have to be listed, or they are not built.
      input: {
        print: resolve(__dirname, "src/print/index.html"),
        admin: resolve(__dirname, "src/admin/index.html"),
      },
    },
  },
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
