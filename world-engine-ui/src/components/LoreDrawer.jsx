import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../api'

const RUNE = { location: '⛰', character: '☉', beast: '✺', spell: '✶', faction: '⚑', plot: '❧', lore: '✜' }

// Slide-over detail for any canon entity. Opening it discovers the node (clears fog).
// `onCompose(id)` is optional: when provided, "Add connected lore" opens the inline
// composer in place; otherwise it deep-links to the full-page /submit form.
export default function LoreDrawer({ id, tileUrl, onClose, onNavigate, onDiscovered, onCompose }) {
  const api = useApi()
  const [rec, setRec] = useState(null)
  const [loading, setLoading] = useState(true)
  const [world, setWorld] = useState(null)

  useEffect(() => {
    let alive = true
    api.getWorld().then((w) => alive && setWorld(w)).catch(() => {})
    return () => { alive = false }
  }, [api])

  const isClosed = world?.window_open === false || world?.status === 'archived'

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
            {tileUrl && (
              <img className="drawer-tile" src={tileUrl} alt=""
                onError={(e) => { e.currentTarget.style.display = 'none' }} />
            )}
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

            {!isClosed && (onCompose ? (
              <button type="button" className="drawer-add" onClick={() => onCompose(rec.id)}>
                ✦ Add connected lore
              </button>
            ) : (
              <Link className="drawer-add" to={`/submit?references=${rec.id}`}>
                ✦ Add connected lore
              </Link>
            ))}
          </>
        )}
      </aside>
    </>
  )
}
