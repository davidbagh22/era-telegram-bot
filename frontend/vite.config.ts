import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // app/webapp.py serves the built frontend at /app (StaticFiles mounted
  // there, not at the domain root — see _mount_frontend). Without this,
  // Vite emits index.html with absolute root-relative asset paths
  // (/assets/...), which 404 in production because nothing is mounted at
  // the actual domain root: the Mini App loads an empty shell and never
  // renders — a real bug this exact misconfiguration caused, only caught
  // by PR16's E2E suite requesting the built app's own asset URLs.
  base: "/app/",
  server: {
    host: true,
  },
});
