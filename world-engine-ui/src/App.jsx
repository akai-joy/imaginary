import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import WorldMap from './pages/WorldMap'
import Codex from './pages/Codex'
import Storylines from './pages/Storylines'
import StorylineDetail from './pages/StorylineDetail'
import Showcase from './pages/Showcase'
import Submit from './pages/Submit'
import BackgroundMusic from './components/BackgroundMusic'

export default function App() {
  return (
    <>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<WorldMap />} />
          <Route path="codex/:kind" element={<Codex />} />
          <Route path="storylines" element={<Storylines />} />
          <Route path="showcase" element={<Showcase />} />
          <Route path="submit" element={<Submit />} />
        </Route>
        <Route
          path="story/:treeId"
          element={
            <ProtectedRoute>
              <StorylineDetail />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <BackgroundMusic />
    </>
  )
}
