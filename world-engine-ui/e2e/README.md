# Screenshots / e2e (Playwright)

Automated screenshots of the app for the README, writeup, and video stills.

## One-time setup

```bash
npm install
npm run pw:install   # downloads the Chromium browser (~90MB)
```

## Capture

```bash
npm run screenshots        # main views -> ./screenshots/*.png
npm run screenshots:all    # also runs the moderation-block capture (needs backend)
```

Output lands in `./screenshots/` (gitignored). Captures:

| File | View |
|------|------|
| `00-world-entry` | Opening-line threshold overlay |
| `01-map` | The Living Atlas (fog-of-war map) |
| `02–04-codex-*` | Codex: Characters / Bestiary / Grimoire |
| `05-storylines` | Storylines index |
| `06-storyline-detail` | Immersive ScenePlayer |
| `07-showcase` | Comics / reels grid |
| `08-moderation-block` | 🛡 "Blocked by the Guardian" verdict *(opt-in)* |

## How it picks data

The config uses `reuseExistingServer: true`. For the **real seeded world**, start
your backend + dev server first, then run the capture:

```bash
# terminal 1
cd ../world-engine && uv run uvicorn app.fast_api_app:app --port 8000
# terminal 2 (this dir)
npm run dev
# terminal 3
npm run screenshots
```

If nothing is on `:5173`, Playwright boots `npm run dev` itself; with the backend
down the app falls back to demo data, so screenshots are never blank.

## Notes

- Demo auth is in-memory only, so the suite logs in once ("Explore in demo mode")
  and moves between pages via in-app nav (SPA navigation preserves state).
- `08-moderation-block` submits a prompt-injection string and needs the real
  backend running — it auto-skips in demo-data mode (the mock doesn't moderate).
