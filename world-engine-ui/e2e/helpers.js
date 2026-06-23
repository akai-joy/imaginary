// Shared helpers for the screenshot suite.

export const SHOTS_DIR = 'screenshots'

// Demo auth lives only in React state (auth.jsx) — every full page load resets it
// to null and ProtectedRoute bounces to /login. So we log in ONCE and then move
// between pages by clicking in-app nav links (SPA navigation preserves state).
export async function loginDemo(page) {
  await page.goto('/')
  // ProtectedRoute redirects to /login; with Firebase blank the only button is
  // "Explore in demo mode".
  const enter = page.getByRole('button', { name: 'Explore in demo mode' })
  await enter.click()
  await page.waitForURL('**/') // back on the Map (index) route
}

// Suppress the once-per-session WorldEntry opening-line overlay so it doesn't
// cover page captures. Call before the first navigation. (We capture the overlay
// itself in a dedicated test that skips this.)
export async function suppressWorldEntry(page) {
  await page.addInitScript(() => {
    try {
      sessionStorage.setItem('we_entry_seen', '1')
    } catch {
      /* private mode */
    }
  })
}

// Wait for a page to actually have its content (a concrete selector), fonts, and
// network settled — then screenshot full-page. No fixed sleeps.
export async function shoot(page, name, selector) {
  if (selector) {
    await page.locator(selector).first().waitFor({ state: 'visible', timeout: 20_000 })
  }
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.evaluate(() => document.fonts?.ready).catch(() => {})
  await page.screenshot({ path: `${SHOTS_DIR}/${name}.png`, fullPage: true })
}
