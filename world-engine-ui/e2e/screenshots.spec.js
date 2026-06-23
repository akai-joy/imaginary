import { test } from '@playwright/test'
import { loginDemo, suppressWorldEntry, shoot } from './helpers.js'

// Captures the main views of the app to ./screenshots. Read-only: works against a
// live seeded backend or the demo-data fallback, so it never produces blank pages.

test('world-entry opening-line overlay', async ({ page }) => {
  // Deliberately do NOT suppress the overlay here — this is the money shot.
  await loginDemo(page)
  await shoot(page, '00-world-entry', '.world-entry')
})

test('main views', async ({ page }) => {
  await suppressWorldEntry(page)
  await loginDemo(page)

  // Map (home / Living Atlas)
  await shoot(page, '01-map', '.atlas-stage')

  // Codex — Characters / Bestiary / Grimoire tabs
  await page.getByRole('link', { name: 'Codex' }).click()
  await shoot(page, '02-codex-characters', '.codex-tabs')
  await page.locator('.codex-tabs a[href="/codex/beasts"]').click()
  await shoot(page, '03-codex-beasts', '.codex-tabs')
  await page.locator('.codex-tabs a[href="/codex/spells"]').click()
  await shoot(page, '04-codex-spells', '.codex-tabs')

  // Storylines index
  await page.getByRole('link', { name: 'Storylines' }).click()
  await shoot(page, '05-storylines', '.story-card')

  // Storyline detail (click into the first tree — opens the immersive ScenePlayer)
  await page.locator('.story-title').first().click()
  await shoot(page, '06-storyline-detail', '.immersive-header')

  // Showcase (comics / reels)
  await page.goBack()
  await page.getByRole('link', { name: 'Showcase' }).click()
  await shoot(page, '07-showcase', '.show-grid, .show-card')
})
