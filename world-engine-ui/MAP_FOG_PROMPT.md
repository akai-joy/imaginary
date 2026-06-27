# Living Atlas — base fog texture prompt (zero-bake)

This replaces `world-engine-ui/public/map_background.jpg` (the faint master-map base).
It is a **base texture only** — the app composites lantern pools, painted tiles, fog
holes, markers, and routes on top at runtime. Do **not** ask the model to bake any of
those in.

## Why square, not 16:9
The atlas coordinate stage is **square** (`aspect-ratio: 1/1`) and 0–100 x/y map onto it
so pools stay round and placement stays undistorted. Generate a **square** image; a 16:9
asset would letterbox inside the stage.

## Prompt

> Generate a single **square** hand-painted fantasy **fog/atmosphere base texture** for a
> top-down fantasy atlas. **4096×4096** (minimum 2048×2048). The art fills the entire
> frame edge-to-edge — no border, no letterboxing, no margins.
>
> CONTENT: swirling, layered **charcoal and blue-gray mist** covering the whole canvas
> (hand-painted, volumetric, not flat gray). Beneath the mist where it thins, a **subtle
> dark antique-gold cartographer grid** (faint graticule) shows through in a few places.
> A gentle painterly sense of unseen land under the fog — hints of darker masses — but
> **no defined geography, coastlines, or named regions**.
>
> COMPOSITION: an **even, roamable expanse** with **no single focal subject** and **no
> bright center** — luminance fairly uniform, drifting **slightly darker toward the
> edges** (soft vignette) so that warm amber elements composited on top later will pop.
>
> MOOD: warm, mysterious, hand-painted 2D fantasy atlas; top-down with slight painterly
> depth. Not a satellite photo, not a 3D isometric game screenshot.
>
> PALETTE: black and blue-gray mist, faint antique-gold grid lines only. No bright or
> saturated colors.
>
> NEGATIVE (must NOT appear): no lantern pools, no glowing circles, no painted scenes or
> vignettes, no villages, towns, buildings, or settlement; no city wall or polygon of any
> shape (no foot/hand shapes); no dashed routes or paths; no rumor pulses or dots; no map
> pins or markers; no UI, buttons, tabs, sidebar, or legend; no text, labels, typography,
> or watermark; no compass rose; no characters or creatures.
>
> One-line constraint: full-bleed **square** 4096×4096 hand-painted charcoal/blue-gray fog
> base, even and roamable, faint gold grid, no subjects of any kind.

## After generating
1. Save as `world-engine-ui/public/map_background.jpg` (or `.webp`).
2. The frontend already references `map_image_url` → `/map_background.jpg` for the mock,
   and the real backend serves the agent-painted master map; this texture is the fallback/base.
3. Optionally set `image-rendering: auto` (already default) — at 4K it stays crisp.
