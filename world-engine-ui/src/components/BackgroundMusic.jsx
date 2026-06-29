import { useEffect, useRef, useState } from 'react'
import { assetUrl } from '../api'

export default function BackgroundMusic() {
  const audioRef = useRef(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [failed, setFailed] = useState(false)

  // Use the cached echoes_ruined_keep.mp3 file
  const musicSrc = assetUrl('/cache/echoes_ruined_keep.mp3')

  useEffect(() => {
    const audio = new Audio(musicSrc)
    audio.loop = true
    audio.volume = 0.2 // Soft background volume
    audioRef.current = audio
    setFailed(false)

    const onError = () => {
      setFailed(true)
      setIsPlaying(false)
    }
    audio.addEventListener('error', onError)

    return () => {
      audio.removeEventListener('error', onError)
      audio.pause()
      audioRef.current = null
    }
  }, [musicSrc])

  const toggle = () => {
    const audio = audioRef.current
    if (!audio) return

    if (isPlaying) {
      // Fade out smoothly
      let vol = audio.volume
      const fade = setInterval(() => {
        if (vol > 0.02) {
          vol -= 0.02
          audio.volume = vol
        } else {
          clearInterval(fade)
          audio.pause()
          setIsPlaying(false)
        }
      }, 30)
    } else {
      audio.volume = 0
      audio.play().then(() => {
        setIsPlaying(true)
        // Fade in smoothly
        let vol = 0
        const fade = setInterval(() => {
          if (vol < 0.2) {
            vol += 0.02
            audio.volume = Math.min(vol, 0.2)
          } else {
            clearInterval(fade)
          }
        }, 30)
      }).catch((e) => {
        console.warn('[music] playback blocked by browser:', e.message)
        setFailed(true)
      })
    }
  }

  return (
    <button
      type="button"
      className={`music-toggle${isPlaying ? ' is-playing' : ''}`}
      onClick={toggle}
      aria-label={isPlaying ? 'Pause background music' : 'Play background music'}
      style={{
        position: 'fixed',
        bottom: '24px',
        right: '24px',
        background: 'rgba(18, 18, 24, 0.75)',
        backdropFilter: 'blur(12px)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: '50px',
        padding: '8px 16px',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        color: '#d1d5db',
        zIndex: 100,
        boxShadow: '0 4px 20px rgba(0, 0, 0, 0.4)',
        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        fontSize: '12px',
        fontWeight: '500',
        letterSpacing: '0.05em',
        fontFamily: 'inherit'
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.25)'
        e.currentTarget.style.transform = 'translateY(-2px)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.1)'
        e.currentTarget.style.transform = 'none'
      }}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style={{ transition: 'transform 0.3s' }}>
        {isPlaying ? (
          <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
        ) : (
          <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h6V3h-6z" />
        )}
      </svg>
      <span>{failed ? 'Music Error' : (isPlaying ? 'Ambient On' : 'Ambient Off')}</span>
    </button>
  )
}
