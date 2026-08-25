import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Fail loudly instead of drifting to 5174 when the port is busy: the backend's
    // frontend_origin and .claude/launch.json both pin 5173.
    strictPort: true,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
