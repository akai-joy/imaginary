import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../api'

function ComicCard({ asset }) {
  return (
    <article className="show-card">
      <div className="comic-grid">
        {asset.gcs_url ? (
          <img className="comic-img" src={asset.gcs_url} alt={asset.caption} />
        ) : (
          (asset.panels || []).map((p, i) => (
            <figure className="panel" key={i}>
              <span className="panel-no">{i + 1}</span>
              <p>{p}</p>
            </figure>
          ))
        )}
      </div>
      <ShowMeta asset={asset} />
    </article>
  )
}

function ReelCard({ asset }) {
  return (
    <article className="show-card">
      <div className="reel">
        {asset.gcs_url ? (
          <video className="reel-video" src={asset.gcs_url} controls playsInline />
        ) : (
          <div className="reel-placeholder">
            <span className="reel-play">▶</span>
            <ol className="reel-scenes">
              {(asset.scenes || []).map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ol>
          </div>
        )}
      </div>
      <ShowMeta asset={asset} />
    </article>
  )
}

function ShowMeta({ asset }) {
  return (
    <div className="show-meta">
      <div className="show-top">
        <Link to={`/story/${asset.tree_id}`} className="show-title">{asset.title}</Link>
        <span className={`kind kind-${asset.kind}`}>{asset.kind}</span>
      </div>
      <p className="show-caption">{asset.caption}</p>
      <p className="meta">
        <span className="synthid">AI-generated · SynthID</span>
        {asset.contributor_ids?.length > 0 && (
          <>
            <span className="dot">·</span>
            <span>{asset.contributor_ids.map((c) => `@${c}`).join(' ')}</span>
          </>
        )}
        {asset.prompt_sheet_url && (
          <>
            <span className="dot">·</span>
            <a href={asset.prompt_sheet_url} target="_blank" rel="noopener noreferrer" className="prompt-link" style={{color: "var(--ochre)", textDecoration: "underline", fontWeight: "bold"}}>
              📄 Prompt Script Sheet
            </a>
          </>
        )}
      </p>
    </div>
  )
}

export default function Showcase() {
  const api = useApi()
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let live = true
    setItems(null)
    setError(null)
    api
      .listShowcase()
      .then((d) => live && setItems(d))
      .catch(() => live && setError('Could not load the showcase.'))
    return () => {
      live = false
    }
  }, [api, reloadKey])

  if (error)
    return (
      <div className="state state-error">
        <p>{error}</p>
        <button className="btn-primary" onClick={() => setReloadKey((k) => k + 1)}>Try again</button>
      </div>
    )
  if (!items) return <p className="state muted">Loading showcase…</p>
  if (items.length === 0)
    return (
      <div className="state">
        <p>No storylines have crossed the showcase threshold yet.</p>
        <Link className="btn-primary" to="/">Explore storylines</Link>
      </div>
    )

  return (
    <div className="page">
      <header className="page-head">
        <h1>Showcase</h1>
        <p className="page-sub">The most-backed storylines, produced into comics and short reels.</p>
      </header>
      <div className="show-grid">
        {items.map((a) => (a.kind === 'reel' ? <ReelCard key={a.id} asset={a} /> : <ComicCard key={a.id} asset={a} />))}
      </div>
    </div>
  )
}
