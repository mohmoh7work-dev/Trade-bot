/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "apple-touch-icon.png"],
      manifest: {
        name: "mohz bot",
        short_name: "mohz bot",
        description: "Start and stop the XAUUSD council bot on your MT5 accounts.",
        theme_color: "#d62839",
        background_color: "#fde8e8",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "icon-512-maskable.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // The app shell works offline; live data (/api) always goes to the network.
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//],
        globPatterns: ["**/*.{js,css,html,svg,png}"],
      },
    }),
  ],
  server: {
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test-setup.ts"],
    globals: false,
  },
});
