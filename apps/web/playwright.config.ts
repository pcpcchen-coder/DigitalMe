import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "../../tests/e2e",
  workers: 1,
  timeout: 45000,
  reporter: [
    ["list"],
    ["json", { outputFile: "../../evidence/browser-tests.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:8765",
    viewport: { width: 1440, height: 1100 },
    launchOptions: {
      args: [
        "--use-fake-device-for-media-stream",
        "--autoplay-policy=no-user-gesture-required",
      ],
    },
    permissions: ["microphone"],
  },
  webServer: {
    command:
      "cd ../.. && DIGITALME_DATA=.e2e-data .venv/bin/python -m uvicorn services.api.main:app --host 127.0.0.1 --port 8765 --no-access-log",
    url: "http://127.0.0.1:8765/health",
    reuseExistingServer: false,
  },
});
