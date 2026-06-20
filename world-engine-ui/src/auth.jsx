import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { GoogleAuthProvider, signInWithPopup, signOut, onAuthStateChanged } from 'firebase/auth'
import { auth, firebaseEnabled } from './firebase'

const AuthCtx = createContext(null)

const DEMO_USER = {
  uid: 'demo-author',
  displayName: 'Demo Author',
  email: 'demo@worldengine.local',
  photoURL: null,
  demo: true,
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!firebaseEnabled) {
      setLoading(false)
      return
    }
    return onAuthStateChanged(auth, (u) => {
      setUser(u)
      setLoading(false)
    })
  }, [])

  const signInWithGoogle = useCallback(async () => {
    if (!firebaseEnabled) {
      setUser(DEMO_USER)
      return
    }
    await signInWithPopup(auth, new GoogleAuthProvider())
  }, [])

  const continueDemo = useCallback(() => setUser(DEMO_USER), [])

  const signOutUser = useCallback(async () => {
    if (firebaseEnabled && !user?.demo) await signOut(auth)
    setUser(null)
  }, [user])

  // Returns the Firebase ID token to send as `Authorization: Bearer <token>`.
  // Your FastAPI backend verifies it with the Firebase Admin SDK.
  const getToken = useCallback(async () => {
    if (firebaseEnabled && auth.currentUser) return auth.currentUser.getIdToken()
    return null
  }, [])

  return (
    <AuthCtx.Provider
      value={{ user, loading, firebaseEnabled, signInWithGoogle, continueDemo, signOutUser, getToken }}
    >
      {children}
    </AuthCtx.Provider>
  )
}

export const useAuth = () => useContext(AuthCtx)
