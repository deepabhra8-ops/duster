import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

import obfuscator from "./build/obfuscate.js";

export default defineConfig({
  plugins: [react(), obfuscator()],
  server: {
    port: 5173,
    open: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.js",
    include: ["src/**/*.test.{js,jsx}"],
  },
});
