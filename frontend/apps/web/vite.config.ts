import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiProxyTarget = process.env.AGENTLENS_API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    exclude: ["monaco-editor"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      "@agentlens/code-renderer": path.resolve(
        __dirname,
        "../../packages/viewers/code-renderer/src",
      ),
      "@agentlens/json-renderer": path.resolve(
        __dirname,
        "../../packages/viewers/json-renderer/src",
      ),
      "@agentlens/markdown-renderer": path.resolve(
        __dirname,
        "../../packages/viewers/markdown-renderer/src",
      ),
      "@agentlens/trajectory-viewer": path.resolve(
        __dirname,
        "../../packages/viewers/trajectory-viewer/src",
      ),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
});
