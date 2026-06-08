// Playwright Test config for the campaign portal smoke suite.
// Targets the live GitHub Pages URL by default; PORTAL_BASE_URL env var overrides.

const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: '.',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.PORTAL_BASE_URL || 'https://marc667us.github.io/campaign-portal/',
    headless: true,
    viewport: { width: 1400, height: 900 },
    screenshot: 'on',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
