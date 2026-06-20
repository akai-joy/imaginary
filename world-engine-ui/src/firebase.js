import { initializeApp } from 'firebase/app'
import { getAuth } from 'firebase/auth'

const cfg = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
}

// Real Google auth turns on only when the core keys are present.
export const firebaseEnabled = Boolean(cfg.apiKey && cfg.authDomain && cfg.projectId)
export const auth = firebaseEnabled ? getAuth(initializeApp(cfg)) : null
