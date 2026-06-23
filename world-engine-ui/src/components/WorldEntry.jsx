import { useEffect, useState } from 'react'

const SEEN_KEY = 'we_entry_seen'

// The opening_line as a threshold: a Dark-Tower-grade seed sentence, revealed once
// per session before the world itself appears. Highlights the final clause in gold.
export default function WorldEntry({ world }) {
  const alreadySeen =
    typeof sessionStorage !== 'undefined' && sessionStorage.getItem(SEEN_KEY)
  const [show, setShow] = useState(!alreadySeen)
  const [leaving, setLeaving] = useState(false)

  useEffect(() => {
    if (!show) return
    const onKey = (e) => {
      if (e.key === 'Enter' || e.key === 'Escape') dismiss()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [show])

  if (!show || !world?.opening_line) return null

  function dismiss() {
    setLeaving(true)
    try {
      sessionStorage.setItem(SEEN_KEY, '1')
    } catch {
      /* ignore private-mode storage errors */
    }
    setTimeout(() => setShow(false), 850)
  }

  // Glow the final clause (after the last comma) for a pursuit-pressure beat.
  const line = world.opening_line
  const cut = line.lastIndexOf(',')
  const head = cut > 0 ? line.slice(0, cut + 1) : line
  const tail = cut > 0 ? line.slice(cut + 1) : ''

  return (
    <div className={`world-entry${leaving ? ' is-leaving' : ''}`} role="dialog" aria-label="Enter the world">
      <div className="we-inner">
        <p className="we-eyebrow reveal" style={{ '--i': 0 }}>A world opens</p>
        <p className="we-theme reveal" style={{ '--i': 1 }}>{world.theme}</p>
        <p className="we-line reveal" style={{ '--i': 2 }}>
          {head}
          {tail && <span className="glow">{tail}</span>}
        </p>
        <div className="reveal" style={{ '--i': 4 }}>
          <button className="we-enter" onClick={dismiss}>Enter the world</button>
          <button className="we-skip" onClick={dismiss}>skip</button>
        </div>
      </div>
    </div>
  )
}
