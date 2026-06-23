import { useMemo } from 'react'
import { useAuth } from './auth'
import {
  mockStorylines,
  mockShowcase,
  DEMO,
  mockWorld,
  mockMap,
  mockCodex,
  mockCanon,
  buildCanonFallback,
} from './mock'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
export const apiMock = !API_BASE

// In-memory copy so demo votes + discoveries persist for the session.
const mockState = {
  storylines: structuredClone(mockStorylines),
  showcase: structuredClone(mockShowcase),
  // Fog state: seed with everything already flagged discovered in the mock.
  discovered: new Set([
    ...mockMap.locations.filter((l) => l.discovered).map((l) => l.id),
    ...['characters', 'beasts', 'spells'].flatMap((k) =>
      mockCodex[k].filter((e) => e.discovered).map((e) => e.id),
    ),
  ]),
}

const withFog = (item) => ({ ...item, discovered: mockState.discovered.has(item.id) })

// Mock implementations of the Living-World surface. The real endpoints are being
// built; until they exist these double as the fallback so Map/Codex stay usable.
const mockGetMap = () => ({
  world: mockWorld,
  regions: mockMap.regions,
  locations: mockMap.locations.map(withFog),
})
const mockGetCodex = (kind) => (mockCodex[kind] || []).map(withFog)
const mockGetCanon = (id) => {
  mockState.discovered.add(id)
  const rec = mockCanon[id] || buildCanonFallback(id)
  return rec ? { ...rec, discovered: true } : null
}
const mockDiscover = (canonId) => {
  mockState.discovered.add(canonId)
  return { discovered: true, canon_id: canonId }
}

// Try the real endpoint; if it isn't there yet (or the network fails), fall back to
// demo data so the new views work before the backend ships them.
async function realOrDemo(label, run, fallback) {
  try {
    return await run()
  } catch (e) {
    console.warn(`[world-engine] ${label} unavailable — using demo data.`, e.message)
    return fallback()
  }
}

async function request(path, { method = 'GET', body, token } = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.status === 204 ? null : res.json()
}

const summary = ({ nodes, ...rest }) => rest

export function useApi() {
  const { getToken } = useAuth()

  return useMemo(
    () => ({
      // GET /canon/storylines -> StorylineTree[] (summary, no nodes)
      async listStorylines() {
        if (apiMock) return mockState.storylines.map(summary)
        return request('/canon/storylines', { token: await getToken() })
      },

      // GET /canon/storylines/:treeId -> StorylineTree (with nodes + lineage)
      async getStoryline(treeId) {
        if (apiMock) return mockState.storylines.find((s) => s.tree_id === treeId) || null
        return request(`/canon/storylines/${treeId}`, { token: await getToken() })
      },

      // GET /scenes/:id -> Scene
      async getScene(id) {
        if (apiMock) return DEMO[id] || DEMO.eldoria
        return request(`/scenes/${id}`, { token: await getToken() })
      },

      // POST /vote { tree_id } -> { ok, vote_total, voted }
      async vote(treeId) {
        if (apiMock) {
          const s = mockState.storylines.find((x) => x.tree_id === treeId)
          if (s && !s.voted) {
            s.voted = true
            s.vote_total += 1
          }
          return { ok: true, tree_id: treeId, vote_total: s?.vote_total, voted: true }
        }
        return request('/vote', { method: 'POST', body: { tree_id: treeId }, token: await getToken() })
      },

      // GET /world/map -> { world, regions, locations[] }
      async getMap() {
        if (apiMock) return mockGetMap()
        return realOrDemo('/world/map', async () =>
          request('/world/map', { token: await getToken() }), mockGetMap)
      },

      // GET /world (active world summary) — falls back to the demo world's map payload
      async getWorld() {
        if (apiMock) return mockWorld
        return realOrDemo('/world', async () =>
          request('/world', { token: await getToken() }), () => mockWorld)
      },

      // GET /codex/:kind -> CanonEntry[] (kind = characters|beasts|spells)
      async getCodex(kind) {
        if (apiMock) return mockGetCodex(kind)
        return realOrDemo(`/codex/${kind}`, async () =>
          request(`/codex/${kind}`, { token: await getToken() }), () => mockGetCodex(kind))
      },

      // GET /canon/:id -> entity detail (opening it also discovers it)
      async getCanon(id) {
        if (apiMock) return mockGetCanon(id)
        return realOrDemo(`/canon/${id}`, async () =>
          request(`/canon/${id}`, { token: await getToken() }), () => mockGetCanon(id))
      },

      // POST /discover { canon_id } -> clears fog for the caller (idempotent)
      async discover(canonId) {
        if (apiMock) return mockDiscover(canonId)
        return realOrDemo('/discover', async () =>
          request('/discover', { method: 'POST', body: { canon_id: canonId }, token: await getToken() }),
          () => mockDiscover(canonId))
      },

      // GET /showcase -> MediaAsset[]
      async listShowcase() {
        if (apiMock) return mockState.showcase
        return request('/showcase', { token: await getToken() })
      },

      // POST /contribute { title, type, body } -> { status, verdict, score, message }
      async submitContribution(payload) {
        if (apiMock) {
          return {
            status: 'accepted',
            verdict: 'ALLOW',
            score: 82,
            message: '(demo) Cleared moderation and merged into canon.',
          }
        }
        return request('/contribute', { method: 'POST', body: payload, token: await getToken() })
      },
    }),
    [getToken],
  )
}
