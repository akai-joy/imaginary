import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../api'
import Thread from '../components/Thread'
import VoteButton from '../components/VoteButton'

export default function Storylines() {
  const api = useApi()
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let live = true
    setItems(null)
    setError(null)
    api
      .listStorylines()
      .then((d) => live && setItems(d))
      .catch(() => live && setError('Could not load storylines.'))
    return () => {
      live = false
    }
  }, [api, reloadKey])

  if (error)
    return (
      <div className="state state-error">
        <p>{error}</p>
        <button className="btn-primary" onClick={() => setReloadKey((k) => k + 1)}>Try again</button>
      </div>
    )
  if (!items) return <p className="state muted">Loading storylines…</p>
  if (items.length === 0)
    return (
      <div className="state">
        <p>No storylines yet.</p>
        <Link className="btn-primary" to="/submit">Add the first piece of lore</Link>
      </div>
    )

  return (
    <div className="page">
      <header className="page-head">
        <h1>Storylines</h1>
        <p className="page-sub">Branches of the world, ranked by how much they’re loved and built upon.</p>
      </header>

      <ul className="story-list">
        {items.map((s) => (
          <li key={s.tree_id} className="story-card">
            <Thread branched={Boolean(s.derived_from)} tall />
            <div className="story-body">
              <div className="story-top">
                <Link to={`/story/${s.tree_id}`} className="story-title">{s.title}</Link>
                <span className={`tag tag-${s.type}`}>{s.type}</span>
              </div>
              <p className="story-summary">{s.summary}</p>
              <p className="meta">
                <span>v{s.version}</span>
                <span className="dot">·</span>
                <span>{s.member_count} nodes</span>
                <span className="dot">·</span>
                <span>score {s.composite_score}</span>
                {s.derived_from && (
                  <>
                    <span className="dot">·</span>
                    <span className="derived">⌥ branched from {s.derived_from}</span>
                  </>
                )}
              </p>
            </div>
            <VoteButton treeId={s.tree_id} initialTotal={s.vote_total} initialVoted={s.voted} />
          </li>
        ))}
      </ul>
    </div>
  )
}
