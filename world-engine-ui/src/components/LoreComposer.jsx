import { useEffect, useMemo, useState } from 'react'
import { useApi } from '../api'

// value -> friendly label. Beast (Bestiary) and Spell (Grimoire) belong here too —
// the Codex browses them and the backend ContributionType supports them.
export const TYPES = [
  { value: 'character', label: 'Character' },
  { value: 'location', label: 'Location' },
  { value: 'beast', label: 'Beast' },
  { value: 'spell', label: 'Spell · Grimoire' },
  { value: 'faction', label: 'Faction' },
  { value: 'plot', label: 'Plot beat' },
  { value: 'lore', label: 'Lore' },
]
export const VALID_TYPES = new Set(TYPES.map((t) => t.value))

function snippet(text, n = 120) {
  if (!text) return ''
  if (text.length <= n) return text
  return text.slice(0, text.lastIndexOf(' ', n)) + '…'
}

// The single source of truth for composing a contribution. Mounted full-page by
// /submit and inline (in a slide-over) from the Map, Codex, and Storyline surfaces.
//
//   continueId  -> derived_from (the "fold": you're continuing a thread)
//   referenceId -> references   (you're connecting new lore to existing canon)
//
// The entry point picks which one; the author never sees the field names.
export default function LoreComposer({
  continueId = null,
  referenceId = null,
  initialType,
  onClearSeed,
  onSuccess,
}) {
  const api = useApi()
  const seedId = continueId || referenceId
  const mode = continueId ? 'continue' : referenceId ? 'reference' : null

  const defaultType = useMemo(() => {
    if (VALID_TYPES.has(initialType)) return initialType
    return continueId ? 'plot' : 'character'
  }, [initialType, continueId])

  const [title, setTitle] = useState('')
  const [type, setType] = useState(defaultType)
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [seed, setSeed] = useState(null)

  // Load the node we're building on so we can show "Continuing: …" with a snippet —
  // and, per the fold principle, only the fragment you attach to, not the whole canon.
  useEffect(() => {
    let alive = true
    if (!seedId) {
      setSeed(null)
      return
    }
    api.getCanon(seedId).then((r) => alive && setSeed(r)).catch(() => alive && setSeed(null))
    return () => {
      alive = false
    }
  }, [api, seedId])

  async function onSubmit(e) {
    e.preventDefault()
    if (!title.trim() || !body.trim() || busy) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const payload = { title: title.trim(), type, body: body.trim() }
      if (continueId) payload.derived_from = [continueId]
      if (referenceId) payload.references = [referenceId]
      const r = await api.submitContribution(payload)
      setResult(r)
      // Keep the draft on BLOCK/contradiction so the author can edit and resubmit.
      if (r?.verdict === 'ALLOW' || r?.status === 'accepted') {
        setTitle('')
        setBody('')
        onSuccess?.(r)
      }
    } catch (e) {
      setError('Submission failed. Check your connection and try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      {seedId && (
        <div className="compose-context">
          <span className="cc-label">{mode === 'continue' ? 'Continuing' : 'Connected to'}</span>
          <div className="cc-card">
            <strong>{seed?.title || (mode === 'continue' ? 'this storyline' : 'this entry')}</strong>
            {seed?.body && <span className="cc-snip">{snippet(seed.body)}</span>}
          </div>
          {onClearSeed && (
            <button type="button" className="cc-clear" onClick={onClearSeed} aria-label="Remove context">×</button>
          )}
        </div>
      )}

      <form className="form" onSubmit={onSubmit}>
        <label className="field">
          <span>Title</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. The Tideward Archive" maxLength={120} />
        </label>

        <label className="field">
          <span>Type</span>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>{mode === 'continue' ? 'What happens next' : 'The lore'}</span>
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={8} maxLength={4000}
            placeholder={
              mode === 'continue'
                ? 'Write the next beat — what follows from the moment above?'
                : 'Describe the character, place, faction, or event — and how it connects to what already exists.'
            } />
          <span className="count">{body.length}/4000</span>
        </label>

        <button className="btn-primary" type="submit" disabled={!title.trim() || !body.trim() || busy}>
          {busy ? 'Sending through the pipeline…' : mode === 'continue' ? 'Add to the story' : 'Submit to canon'}
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
    </>
  )
}
