import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useApi } from '../api'
import Thread from '../components/Thread'
import VoteButton from '../components/VoteButton'
import ScenePlayer from '../components/ScenePlayer'
import ComposerDrawer from '../components/ComposerDrawer'

export default function StorylineDetail() {
  const { treeId } = useParams()
  const api = useApi()
  const [story, setStory] = useState(null)
  const [error, setError] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [viewMode, setViewMode] = useState('player')
  // The node a "Continue" action will build on (derived_from). null = drawer closed.
  const [continueFrom, setContinueFrom] = useState(null)
  const [world, setWorld] = useState(null)

  useEffect(() => {
    let alive = true
    api.getWorld().then((w) => alive && setWorld(w)).catch(() => {})
    return () => { alive = false }
  }, [api])

  useEffect(() => {
    let live = true
    setStory(null)
    setError(null)
    api
      .getStoryline(treeId)
      .then((d) => live && setStory(d))
      .catch(() => live && setError('Could not load this storyline.'))
    return () => {
      live = false
    }
  }, [api, treeId, reloadKey])

  const isClosed = world?.window_open === false || world?.status === 'archived'

  if (error)
    return (
      <div className="player-page-immersive">
        <div className="state state-immersive error">
          <p className="msg">{error}</p>
          <button className="btn-toggle-minimal active" onClick={() => setReloadKey((k) => k + 1)}>Try again</button>
        </div>
      </div>
    )
  if (!story)
    return (
      <div className="player-page-immersive">
        <p className="msg">Loading storyline…</p>
      </div>
    )

  // Nodes arrive in lineage order; the last is the thread's tip. Continuing from the
  // tip extends the story; continuing from an earlier node forks it.
  const nodes = story.nodes || []
  const tipId = nodes.length ? nodes[nodes.length - 1].id : story.tree_id

  return (
    <div className="player-page-immersive">
      <header className="immersive-header">
        <Link to="/" className="back-link">
          ← Back to storylines
        </Link>
        <div className="view-toggle-minimal">
          <button
            className={`btn-toggle-minimal ${viewMode === 'player' ? 'active' : ''}`}
            onClick={() => setViewMode('player')}
          >
            🎬 Play Storyline
          </button>
          <button
            className={`btn-toggle-minimal ${viewMode === 'list' ? 'active' : ''}`}
            onClick={() => setViewMode('list')}
          >
            📜 Lineage List
          </button>
          {/* Continue the thread from its latest beat (the tip), or the root if empty. */}
          {!isClosed && (
            <button
              className="btn-continue-story"
              onClick={() =>
                setContinueFrom(tipId)
              }
            >
              ✦ Continue this story
            </button>
          )}
        </div>
      </header>

      {viewMode === 'player' ? (
        <ScenePlayer startSceneId={story.tree_id} />
      ) : (
        <div className="list-content">
          <header className="detail-head-immersive">
            <div className="detail-info">
              <span className={`tag tag-${story.type}`}>{story.type}</span>
              <h1>{story.title}</h1>
              <p className="detail-summary">{story.summary}</p>
              <p className="meta">
                <span>v{story.version}</span>
                <span className="dot">·</span>
                <span>{story.member_count} nodes</span>
                <span className="dot">·</span>
                <span>score {story.composite_score}</span>
              </p>
            </div>
            <VoteButton treeId={story.tree_id} initialTotal={story.vote_total} initialVoted={story.voted} />
          </header>
          <h2 className="section-label">Canon, in order of lineage</h2>
          <ol className="node-list">
            {story.nodes?.map((n) => (
              <li key={n.id} className="node">
                <Thread branched={Boolean(n.derived_from && n.derived_from.length)} tall />
                <div className="node-body">
                  <div className="node-top">
                    <h3 className="node-title">{n.title}</h3>
                    <span className={`tag tag-${n.type}`}>{n.type}</span>
                  </div>
                  <p className="node-text">{n.body}</p>
                  <p className="meta">
                    <span className="contributor">@{n.contributor}</span>
                    <span className="dot">·</span>
                    <span>{n.id}</span>
                    <span className="dot">·</span>
                    <span>v{n.version}</span>
                    {n.derived_from?.length > 0 && (
                      <>
                        <span className="dot">·</span>
                        <span className="derived">⌥ builds on {n.derived_from.join(', ')}</span>
                      </>
                    )}
                  </p>
                  {!isClosed && (
                    <button className="node-continue" onClick={() => setContinueFrom(n.id)}>
                      ✦ {n.id === tipId ? 'Continue from here' : 'Fork from here'}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      {continueFrom && (
        <ComposerDrawer
          continueId={continueFrom}
          onClose={() => setContinueFrom(null)}
          onSuccess={() => setReloadKey((k) => k + 1)}
        />
      )}
    </div>
  )
}
