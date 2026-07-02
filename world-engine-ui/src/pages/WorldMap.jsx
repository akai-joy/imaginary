import { useCallback, useEffect, useRef, useState } from 'react'
import { useApi } from '../api'
import LoreDrawer from '../components/LoreDrawer'
import ChronicleDrawer from '../components/ChronicleDrawer'
import ComposerDrawer from '../components/ComposerDrawer'

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

function getCleanUrl(url) {
  if (!url) return ''
  if (url.startsWith('http://localhost:8000/')) {
    return url.replace('http://localhost:8000/', '/')
  }
  return url
}

const MIN_ZOOM = 0.6
const MAX_ZOOM = 5
const clampZoom = (z) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z))

// Keep at least ~140px of the stage inside the viewport so the map can't be dragged away.
function clampPan(pan, zoom, rect) {
  const half = (rect.height * zoom) / 2
  const maxX = rect.width / 2 + half - 140
  const maxY = rect.height / 2 + half - 140
  return {
    x: Math.min(maxX, Math.max(-maxX, pan.x)),
    y: Math.min(maxY, Math.max(-maxY, pan.y)),
  }
}

// Zoom about an anchor point (ax/ay are offsets from the viewport centre) so the
// world under the cursor/pinch stays put: screen = centre + pan + world·zoom.
function zoomAt(view, nextZoom, ax, ay, rect) {
  const z = clampZoom(nextZoom)
  const f = z / view.zoom
  return {
    zoom: z,
    pan: clampPan({ x: ax - (ax - view.pan.x) * f, y: ay - (ay - view.pan.y) * f }, z, rect),
  }
}

