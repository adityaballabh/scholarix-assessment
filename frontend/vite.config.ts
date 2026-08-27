import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
  },
  server: {
    port: 5173,
    // The backend's frontend_origin and launch config are fixed to port 5173
    strictPort: true,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
