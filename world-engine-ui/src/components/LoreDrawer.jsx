import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../api'

const RUNE = { location: '⛰', character: '☉', beast: '✺', spell: '✶', faction: '⚑', plot: '❧', lore: '✜' }

// Slide-over detail for any canon entity. Opening it discovers the node (clears fog).
export default function LoreDrawer({ id, onClose, onNavigate, onDiscovered }) {
  const api = useApi()
  const [rec, setRec] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    api.getCanon(id).then((r) => {
      if (!alive) return
      setRec(r)
      setLoading(false)
      onDiscovered?.(id)
    })
    return () => { alive = false }
  }, [id, api, onDiscovered])

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer" aria-label="Lore detail">
        <button className="drawer-close" onClick={onClose} aria-label="Close">×</button>
        {loading && <p className="muted">Unrolling the page…</p>}
        {!loading && !rec && <p className="muted">Nothing charted here yet.</p>}
        {!loading && rec && (
          <>
            <div className="drawer-kicker">
              {RUNE[rec.type] || '✜'} {rec.type}
              {rec.map_meta?.region ? ` · ${rec.map_meta.region}` : ''}
            </div>
            <h2>{rec.title}</h2>
            <p className="muted" style={{ fontFamily: 'var(--mono)', fontSize: 12, margin: 0 }}>
              by {rec.contributor_id} · v{rec.version}
            </p>
            <p className="drawer-body">{rec.body}</p>

            {rec.references?.length > 0 && (
              <div className="drawer-rel">
                <h3>Builds on</h3>
                {rec.references.map((r) => (
                  <button key={r.id} className="rel-chip" onClick={() => onNavigate?.(r.id)}>
                    {r.title} <span className="rc-type">{r.type}</span>
                  </button>
                ))}
              </div>
            )}
            {rec.referenced_by?.length > 0 && (
              <div className="drawer-rel">
                <h3>Found here</h3>
                {rec.referenced_by.map((r) => (
                  <button key={r.id} className="rel-chip" onClick={() => onNavigate?.(r.id)}>
                    {r.title} <span className="rc-type">{r.type}</span>
                  </button>
                ))}
              </div>
            )}
            {rec.storylines?.length > 0 && (
              <div className="drawer-rel">
                <h3>Storylines set here</h3>
                {rec.storylines.map((t) => (
                  <Link key={t} className="rel-chip" to={`/story/${t}`}>{t}</Link>
                ))}
              </div>
            )}

            <Link className="drawer-add" to={`/submit?references=${rec.id}`}>
              ✦ Add lore here
            </Link>
          </>
        )}
      </aside>
    </>
  )
}