export default function WorldMap() {
  const api = useApi()
  const [map, setMap] = useState(null)
  const [chronicle, setChronicle] = useState(null)
  const [showChronicle, setShowChronicle] = useState(false)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [hovered, setHovered] = useState(null)
  const [composeFor, setComposeFor] = useState(null)

  const [view, setView] = useState({ zoom: 1, pan: { x: 0, y: 0 } })
  const [grabbing, setGrabbing] = useState(false)
  const viewportRef = useRef(null)
  const pointers = useRef(new Map()) // active pointerId -> {x, y} (2 = pinch)
  const gesture = useRef(null)
  const moved = useRef(false)

  const load = useCallback(() => {
    api.getMap().then(setMap).catch((e) => setError(e.message))
  }, [api])
  useEffect(() => { load() }, [load])

  // The world's own voice — loaded once, independently of the map (it's cached
  // server-side by world + story count, so this is cheap on re-open).
  useEffect(() => {
    let alive = true
    api.getChronicle().then((c) => alive && setChronicle(c)).catch(() => {})
    return () => { alive = false }
  }, [api])

  useEffect(() => {
    const el = viewportRef.current
    if (!el) return
    const onWheel = (e) => {
      e.preventDefault()
      const rect = el.getBoundingClientRect()
      const ax = e.clientX - rect.left - rect.width / 2
      const ay = e.clientY - rect.top - rect.height / 2
      setView((v) => zoomAt(v, v.zoom * (e.deltaY < 0 ? 1.12 : 0.89), ax, ay, rect))
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
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    const pts = [...pointers.current.values()]
    if (pts.length === 1) {
      gesture.current = { mode: 'pan', sx: e.clientX, sy: e.clientY, pan0: view.pan }
      moved.current = false
      setGrabbing(true)
      setHovered(null)
    } else if (pts.length === 2) {
      const [a, b] = pts
      gesture.current = {
        mode: 'pinch',
        d0: Math.hypot(a.x - b.x, a.y - b.y),
        mid0: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
        view0: view,
      }
      moved.current = true
    }
  }
  function onPointerMove(e) {
    if (!pointers.current.has(e.pointerId)) return
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    const g = gesture.current
    const el = viewportRef.current
    if (!g || !el) return
    const rect = el.getBoundingClientRect()
    if (g.mode === 'pan') {
      const dx = e.clientX - g.sx
      const dy = e.clientY - g.sy
      if (Math.abs(dx) > 4 || Math.abs(dy) > 4) moved.current = true
      setView((v) => ({ ...v, pan: clampPan({ x: g.pan0.x + dx, y: g.pan0.y + dy }, v.zoom, rect) }))
    } else if (g.mode === 'pinch' && pointers.current.size >= 2) {
      const [a, b] = [...pointers.current.values()]
      const d = Math.hypot(a.x - b.x, a.y - b.y)
      const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
      const ax = g.mid0.x - rect.left - rect.width / 2
      const ay = g.mid0.y - rect.top - rect.height / 2
      const next = zoomAt(g.view0, g.view0.zoom * (d / (g.d0 || 1)), ax, ay, rect)
      next.pan = clampPan(
        { x: next.pan.x + (mid.x - g.mid0.x), y: next.pan.y + (mid.y - g.mid0.y) },
        next.zoom, rect,
      )
      setView(next)
    }
  }
  function onPointerUp(e) {
    pointers.current.delete(e.pointerId)
    const pts = [...pointers.current.values()]
    if (pts.length === 1) {
      // Pinch ended with one finger still down: continue as a pan from here.
      gesture.current = { mode: 'pan', sx: pts[0].x, sy: pts[0].y, pan0: view.pan }
    } else if (pts.length === 0) {
      gesture.current = null
      setGrabbing(false)
    }
  }
  function onPointerLeave() {
    pointers.current.clear()
    gesture.current = null
    setGrabbing(false)
  }
  function openPlace(id) {
    if (moved.current) return
    setSelected(id)
  }
  const zoomBy = (f) => {
    const rect = viewportRef.current?.getBoundingClientRect()
    if (!rect) return
    setView((v) => zoomAt(v, v.zoom * f, 0, 0, rect))
  }
  const reset = () => setView({ zoom: 1, pan: { x: 0, y: 0 } })

  if (error) return <div className="state state-error">Could not chart the world: {error}</div>
  if (!map) return <div className="state">Charting the world…</div>

  const baseLocations = map.locations.map(placeLocation)
  const locations = []
  const coordCount = {}

  for (const rawLoc of baseLocations) {
    const loc = { ...rawLoc }
    const key = `${loc.x.toFixed(2)},${loc.y.toFixed(2)}`
    if (coordCount[key]) {
      const count = coordCount[key]
      coordCount[key] += 1
      const angle = (count * 2 * Math.PI) / 6
      const r = 3.0 // radial offset radius in percent
      loc.x = Math.max(2, Math.min(98, loc.x + r * Math.cos(angle)))
      loc.y = Math.max(2, Math.min(98, loc.y + r * Math.sin(angle)))
    } else {
      coordCount[key] = 1
    }
    locations.push(loc)
  }

  const byId = Object.fromEntries(locations.map((l) => [l.id, l]))
  const discovered = locations.filter((l) => l.discovered)
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
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onPointerLeave={onPointerLeave}
        >
          <div className="atlas-controls">
            <button className="atlas-zoom-btn" onClick={() => zoomBy(1.2)} aria-label="Zoom in">＋</button>
            <button className="atlas-zoom-btn" onClick={() => zoomBy(0.83)} aria-label="Zoom out">−</button>
            <button className="atlas-zoom-btn" onClick={reset} aria-label="Reset view">⟳</button>
          </div>

          {chronicle?.chronicle_text && (
            <button
              type="button"
              className="chronicle-trigger"
              onClick={(e) => { e.stopPropagation(); setShowChronicle(true) }}
              onPointerDown={(e) => e.stopPropagation()}
            >
              <span className="ct-mark">❧</span>
              <span className="ct-label">Let {chronicle.persona_label} catch you up on the world</span>
            </button>
          )}

          <div
            className="atlas-stage"
            style={{
              transform: `translate(calc(-50% + ${view.pan.x}px), calc(-50% + ${view.pan.y}px)) scale(${view.zoom})`,
              // Counter-scale for pins/labels/cards so annotations stay constant-size
              // while the world zooms (capped so labels don't balloon at min zoom).
              '--inv': Math.min(1.45, 1 / view.zoom),
            }}
          >
            <div className="atlas-worldmap" aria-hidden="true" />

            {/* Ambient candlelit light pools illuminating the parchment underlay at discovered places */}
            {discovered.map((l) => (
              <div
                key={`light-${l.id}`}
                className="place-light"
                style={{
                  position: 'absolute',
                  left: `${l.x}%`,
                  top: `${l.y}%`,
                  transform: 'translate(-50%, -50%)',
                  width: '40%',
                  height: '40%',
                  borderRadius: '50%',
                  background: 'radial-gradient(circle, rgba(245, 158, 11, 0.16) 0%, rgba(245, 158, 11, 0.05) 50%, transparent 100%)',
                  pointerEvents: 'none',
                  zIndex: 1,
                  mixBlendMode: 'color-dodge',
                }}
              />
            ))}

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
            <svg
              className="atlas-fog"
              viewBox="-50 -50 200 200"
              preserveAspectRatio="none"
              style={{
                position: 'absolute',
                left: '-50%',
                top: '-50%',
                width: '200%',
                height: '200%',
              }}
            >
              <defs>
                <radialGradient id="fogHole">
                  <stop offset="0%" stopColor="#000" />
                  <stop offset="45%" stopColor="#000" />
                  <stop offset="100%" stopColor="#fff" />
                </radialGradient>
                <mask id="fogMask">
                  <rect x="-50" y="-50" width="200" height="200" fill="#fff" />
                  {discovered.map((l) => (
                    <circle key={l.id} cx={l.x} cy={l.y} r="28" fill="url(#fogHole)" />
                  ))}
                </mask>
              </defs>
              <rect x="-50" y="-50" width="200" height="200" fill="#0f1013" opacity="0.94" mask="url(#fogMask)" />
            </svg>

            {/* Charted lantern pools: the location's painted tile, above the fog. */}
            {locations.map((l) =>
              l.discovered && l.tile_url ? (
                <img
                  key={`tile-${l.id}`}
                  className="place-tile"
                  src={getCleanUrl(l.tile_url)}
                  style={{ left: `${l.x}%`, top: `${l.y}%` }}
                  alt=""
                  draggable="false"
                  onError={(e) => { e.currentTarget.style.display = 'none' }}
                />
              ) : null,
            )}

            {locations.map((l) => (
              <button
                key={l.id}
                className={`place${l.discovered ? '' : ' is-fog'}`}
                style={{ left: `${l.x}%`, top: `${l.y}%` }}
                onClick={() => openPlace(l.id)}
                onMouseEnter={() => l.discovered && !gesture.current && setHovered(l.id)}
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
                className={`place-card${hoveredLoc.x > 62 ? ' flip-x' : ''}${hoveredLoc.y < 24 ? ' flip-y' : ''}`}
                style={{ left: `${hoveredLoc.x}%`, top: `${hoveredLoc.y}%` }}
                onMouseEnter={() => setHovered(hoveredLoc.id)}
                onMouseLeave={() => setHovered(null)}
              >
                {hoveredLoc.tile_url && (
                  <img className="pc-thumb" src={getCleanUrl(hoveredLoc.tile_url)} alt=""
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

      {showChronicle && (
        <ChronicleDrawer chronicle={chronicle} onClose={() => setShowChronicle(false)} />
      )}

      {selected && (
        <LoreDrawer
          id={selected}
          tileUrl={getCleanUrl(byId[selected]?.tile_url)}
          onClose={() => setSelected(null)}
          onNavigate={(id) => setSelected(id)}
          onDiscovered={onDiscovered}
          onCompose={(id) => { setSelected(null); setComposeFor(id) }}
        />
      )}

      {composeFor && (
        <ComposerDrawer
          referenceId={composeFor}
          onClose={() => setComposeFor(null)}
          onSuccess={load}
        />
      )}
    </>
  )
}
