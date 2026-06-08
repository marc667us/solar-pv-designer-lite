// End-to-end smoke test for the campaign portal.
// Drives sign-in, product picker, dashboard KPIs/charts, and every visible tab.
// Replaces the previous console.log-only workflow (Phase 5.1/5.2/5.3 of the
// 2026-06-06 quality-gate work-schedule). Credentials come from env vars
// (CAMPAIGN_TEST_EMAIL / CAMPAIGN_TEST_PASSWORD), not plaintext.

const { test, expect } = require('@playwright/test');

const EMAIL = process.env.CAMPAIGN_TEST_EMAIL;
const PASSWORD = process.env.CAMPAIGN_TEST_PASSWORD;

test.beforeAll(() => {
  if (!EMAIL || !PASSWORD) {
    throw new Error(
      'CAMPAIGN_TEST_EMAIL and CAMPAIGN_TEST_PASSWORD must be set ' +
      '(GitHub Actions secrets). Refusing to run with default credentials.'
    );
  }
});

test.describe('campaign portal smoke', () => {
  // Collect console + page errors per-test; fail the test if any fire,
  // unless the source URL matches a documented harmless 3rd-party noise rule.
  let consoleErrors = [];
  let pageErrors = [];

  test.beforeEach(async ({ page }) => {
    consoleErrors = [];
    pageErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (err) => pageErrors.push(err.message));
  });

  test.afterEach(async () => {
    expect(pageErrors, 'no page errors').toEqual([]);
    expect(consoleErrors, 'no console errors').toEqual([]);
  });

  test('login → product picker → dashboard with KPIs + charts', async ({ page }) => {
    // 1. Portal loads
    await page.goto(`?cb=${Date.now()}`, { waitUntil: 'networkidle' });
    await expect(page.locator('#step-signin')).toBeVisible();

    // 2. Sign in
    await page.fill('#rep-email', EMAIL);
    await page.fill('#rep-password', PASSWORD);
    await page.click('#signin-btn');

    // 3. Product picker shows (deterministic — no fixed sleeps)
    await expect(page.locator('#step-product')).toBeVisible({ timeout: 15_000 });

    // 4. Pick SolarPro Ghana + Connect
    await page.click('.product-card[data-id="solarpro-ghana"]');
    await page.click('#connect-btn');

    // 5. Dashboard reveals — login overlay must be hidden
    await expect(page.locator('#login')).toHaveClass(/hidden/, { timeout: 15_000 });

    // 6. All 7 KPIs render with non-placeholder values
    const kpiSlugs = ['INVITED', 'CONTACTED', 'SIGNED UP', 'ACTIVE', 'FEEDBACK', 'NURTURED', 'PAID'];
    for (const slug of kpiSlugs) {
      const kpi = page.locator(`[id="kpi-${slug}"]`);
      await expect(kpi, `KPI "${slug}" present`).toBeVisible();
      const txt = (await kpi.textContent())?.trim() || '';
      expect(txt, `KPI "${slug}" value not n/a / empty`).not.toBe('');
      expect(txt.toLowerCase()).not.toBe('n/a');
    }

    // 7. Every <canvas> on the page has nonzero pixel dimensions
    const canvases = await page.$$eval('canvas', (els) =>
      els.map((e) => ({ id: e.id || '(unnamed)', w: e.width, h: e.height }))
    );
    expect(canvases.length, 'at least one chart canvas rendered').toBeGreaterThan(0);
    for (const c of canvases) {
      expect(c.w, `canvas ${c.id} width`).toBeGreaterThan(0);
      expect(c.h, `canvas ${c.id} height`).toBeGreaterThan(0);
    }
  });

  test('every visible tab activates its panel without errors', async ({ page }) => {
    // Reach dashboard
    await page.goto(`?cb=${Date.now()}`, { waitUntil: 'networkidle' });
    await page.fill('#rep-email', EMAIL);
    await page.fill('#rep-password', PASSWORD);
    await page.click('#signin-btn');
    await expect(page.locator('#step-product')).toBeVisible({ timeout: 15_000 });
    await page.click('.product-card[data-id="solarpro-ghana"]');
    await page.click('#connect-btn');
    await expect(page.locator('#login')).toHaveClass(/hidden/, { timeout: 15_000 });

    // Discover every tab the portal actually renders, not a hard-coded list.
    // Codex flagged that only 2 of 9 tabs were exercised previously.
    const tabIds = await page.$$eval('.tab', (els) =>
      els.map((e) => e.dataset.tab).filter(Boolean)
    );
    expect(tabIds.length, 'at least one tab visible').toBeGreaterThan(0);

    for (const id of tabIds) {
      await page.click(`.tab[data-tab="${id}"]`);
      // Most portals reveal a sibling .panel matching the data-tab id;
      // fall back to "tab class shows 'active'" if no panel id matches.
      const panel = page.locator(`[data-panel="${id}"], #panel-${id}, #${id}`).first();
      const tabEl = page.locator(`.tab[data-tab="${id}"]`);
      const panelVisible = await panel.isVisible().catch(() => false);
      const tabActive = (await tabEl.getAttribute('class') || '').includes('active');
      expect(panelVisible || tabActive, `tab "${id}" activated`).toBeTruthy();
    }
  });

  test('invalid login is rejected and reveals nothing privileged', async ({ page }) => {
    await page.goto(`?cb=${Date.now()}`, { waitUntil: 'networkidle' });
    await page.fill('#rep-email', EMAIL);
    await page.fill('#rep-password', 'definitely-not-the-password');
    await page.click('#signin-btn');

    // Give the API a moment to respond (no fixed sleep — explicit waits)
    await page.waitForLoadState('networkidle');

    // Sign-in card must still be visible, dashboard hidden, no canvases rendered
    await expect(page.locator('#step-signin')).toBeVisible();
    await expect(page.locator('#login')).not.toHaveClass(/hidden/);
    const dashboardCanvases = await page.$$('canvas');
    expect(dashboardCanvases.length, 'no chart canvases on failed login').toBe(0);
  });
});
