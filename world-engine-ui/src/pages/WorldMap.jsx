import { useCallback, useEffect, useRef, useState } from 'react'
import { useApi } from '../api'
import LoreDrawer from '../components/LoreDrawer'

// Stable 0..1 hash from a string so a given id always lands in the same spot.
function hash01(str, salt) {
  let h = 2166136261
  const s = `${str}:${salt}`
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return (h >>> 0) % 1000 / 1000
}

// Locations created before the Cartographer have no map_meta and arrive at (0,0).
function placeLocation(loc) {
  if (loc.x !== 0 || loc.y !== 0) return loc
  return { ...loc, x: 12 + hash01(loc.id, 'x') * 76, y: 16 + hash01(loc.id, 'y') * 66 }
}

function snippet(text, n = 110) {
  if (!text) return ''
  if (text.length <= n) return text
  return text.slice(0, text.lastIndexOf(' ', n)) + '…'
}

const MIN_ZOOM = 0.6
const MAX_ZOOM = 5
const clampZoom = (z) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z))

export default function WorldMap() {
  const api = useApi()
  const [map, setMap] = useState(null)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [hovered, setHovered] = useState(null)

  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [grabbing, setGrabbing] = useState(false)
  const viewportRef = useRef(null)
  const drag = useRef(null)
  const moved = useRef(false)

  const load = useCallback(() => {
    api.getMap().then(setMap).catch((e) => setError(e.message))
  }, [api])
  useEffect(() => { load() }, [load])

  useEffect(() => {
    const el = viewportRef.current
    if (!el) return
    const onWheel = (e) => {
      e.preventDefault()
      setZoom((z) => clampZoom(z * (e.deltaY < 0 ? 1.12 : 0.89)))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [map])

  const onDiscovered = useCallback((id) => {
    setMap((m) => m && {
      ...m,
      locations: m.locations.map((l) => (l.id === id ? { ...l, discovered: true } : l)),
    })
  }, [])

  function onPointerDown(e) {
    drag.current = { sx: e.clientX, sy: e.clientY, px: pan.x, py: pan.y }
    moved.current = false
    setGrabbing(true)
    setHovered(null)
  }
  function onPointerMove(e) {
    if (!drag.current) return
    const dx = e.clientX - drag.current.sx
    const dy = e.clientY - drag.current.sy
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) moved.current = true
    setPan({ x: drag.current.px + dx, y: drag.current.py + dy })
  }
  function endDrag() {
    drag.current = null
    setGrabbing(false)
  }
  function openPlace(id) {
    if (moved.current) return
    setSelected(id)
  }
  const zoomBy = (f) => setZoom((z) => clampZoom(z * f))
  const reset = () => { setZoom(1); setPan({ x: 0, y: 0 }) }

  if (error) return <div className="state state-error">Could not chart the world: {error}</div>
  if (!map) return <div className="state">Charting the world…</div>

  const locations = map.locations.map(placeLocation)
  const byId = Object.fromEntries(locations.map((l) => [l.id, l]))
  const discovered = locations.filter((l) => l.discovered)
  const canvasUrl = map.world?.map_image_url
  const hoveredLoc = hovered ? byId[hovered] : null

  return (
    <>
      <div className="page-head reveal" style={{ '--i': 0 }}>
        <h1>The Living Atlas</h1>
        <p className="page-sub">
          A world that already exists, revealed as people write it. Drag to roam, scroll to zoom,
          hover a beacon to glimpse what's there.
        </p>
      </div>

      <div className="atlas-wrap reveal" style={{ '--i': 1 }}>
        <div
          ref={viewportRef}
          className={`atlas${grabbing ? ' is-grabbing' : ''}`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerLeave={endDrag}
        >
          <div className="atlas-controls">
            <button className="atlas-zoom-btn" onClick={() => zoomBy(1.2)} aria-label="Zoom in">＋</button>
            <button className="atlas-zoom-btn" onClick={() => zoomBy(0.83)} aria-label="Zoom out">−</button>
            <button className="atlas-zoom-btn" onClick={reset} aria-label="Reset view">⟳</button>
          </div>

          <div
            className="atlas-stage"
            style={{ transform: `translate(calc(-50% + ${pan.x}px), calc(-50% + ${pan.y}px)) scale(${zoom})` }}
          >
            {canvasUrl && (
              <img className="atlas-canvas" src={canvasUrl} alt="" draggable="false"
                onError={(e) => { e.currentTarget.style.display = 'none' }} />
            )}

            <svg className="atlas-roads" viewBox="0 0 100 100" preserveAspectRatio="none">
              {locations.flatMap((l) =>
                (l.near || []).map((nid) => {
                  const t = byId[nid]
                  if (!t) return null
                  return <line key={`${l.id}-${nid}`} className="atlas-road" x1={l.x} y1={l.y} x2={t.x} y2={t.y} />
                }),
              )}
            </svg>

            {/* Fog of war: opaque mist with feathered clear holes at discovered places. */}
            <svg className="atlas-fog" viewBox="0 0 100 100" preserveAspectRatio="none">
              <defs>
                <radialGradient id="fogHole">
                  <stop offset="0%" stopColor="#000" />
                  <stop offset="55%" stopColor="#000" />
                  <stop offset="100%" stopColor="#fff" />
                </radialGradient>
                <mask id="fogMask">
                  <rect x="0" y="0" width="100" height="100" fill="#fff" />
                  {discovered.map((l) => (
                    <circle key={l.id} cx={l.x} cy={l.y} r="20" fill="url(#fogHole)" />
                  ))}
                </mask>
              </defs>
              <rect x="0" y="0" width="100" height="100" fill="#1b1d22" opacity="0.9" mask="url(#fogMask)" />
            </svg>

            {locations.map((l) => (
              <button
                key={l.id}
                className={`place${l.discovered ? '' : ' is-fog'}`}
                style={{ left: `${l.x}%`, top: `${l.y}%` }}
                onClick={() => openPlace(l.id)}
                onMouseEnter={() => l.discovered && !drag.current && setHovered(l.id)}
                onMouseLeave={() => setHovered((h) => (h === l.id ? null : h))}
                title={l.discovered ? l.title : 'Uncharted — open to reveal'}
              >
                <span className="place-pin" />
                <span className="place-name">{l.discovered ? l.title : '???'}</span>
              </button>
            ))}

            {/* One hover card at a time (markers stay clean). */}
            {hoveredLoc && hoveredLoc.discovered && (
              <div
                className="place-card"
                style={{ left: `${hoveredLoc.x}%`, top: `${hoveredLoc.y}%` }}
                onMouseEnter={() => setHovered(hoveredLoc.id)}
                onMouseLeave={() => setHovered(null)}
              >
                {hoveredLoc.tile_url && (
                  <img className="pc-thumb" src={hoveredLoc.tile_url} alt=""
                    onError={(e) => { e.currentTarget.style.display = 'none' }} />
                )}
                <div className="pc-body">
                  <div className="pc-title">{hoveredLoc.title}</div>
                  {hoveredLoc.region && <div className="pc-region">{hoveredLoc.region}</div>}
                  <p className="pc-text">{snippet(hoveredLoc.body)}</p>
                  <button className="pc-explore" onClick={() => setSelected(hoveredLoc.id)}>Explore →</button>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="atlas-legend">
          <span><span className="dot lit" />charted ({discovered.length})</span>
          <span><span className="dot fog" />rumored ({locations.length - discovered.length})</span>
          <span className="frontier">drag to roam · scroll to zoom · hover a beacon</span>
        </div>
      </div>

      {selected && (
        <LoreDrawer
          id={selected}
          onClose={() => setSelected(null)}
          onNavigate={(id) => setSelected(id)}
          onDiscovered={onDiscovered}
        />
      )}
    </>
  )
}
