import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../api'
import VoteButton from '../components/VoteButton'

// Folio numbering for the table of contents.
const ROMAN = [[100, 'C'], [90, 'XC'], [50, 'L'], [40, 'XL'], [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I']]
function roman(n) {
  let s = ''
  for (const [v, r] of ROMAN) while (n >= v) { s += r; n -= v }
  return s
}

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
      <header className="page-head reveal" style={{ '--i': 0 }}>
        <div className="page-kicker">❦ the chronicle, in order of renown</div>
        <h1>Storylines</h1>
        <p className="page-sub">Branches of the world, ranked by how much they’re loved and built upon.</p>
      </header>

      {/* An illuminated table of contents: each storyline is a folio entry whose
          dotted leader runs out to its backing tally, the way a contents page
          leads to a page number. */}
      <ol className="toc">
        {items.map((s, i) => (
          <li key={s.tree_id} className="toc-entry reveal" style={{ '--i': i + 1 }}>
            <span className="toc-num" aria-hidden="true">{roman(i + 1)}</span>
            <div className="toc-body">
              <div className="toc-line">
                <Link to={`/story/${s.tree_id}`} className="toc-title">{s.title}</Link>
                <span className={`toc-type tag-${s.type}`}>{s.type}</span>
                <span className="toc-leader" aria-hidden="true" />
                <VoteButton treeId={s.tree_id} initialTotal={s.vote_total} initialVoted={s.voted} />
              </div>
              <p className="toc-summary">{s.summary}</p>
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
          </li>
        ))}
      </ol>
    </div>
  )
}
