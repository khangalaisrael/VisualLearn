/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Build-time default backend URL (see DEFAULT_BACKEND_URL in
  // src/shared/api-client.ts). Set when building a store/hosted package:
  //   VITE_BACKEND_URL=https://api.example.com npm run build
  readonly VITE_BACKEND_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
