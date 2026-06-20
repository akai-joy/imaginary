import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth'

export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  const loc = useLocation()

  if (loading) return <div className="screen-center muted">Loading…</div>
  if (!user) return <Navigate to="/login" replace state={{ from: loc }} />
  return children
}
