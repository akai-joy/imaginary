import { useEffect, useRef, useState } from 'react'
import { assetUrl } from '../api'

// Slide-over for the world's own storyteller voice ("what we know so far").
// Mirrors LoreDrawer's panel chrome so it reads as part of the same family as the
// location drawers. `chronicle` is passed in already-loaded (WorldMap fetches it
// on mount, and it's cached server-side), so opening is instant with no spinner.

// Speaker/play icons — same glyph family as ScenePlayer's voice-over control.
const PLAY = <path d="M8 5v14l11-7z" />
const STOP = <><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></>

function PlayButton({ src, label }) {
  const audioRef = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const audio = new Audio(src)
    audioRef.current = audio
    setFailed(false)
    const onEnd = () => setPlaying(false)
    const onError = () => { setPlaying(false); setFailed(true) }
    audio.addEventListener('ended', onEnd)
    audio.addEventListener('error', onError)
    return () => {
      audio.removeEventListener('ended', onEnd)
      audio.removeEventListener('error', onError)
      audio.pause()
      audioRef.current = null
    }
  }, [src])

  const toggle = () => {
    const audio = audioRef.current
    if (!audio) return
    if (playing) {
      audio.pause()
      setPlaying(false)
    } else {
      audio.play().then(() => setPlaying(true)).catch((e) => {
        console.warn('[chronicle] audio playback failed:', src, e?.message)
        setPlaying(false)
        setFailed(true)
      })
    }
  }

  return (
    <button
      type="button"
      className={`chronicle-listen${playing ? ' is-playing' : ''}`}
      onClick={toggle}
      aria-label={playing ? 'Pause narration' : 'Hear the tale'}
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        {playing ? STOP : PLAY}
      </svg>
      <span>{failed ? 'Audio unavailable' : (playing ? 'Pause' : (label || 'Hear the tale'))}</span>
    </button>
  )
}

export default function ChronicleDrawer({ chronicle, onClose }) {
  const audioUrl = assetUrl(chronicle?.audio_url)
  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer" aria-label="What we know so far">
        <button className="drawer-close" onClick={onClose} aria-label="Close">×</button>
        {!chronicle && <p className="muted">The teller clears their throat…</p>}
        {chronicle && (
          <>
            <div className="drawer-kicker">❧ what we know so far</div>
            <h2>{chronicle.persona_label}</h2>
            {audioUrl && <PlayButton src={audioUrl} label={`Hear ${chronicle.persona_label}`} />}
            <p className="chronicle-drawer-text">{chronicle.chronicle_text}</p>
          </>
        )}
      </aside>
    </>
  )
}
