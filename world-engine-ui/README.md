# World Engine — Front-end

React + Vite front-end for the collaborative storytelling world: Google sign-in,
storyline browsing, the comic/reel showcase, voting, and lore submission.

It runs **out of the box in demo mode** (mock data + a demo sign-in), and becomes the
real app once you point it at your backend and Firebase project via `.env`.

## Run it

```bash
npm install
npm run dev        # http://localhost:5173  — works immediately in demo mode
```

`npm run build` produces a static bundle in `dist/`.

## Switch on real auth + data

Copy `.env.example` to `.env` and fill in:

```
VITE_API_BASE_URL=https://your-backend.run.app      # your FastAPI service
VITE_FIREBASE_API_KEY=...
VITE_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your-project
VITE_FIREBASE_APP_ID=...
```

- Leave **API base** blank → built-in mock data (no backend needed).
- Leave **Firebase keys** blank → a demo sign-in button instead of Google.
- Set both → real Google sign-in and live data.

### Firebase setup (5 min)
1. Firebase console → create/select a project → **Authentication → Sign-in method → enable Google**.
2. **Project settings → Your apps → Web app** → copy the config values into `.env`.
3. **Authentication → Settings → Authorized domains** → add `localhost` and your deployed domain.

## How auth reaches your backend

On sign-in the app holds a Firebase **ID token**. Every API call sends it as
`Authorization: Bearer <token>`. Your FastAPI backend verifies it with the Firebase
Admin SDK and uses the `uid` as `author_id` — the same id threaded through contributions,
votes, and the ledger. **The browser never talks to the agents directly**: it only calls
your API, which runs auth, rate limits, and the deterministic controller server-side.

## Backend API contract

The client (`src/api.js`) expects these endpoints. Match them in FastAPI (shapes mirror
`CONTEXT.md`):

| Method & path | Returns |
|---|---|
| `GET /canon/storylines` | `StorylineTree[]` summaries: `{ tree_id, title, summary, type, member_count, vote_total, composite_score, version, voted, derived_from }` |
| `GET /canon/storylines/:treeId` | One tree, plus `nodes: CanonEntry[]` where each is `{ id, type, title, contributor, version, derived_from[], body }` |
| `POST /vote` `{ tree_id }` | `{ ok, tree_id, vote_total, voted }` (enforce one vote per user per tree) |
| `GET /showcase` | `MediaAsset[]`: `{ id, tree_id, kind: "comic"\|"reel", title, caption, hashtags[], contributor_ids[], gcs_url, panels?[], scenes?[] }` |
| `POST /contribute` `{ title, type, body }` | `{ status, verdict, score, message }` |

For comics, the client renders `gcs_url` as an image (falls back to `panels[]` text in
demo). For reels it renders `gcs_url` as a video (falls back to `scenes[]`).

## Deploy

Frontend → **Firebase Hosting**:

```bash
npm run build
npx firebase-tools deploy --only hosting
```

Backend (FastAPI) → **Cloud Run**, with the Firebase Admin SDK verifying ID tokens. Set
`VITE_API_BASE_URL` to the Cloud Run URL and rebuild.

## Structure

```
src/
  auth.jsx        Google sign-in + demo fallback + token accessor
  firebase.js     Firebase init (auto-disabled with no keys)
  api.js          API client (Bearer token) + mock fallback
  mock.js         demo data
  components/     Layout, ProtectedRoute, Thread (lineage), VoteButton
  pages/          Login, Storylines, StorylineDetail, Showcase, Submit
```
