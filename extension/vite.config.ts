import { resolve } from "node:path";

import { crx } from "@crxjs/vite-plugin";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

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

// Font packages (KaTeX, JetBrains Mono) list each font as woff2 plus woff/ttf
// fallbacks. Chrome always uses woff2, so the fallbacks are cut from the built
// stylesheets and their files (about 1 MB) left out of the extension.
function woff2Only(): Plugin {
  const unused = /,\s*url\(([^)]*\.(?:woff|ttf))\)\s*format\("(?:woff|truetype)"\)/g;
  return {
    name: "woff2-only",
    apply: "build",
    generateBundle(_options, bundle) {
      const dropped = new Set<string>();
      for (const file of Object.values(bundle)) {
        if (file.type !== "asset" || !file.fileName.endsWith(".css")) continue;
        file.source = String(file.source).replace(unused, (_match, url: string) => {
          dropped.add(url.split("/").pop() ?? url);
          return "";
        });
      }
      for (const name of Object.keys(bundle)) {
        if (dropped.has(name.split("/").pop() ?? name)) delete bundle[name];
      }
    },
  };
}

// @crxjs/vite-plugin reads manifest.json, rewrites its source-file
// references (background.service_worker, content_scripts[].js,
// side_panel.default_path) into the built dist/ output, and handles the
// tricky MV3 bundling details by hand (content scripts must be
// self-contained scripts, not ES modules with shared chunks — a hand-rolled
// multi-entry Rollup config gets this subtly wrong).
export default defineConfig({
  plugins: [react(), crx({ manifest }), woff2Only()],
  build: {
    // Warns when one script grows past this, so the startup bundle doesn't quietly creep back up.
    chunkSizeWarningLimit: 400,
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
