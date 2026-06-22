# World Engine UI — Style & UX Review

Scope: `world-engine-ui/` (React 18 + Vite frontend). This is a review only — no
source files were changed. Suggested diffs are included for the quick wins.

## Overall

This is a genuinely well-crafted frontend — above typical capstone quality. It has
a real point of view rather than a generic component-library look, the code is
consistent and idiomatic, and the data layer degrades gracefully to mock mode. The
issues below are mostly polish and a few small correctness/UX gaps.

---

## Visual / stylistic — strong

- **A deliberate, content-appropriate aesthetic.** The palette comment says it out
  loud (`index.css:1` — "cool bone + oxblood — deliberately not the cream/terracotta
  default"). The type system is the standout: serif (Hoefler/Iowan) for titles,
  **monospace for all metadata** — the version/score/contributor "ledger" lines — and
  sans for body. For a project about *canon, provenance, and a points ledger*,
  rendering metadata as a mono ledger is a smart, coherent metaphor, not just
  decoration.
- **The `Thread` SVG component** (`components/Thread.jsx`) is a nice signature
  element — a hairline lineage line with a node and optional branch stub that
  visually encodes the provenance/derived-from concept the whole project is about.
- **Disciplined design tokens.** Everything routes through CSS custom properties
  (color, type stacks, radius, max-width). `color-mix()` for tag borders is a
  tasteful modern touch.
- **Accessibility basics are present and not an afterthought:** `:focus-visible`
  outline, `prefers-reduced-motion` reset, `aria-pressed`/`role="alert"` on the vote
  button, `aria-hidden` on decorative glyphs/threads, a real mobile breakpoint at
  760px. That's more than most demos do.

## Code style — clean and consistent

- Small functional components, hooks-only, one concern per file. The data-fetch
  pattern (`let live = true` cleanup guard to avoid setState-after-unmount) is applied
  identically across `Storylines`, `StorylineDetail`, and `Showcase`.
- `VoteButton` does **optimistic update with rollback on failure**
  (`components/VoteButton.jsx:14–28`) — the right pattern, correctly implemented.
- The `useApi`/`apiMock` split is elegant: every method has a mock branch, so the
  whole app runs with zero backend and the mock votes even persist for the session
  via `structuredClone`.

---

## Issues & gaps (roughly priority order)

### 1. Submit gives no feedback on empty input

`Submit.jsx:16` early-returns when `title`/`body` are empty, but the button is only
disabled on `busy` — so clicking "Submit to canon" with an empty title does
*nothing*, silently. The user can't tell whether it's broken.

**Suggested change** — disable the button until both fields have content. Define a
validity flag and use it on the button:

```jsx
// Submit.jsx
const canSubmit = title.trim() && body.trim() && !busy

// ...
<button className="btn-primary" type="submit" disabled={!canSubmit}>
  {busy ? 'Sending through the pipeline…' : 'Submit to canon'}
</button>
```

This keeps the existing early-return as a safety net but makes the disabled state
communicate *why* nothing happens. (Optional further polish: add `aria-invalid` +
an inline hint on the title field once the user has touched it.)

### 2. "Continue with Google" is misleading in demo mode

In `Login.jsx:49` the Google button is always shown, and when Firebase isn't
configured, `signInWithGoogle` silently logs in as `DEMO_USER` (`auth.jsx:31–33`)
with no Google popup. A demo-mode user clicking the official-looking Google button
gets signed in as "Demo Author" — the two buttons look different but behave
identically.

**Suggested change** — when `!firebaseEnabled`, make the demo path the primary
action and either hide or clearly mark the Google button:

```jsx
// Login.jsx — render the real Google button only when auth is actually wired up
{firebaseEnabled ? (
  <button className="btn-google" onClick={signInWithGoogle}>
    <GoogleGlyph />
    Continue with Google
  </button>
) : (
  <>
    <button className="btn-primary" onClick={continueDemo}>Explore in demo mode</button>
    <p className="panel-note">
      Add your Firebase keys to <code>.env</code> to switch on real Google sign-in.
    </p>
  </>
)}
```

This removes the ambiguity (no fake Google flow) without changing behavior for the
configured case.

### 3. Two contribution types render unstyled tags

`Submit` offers `character, location, faction, plot, lore` (`Submit.jsx:4`), but
`index.css` only defines colored tag variants for `tag-character`, `tag-plot`,
`tag-faction` (`index.css:139–141`). **`location` and `lore` fall through to the
gray default** while their siblings are colored — it reads like a bug. The backend
enum also has an `other` type worth covering.

**Suggested change** — add the missing variants next to the existing ones:

```css
/* index.css — alongside .tag-character / .tag-plot / .tag-faction */
.tag-location { color: var(--good); border-color: color-mix(in srgb, var(--good) 30%, transparent); }
.tag-lore    { color: var(--ochre); border-color: color-mix(in srgb, var(--ochre) 35%, transparent); }
.tag-other   { color: var(--ink-soft); border-color: var(--line); }
```

(Pick hues that stay distinct from `character`/`plot`/`faction`; the above reuses
the existing token palette so it stays on-brand. Faction and location both using
`--good` would collide — give `location` its own value if you have one to spare.)

### 4. Backend data-escaping bug will surface here

This connects to a critical finding in the backend review (`CLAUDE_review.md`): the
backend's `after_model` callback HTML-escapes string values *before persisting*.
React already escapes on render, so any canon title/body/verdict message containing
an apostrophe or `&` will display as literal `&#x27;` / `&amp;` in `story-summary`,
`node-text`, and the Submit `verdict-msg`. **The UI is correct** — the fix belongs in
the backend (escape at render time, not at write time). Flagged here because it's a
visible, user-facing symptom even though the cause is server-side. No UI change
recommended beyond being aware of it during testing.

### 5. Inconsistent empty / error states

`Storylines` empty state has a CTA button ("Add the first piece of lore",
`Storylines.jsx:29`), but `Showcase`'s empty state (`Showcase.jsx:87`) and all error
states are dead-ends — plain text, no retry/refresh action. Consider a shared
`<EmptyState>` / `<ErrorState>` component with an optional action, so the three pages
behave consistently (and a "Try again" button on errors avoids a full reload).

### 6. List doesn't re-rank after a vote

The Storylines header promises branches "ranked by how much they're loved," but an
optimistic vote updates a single card's count without re-sorting the list. Acceptable
for a demo; noting the expectation gap. If desired, lift vote state to the list and
re-sort on change, or refetch after a successful vote.

### 7. Smaller a11y / polish items

- The reel `<video>` has no `<track>`/captions (`Showcase.jsx:30`) — fine for mock
  data, note for real media.
- Mono metadata at 12px is on the small side; the ochre badge/tags on transparent
  are the lowest-contrast elements — worth a quick WCAG AA contrast check.
- `Storylines.jsx:59` shows a raw tree id in user copy ("⌥ branched from canon_…").
  Showing an internal id to readers is a touch leaky; prefer the parent's title
  (would require the list payload to include it, or a lookup).

### 8. Naming nit

The vote handler is named `back()` (`VoteButton.jsx:11`) — semantically "back this
story," but it reads like navigation "go back." `castVote` / `handleBack` would be
clearer. Cosmetic only.

---

## Bottom line

The frontend is the most polished part of the project: a distinctive editorial
aesthetic that reinforces the product concept (canon + ledger + lineage), consistent
idiomatic React, and graceful mock-mode degradation. The highest-value fixes are the
silent empty-submit (#1), the two missing tag colors (#3), and the misleading demo
Google button (#2) — all small, localized changes. Addressing the backend escaping
(#4) so it doesn't show through would take this to genuinely portfolio-grade UI.
