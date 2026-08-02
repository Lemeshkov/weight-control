/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_LAB_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
