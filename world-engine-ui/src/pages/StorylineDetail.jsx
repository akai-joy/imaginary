import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useApi } from '../api'
import Thread from '../components/Thread'
import VoteButton from '../components/VoteButton'

export default function StorylineDetail() {
  const { treeId } = useParams()
  const api = useApi()
  const [story, setStory] = useState(null)
  const [error, setError] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)

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

  if (error)
    return (
      <div className="state state-error">
        <p>{error}</p>
        <button className="btn-primary" onClick={() => setReloadKey((k) => k + 1)}>Try again</button>
      </div>
    )
  if (!story) return <p className="state muted">Loading…</p>

  return (
    <div className="page detail">
      <Link to="/" className="back">← All storylines</Link>

      <header className="detail-head">
        <div>
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
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
