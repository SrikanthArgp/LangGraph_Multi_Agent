import { defineConfig, configDefaults } from "vitest/config";
import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  plugins: [tsconfigPaths(), react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.tsx"],
    // e2e/** holds Playwright specs, which use their own test runner/globals and would
    // otherwise be picked up (and fail) under Vitest's default *.spec.ts glob.
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
