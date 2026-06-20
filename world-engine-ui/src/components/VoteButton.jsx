import { useState } from 'react'
import { useApi } from '../api'

export default function VoteButton({ treeId, initialTotal, initialVoted }) {
  const api = useApi()
  const [total, setTotal] = useState(initialTotal ?? 0)
  const [voted, setVoted] = useState(Boolean(initialVoted))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  async function back() {
    if (voted || busy) return
    setBusy(true)
    setErr(null)
    const prevTotal = total
    setTotal((t) => t + 1) // optimistic
    setVoted(true)
    try {
      const r = await api.vote(treeId)
      if (typeof r?.vote_total === 'number') setTotal(r.vote_total)
      setVoted(r?.voted ?? true)
    } catch (e) {
      setTotal(prevTotal)
      setVoted(false)
      setErr('That vote didn’t register. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="vote">
      <button
        className={`vote-btn ${voted ? 'is-voted' : ''}`}
        onClick={back}
        disabled={voted || busy}
        aria-pressed={voted}
      >
        <span className="vote-count">{total}</span>
        <span className="vote-label">{voted ? 'Backed' : busy ? 'Backing…' : 'Back this story'}</span>
      </button>
      {err && <p className="vote-err" role="alert">{err}</p>}
    </div>
  )
}
