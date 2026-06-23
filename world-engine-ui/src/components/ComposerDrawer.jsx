import { useEffect, useState } from 'react'
import LoreComposer from './LoreComposer'

// Slide-over shell that hosts the LoreComposer in place, so a contributor can continue
// a story or add connected lore without leaving the map / codex / storyline they're on.
// Reuses the same `.drawer` chrome as LoreDrawer for visual continuity.
export default function ComposerDrawer({ continueId, referenceId, initialType, onClose, onSuccess }) {
  const mode = continueId ? 'continue' : 'reference'
  const [done, setDone] = useState(false)

  // On an accepted contribution, refresh the underlying view immediately, then close
  // the drawer after a beat so the author still registers the green verdict.
  useEffect(() => {
    if (!done) return
    const t = setTimeout(() => onClose?.(), 2000)
    return () => clearTimeout(t)
  }, [done, onClose])

  function handleSuccess(r) {
    onSuccess?.(r)
    setDone(true)
  }

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer" aria-label="Compose contribution">
        <button className="drawer-close" onClick={onClose} aria-label="Close">×</button>
        <div className="drawer-kicker">✦ {mode === 'continue' ? 'Continue the story' : 'Add connected lore'}</div>
        <h2>{mode === 'continue' ? 'What happens next' : 'New lore'}</h2>
        <p className="muted" style={{ margin: '0 0 18px' }}>
          {done
            ? 'Woven into the canon. Closing…'
            : 'Runs through moderation, continuity, and scoring before it joins the canon.'}
        </p>
        <LoreComposer
          continueId={continueId}
          referenceId={referenceId}
          initialType={initialType}
          onSuccess={handleSuccess}
        />
      </aside>
    </>
  )
}
