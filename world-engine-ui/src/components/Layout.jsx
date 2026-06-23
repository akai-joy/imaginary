import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { apiMock, useApi } from '../api'
import WorldEntry from './WorldEntry'

function countdown(closesAt) {
  if (!closesAt) return null
  const ms = new Date(closesAt).getTime() - Date.now()
  if (Number.isNaN(ms) || ms <= 0) return 'closed'
  const d = Math.floor(ms / 86400000)
  const h = Math.floor((ms % 86400000) / 3600000)
  const m = Math.floor((ms % 3600000) / 60000)
  return d > 0 ? `${d}d ${h}h` : `${h}h ${m}m`
}

export default function Layout() {
  const { user, signOutUser } = useAuth()
  const api = useApi()
  const nav = useNavigate()
  const [world, setWorld] = useState(null)
  const [left, setLeft] = useState(null)

  useEffect(() => {
    let alive = true
    api.getWorld().then((w) => alive && setWorld(w)).catch(() => {})
    return () => { alive = false }
  }, [api])

  useEffect(() => {
    if (!world?.closes_at) return
    const tick = () => setLeft(countdown(world.closes_at))
    tick()
    const id = setInterval(tick, 60000)
    return () => clearInterval(id)
  }, [world])

  async function handleSignOut() {
    await signOutUser()
    nav('/login', { replace: true })
  }

  const initial = (user?.displayName || user?.email || '?').charAt(0).toUpperCase()

  return (
    <div className="app">
      {world && <WorldEntry world={world} />}

      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">✦</span>
          <span className="brand-word">World&nbsp;Engine</span>
        </div>
        <nav className="nav">
          <NavLink to="/" end>Map</NavLink>
          <NavLink to="/codex/characters">Codex</NavLink>
          <NavLink to="/storylines">Storylines</NavLink>
          <NavLink to="/showcase">Showcase</NavLink>
          {/* Prominent global entry for starting a brand-new root (no seed = new thread). */}
          <NavLink to="/submit" className="nav-cta">✦ Add lore</NavLink>
        </nav>
        <div className="user">
          {apiMock && <span className="badge" title="No backend configured — showing demo data">demo data</span>}
          <span className="avatar" aria-hidden="true">{initial}</span>
          <span className="user-name">{user?.displayName || user?.email}</span>
          <button className="link-btn" onClick={handleSignOut}>Sign out</button>
        </div>
      </header>

      {world && (
        <section className="world-banner">
          <div>
            <span className="wb-mark">Active drop · {world.theme}</span>
            {world.opening_line && <p className="wb-line">“{world.opening_line}”</p>}
          </div>
          {left && (
            <div className="wb-clock" title="When this drop closes it is archived as a collectible">
              <span className="t">{left}</span>
              <span className="l">until the world closes</span>
            </div>
          )}
        </section>
      )}

      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
