import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  return {
    plugins: [react()],
    server: {
      port: Number(env.VITE_DEV_PORT ?? 5173),
      host: true
    },
    preview: {
      port: Number(env.VITE_PREVIEW_PORT ?? 4173),
      host: true
    }
  };
});
