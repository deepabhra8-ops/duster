import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

import obfuscator from "./build/obfuscate.js";

// Vite configuration for the DUSTER React frontend.
// Dev server runs on port 5173 by default; the FastAPI backend is expected
// at http://localhost:5050 (configured via VITE_API_BASE_URL in .env).
export default defineConfig({
  // The obfuscator applies to production builds only, and is a no-op in `vite
  // dev` and under vitest. See build/obfuscate.js for what it does and does not
  // buy - in short, it raises the cost of reading the bundle, and is not a
  // security boundary.
  plugins: [react(), obfuscator()],
  server: {
    port: 5173,
    open: true,
  },
  test: {
    // jsdom, not node: the tests render real components and assert on the DOM.
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.js",
    include: ["src/**/*.test.{js,jsx}"],
  },
});
