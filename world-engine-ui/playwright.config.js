import { defineConfig, devices } from '@playwright/test'

// Screenshot / e2e config for World Engine UI.
//
// By default this reuses an already-running dev server (so you can point the app
// at your real seeded backend and capture the real world). If nothing is running
// on :5173 it boots `npm run dev` for you, which falls back to demo data when the
// backend is down — so screenshots are never blank.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  timeout: 60_000,
  use: {
    baseURL: 'http://localhost:5173',
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2, // crisp 2x captures for the writeup/README
    headless: true,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
