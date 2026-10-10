/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Build-time default backend URL (see DEFAULT_BACKEND_URL in
  // src/shared/api-client.ts). Set when building a store/hosted package:
  //   VITE_BACKEND_URL=https://api.example.com npm run build
  readonly VITE_BACKEND_URL?: string;
  // Build-time shared LOCAL_API_KEY (see DEFAULT_LOCAL_API_KEY in
  // src/shared/api-client.ts) — baked in so a real distributed user never
  // sees or edits it; Settings no longer exposes an API Key field at all.
  // Set alongside VITE_BACKEND_URL when building for distribution:
  //   VITE_BACKEND_URL=... VITE_LOCAL_API_KEY=... npm run build
  readonly VITE_LOCAL_API_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
