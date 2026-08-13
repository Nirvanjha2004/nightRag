/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * API origin for the built UI when the frontend is hosted separately from
   * the NightRag backend (e.g. UI on Vercel/Netlify, API on Render).
   * Full origin, no trailing slash: https://nightrag-api.onrender.com
   * Leave unset when the FastAPI server serves the UI itself (same origin).
   */
  readonly VITE_NIGHTRAG_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
