import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end configuration.
 *
 * This harness exists because two real defects shipped past a green unit suite:
 * a report panel that clipped its own content, and the active scanner never
 * reaching the report requests. Neither is visible to a test that imports a
 * module — the first is a layout consequence of a real viewport, the second
 * only appears once a request crosses the wire. Both were found by hand, and
 * without something like this they would have to be found by hand again.
 *
 * Deliberately small. The unit suite covers the pure logic; these specs cover
 * only what needs a browser and a backend.
 *
 * Both servers are started here rather than assumed. A suite that silently
 * passes because someone forgot to run the API is worse than no suite: the
 * frontend renders its "can't reach the API" notice, which is a legitimate UI
 * state, and assertions written loosely enough would accept it.
 */

const API_PORT = 8000
const WEB_PORT = 5173
const REPO = new URL('..', import.meta.url).pathname

export default defineConfig({
  testDir: './e2e',
  // The drawn-area flow costs a few seconds of map and series work; the
  // default 30s is tight on a cold first run.
  timeout: 90_000,
  expect: { timeout: 15_000 },
  // Serial locally, and never retried into a false pass — a flaky assertion
  // here is a finding, not something to paper over with a second attempt.
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],

  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // The sandbox provides the browser; never download one.
    launchOptions: { executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' },
  },

  /*
   * Two viewports, because one of the two defects this suite exists to catch
   * was only visible at a real height. 1440x900 is a laptop, not a large
   * desktop, deliberately: it is the size at which the report panel ran out of
   * room, and a suite that only tests 1920x1080 would have shipped the bug.
   */
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { ...devices['Pixel 7'], viewport: { width: 390, height: 844 } } },
  ],

  webServer: [
    {
      command: `.venv/bin/uvicorn mock_ee_backend:app --port ${API_PORT}`,
      cwd: REPO,
      url: `http://localhost:${API_PORT}/api/catalog?scanner=land`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      stdout: 'ignore',
      stderr: 'pipe',
    },
    {
      command: `npm run dev -- --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}/`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: 'ignore',
      stderr: 'pipe',
    },
  ],
})
