import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    lib: {
      entry: "src/embed.tsx",
      name: "HotelaChat",
      fileName: "hotela-chat",
      formats: ["es", "iife"],
    },
    rollupOptions: {
      external: [],
      output: {
        assetFileNames: "hotela-chat.[ext]",
      },
    },
  },
});
