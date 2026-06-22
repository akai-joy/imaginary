import { useMemo } from 'react'
import { useAuth } from './auth'
import { mockStorylines, mockShowcase, DEMO } from './mock'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
export const apiMock = !API_BASE

// In-memory copy so demo votes persist for the session.
const mockState = {
  storylines: structuredClone(mockStorylines),
  showcase: structuredClone(mockShowcase),
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
