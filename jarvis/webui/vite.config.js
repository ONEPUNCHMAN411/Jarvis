import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base "./" makes built asset paths relative so the bundle loads from a
// local file:// URL inside QWebEngineView.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "dist",
    assetsDir: "assets",
    emptyOutDir: true,
  },
});
