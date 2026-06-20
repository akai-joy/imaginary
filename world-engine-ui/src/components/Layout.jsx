import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { apiMock } from '../api'

export default function Layout() {
  const { user, signOutUser } = useAuth()
  const nav = useNavigate()

  async function handleSignOut() {
    await signOutUser()
    nav('/login', { replace: true })
  }

  const initial = (user?.displayName || user?.email || '?').charAt(0).toUpperCase()

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">⌥</span>
          <span className="brand-word">World&nbsp;Engine</span>
        </div>
        <nav className="nav">
          <NavLink to="/" end>Storylines</NavLink>
          <NavLink to="/showcase">Showcase</NavLink>
          <NavLink to="/submit">Submit lore</NavLink>
        </nav>
        <div className="user">
          {apiMock && <span className="badge" title="No backend configured — showing demo data">demo data</span>}
          <span className="avatar" aria-hidden="true">{initial}</span>
          <span className="user-name">{user?.displayName || user?.email}</span>
          <button className="link-btn" onClick={handleSignOut}>Sign out</button>
        </div>
      </header>
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
