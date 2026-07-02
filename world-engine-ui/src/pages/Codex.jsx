import { useCallback, useEffect, useState } from 'react'
import { NavLink, useParams } from 'react-router-dom'
import { useApi } from '../api'
import LoreDrawer from '../components/LoreDrawer'
import ComposerDrawer from '../components/ComposerDrawer'

const KINDS = [
  { slug: 'characters', label: 'Characters', rune: '☉', blurb: 'The souls who walk this world.', type: 'character' },
  { slug: 'beasts', label: 'Bestiary', rune: '✺', blurb: 'The creatures that haunt its edges.', type: 'beast' },
  { slug: 'spells', label: 'Grimoire', rune: '✶', blurb: 'The workings that bend it.', type: 'spell' },
]

function letterIcon(title) {
  const l = (title || '')[0]?.toUpperCase()
  return /^[A-Z]$/.test(l || '') ? new URL(`../../assets/img/${l}_icon.png`, import.meta.url).href : null
}

export default function Codex() {
  const api = useApi()
  const { kind = 'characters' } = useParams()
  const meta = KINDS.find((k) => k.slug === kind) || KINDS[0]
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [composeFor, setComposeFor] = useState(null)

  const refresh = useCallback(() => {
    api.getCodex(kind).then(setItems).catch((e) => setError(e.message))
  }, [api, kind])

  useEffect(() => {
    let alive = true
    setItems(null)
    setError(null)
    api.getCodex(kind).then((d) => alive && setItems(d)).catch((e) => alive && setError(e.message))
    return () => { alive = false }
  }, [api, kind])

  const onDiscovered = useCallback((id) => {
    setItems((arr) => arr && arr.map((e) => (e.id === id ? { ...e, discovered: true } : e)))
  }, [])

  return (
    <>
      <div className="page-head reveal" style={{ '--i': 0 }}>
        <h1>The Codex</h1>
        <p className="page-sub">{meta.blurb} Sealed entries are rumored — open one to reveal it.</p>
      </div>

      <div className="codex-tabs reveal" style={{ '--i': 1 }}>
        {KINDS.map((k) => (
          <NavLink
            key={k.slug}
            to={`/codex/${k.slug}`}
            className={() => `codex-tab${k.slug === kind ? ' active' : ''}`}
          >
            {k.rune} {k.label}
          </NavLink>
        ))}
      </div>

      {error && <div className="state state-error">Could not open the codex: {error}</div>}
      {!items && !error && <div className="state">Turning pages…</div>}

      {items && (
        <div className="codex-grid">
          {items.map((e, i) => (
            <button
              key={e.id}
              className={`codex-card reveal${e.discovered ? '' : ' is-fog'}`}
              style={{ '--i': i + 2 }}
              onClick={() => setSelected(e.id)}
            >
              <span className="cc-rune">
                {kind === 'characters' && e.discovered && letterIcon(e.title)
                  ? <img className="cc-letter" src={letterIcon(e.title)} alt="" />
                  : meta.rune}
              </span>
              <h3 className="cc-title">{e.discovered ? e.title : 'Sealed entry'}</h3>
              <p className="cc-body">{e.body}</p>
              {e.discovered && <p className="cc-by">scribed by {e.contributor_id}</p>}
              {!e.discovered && (
                <span className="cc-lock"><span className="lk">⚜</span>open to reveal</span>
              )}
            </button>
          ))}
          {items.length === 0 && (
            <p className="muted">Nothing recorded here yet. Be the first to add to the {meta.label.toLowerCase()}.</p>
          )}
        </div>
      )}

      {selected && (
        <LoreDrawer
          id={selected}
          onClose={() => setSelected(null)}
          onNavigate={(id) => setSelected(id)}
          onDiscovered={onDiscovered}
          onCompose={(id) => { setSelected(null); setComposeFor(id) }}
        />
      )}

      {composeFor && (
        <ComposerDrawer
          referenceId={composeFor}
          initialType={meta.type}
          onClose={() => setComposeFor(null)}
          onSuccess={refresh}
        />
      )}
    </>
  )
}
