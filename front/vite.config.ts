import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// Em dev, /api é repassado para o back (sem problemas de CORS).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: { "/api": env.API_PROXY_TARGET || "http://localhost:8010" },
    },
  };
});
