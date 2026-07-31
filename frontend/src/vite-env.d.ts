/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_STUDIO_NAME?: string;
  readonly VITE_ADSENSE_CLIENT?: string;
  readonly VITE_ADSENSE_SLOT_ANSWER?: string;
  readonly VITE_VAPID_PUBLIC_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
