import { useEffect, useState, useRef } from 'react'

const SEEN_KEY = 'we_entry_seen'

// The opening_line as a threshold: a Dark-Tower-grade seed sentence, revealed once
// per session before the world itself appears. Highlights the final clause in gold.
// Includes the epic intro soundtrack that loops and fades out on dismissal.
export default function WorldEntry({ world }) {
  const alreadySeen =
    typeof sessionStorage !== 'undefined' && sessionStorage.getItem(SEEN_KEY)
  const [show, setShow] = useState(!alreadySeen)
  const [leaving, setLeaving] = useState(false)
  const [muted, setMuted] = useState(false)
  const audioRef = useRef(null)

  useEffect(() => {
    if (!show) return

    // Create audio instance with our epic Medieval Wizards intro theme
    const audio = new Audio('/MedievalWizards-intro.mp3')
    audio.loop = false
    audio.volume = 0.5
    audioRef.current = audio

    // Autoplay attempt (with user interaction fallback to bypass browser autoplay blocks)
    const playAudio = () => {
      audio.play().catch(() => {
        const startOnInteraction = () => {
          audio.play().catch(() => {})
          window.removeEventListener('click', startOnInteraction)
          window.removeEventListener('keydown', startOnInteraction)
        }
        window.addEventListener('click', startOnInteraction)
        window.addEventListener('keydown', startOnInteraction)
      })
    }

    playAudio()

    const onKey = (e) => {
      if (e.key === 'Enter' || e.key === 'Escape') dismiss()
    }
    window.addEventListener('keydown', onKey)

    return () => {
      audio.pause()
      audio.src = ''
      window.removeEventListener('keydown', onKey)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [show])

  // Sync mute state changes to the audio element
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.muted = muted
    }
  }, [muted])

  if (!show || !world?.opening_line) return null

  function dismiss() {
    setLeaving(true)
    try {
      sessionStorage.setItem(SEEN_KEY, '1')
    } catch {
      /* ignore private-mode storage errors */
    }

    // Smooth fade out of audio to prevent harsh abrupt stops
    if (audioRef.current && !muted) {
      const audio = audioRef.current
      let vol = audio.volume
      const fadeInterval = setInterval(() => {
        if (vol > 0.05) {
          vol -= 0.05
          audio.volume = Math.max(0, vol)
        } else {
          audio.pause()
          clearInterval(fadeInterval)
        }
      }, 50)
    } else if (audioRef.current) {
      audioRef.current.pause()
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
      {/* Top right mute controller */}
      <button 
        className="we-mute reveal" 
        style={{ '--i': 0 }} 
        onClick={() => setMuted(!muted)}
        aria-label={muted ? "Unmute intro music" : "Mute intro music"}
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
          {muted ? (
            <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.21.05-.42.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>
          ) : (
            <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
          )}
        </svg>
      </button>

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
