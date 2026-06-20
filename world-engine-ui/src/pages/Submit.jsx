import { useState } from 'react'
import { useApi } from '../api'

const TYPES = ['character', 'location', 'faction', 'plot', 'lore']

export default function Submit() {
  const api = useApi()
  const [title, setTitle] = useState('')
  const [type, setType] = useState('character')
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  async function onSubmit(e) {
    e.preventDefault()
    if (!title.trim() || !body.trim() || busy) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const r = await api.submitContribution({ title: title.trim(), type, body: body.trim() })
      setResult(r)
      if (r?.verdict === 'ALLOW' || r?.status === 'accepted') {
        setTitle('')
        setBody('')
      }
    } catch (e) {
      setError('Submission failed. Check your connection and try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page narrow">
      <header className="page-head">
        <h1>Submit lore</h1>
        <p className="page-sub">
          Your contribution runs through moderation, continuity, and scoring before it joins the canon.
        </p>
      </header>

      <form className="form" onSubmit={onSubmit}>
        <label className="field">
          <span>Title</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. The Tideward Archive" maxLength={120} />
        </label>

        <label className="field">
          <span>Type</span>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>The lore</span>
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={8} maxLength={4000}
            placeholder="Describe the character, place, faction, or event — and how it connects to what already exists." />
          <span className="count">{body.length}/4000</span>
        </label>

        <button className="btn-primary" type="submit" disabled={busy}>
          {busy ? 'Sending through the pipeline…' : 'Submit to canon'}
        </button>
      </form>

      {error && <p className="state state-error">{error}</p>}

      {result && (
        <div className={`verdict verdict-${(result.verdict || result.status || '').toLowerCase()}`}>
          <p className="verdict-line">
            <strong>{result.verdict || result.status}</strong>
            {typeof result.score === 'number' && <span className="verdict-score">score {result.score}</span>}
          </p>
          {result.message && <p className="verdict-msg">{result.message}</p>}
        </div>
      )}
    </div>
  )
}
