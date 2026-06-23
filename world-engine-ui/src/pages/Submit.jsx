import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import LoreComposer from '../components/LoreComposer'

// Full-page entry for the composer: the "start something new (a root)" path, and the
// target for shareable deep links (/submit?continue=<id> or ?references=<id>). The
// inline drawers on Map/Codex/Storyline render the same LoreComposer component.
export default function Submit() {
  const [params, setParams] = useSearchParams()
  const continueId = params.get('continue')
  const referenceId = params.get('references')
  const typeParam = params.get('type')
  const mode = continueId ? 'continue' : referenceId ? 'reference' : null

  const heading = useMemo(() => {
    if (mode === 'continue') return 'Continue the story'
    if (mode === 'reference') return 'Add connected lore'
    return 'Submit lore'
  }, [mode])

  function clearSeed() {
    const next = new URLSearchParams(params)
    next.delete('continue')
    next.delete('references')
    setParams(next, { replace: true })
  }

  return (
    <div className="page narrow">
      <header className="page-head">
        <h1>{heading}</h1>
        <p className="page-sub">
          Your contribution runs through moderation, continuity, and scoring before it joins the canon.
        </p>
      </header>

      <LoreComposer
        continueId={continueId}
        referenceId={referenceId}
        initialType={typeParam}
        onClearSeed={continueId || referenceId ? clearSeed : undefined}
      />
    </div>
  )
}
