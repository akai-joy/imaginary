import { useState, useEffect, useRef, useCallback } from "react";
import { useApi } from "../api";

// --- Demo fallback if graph nodes don't exist yet ---
import { DEMO } from "../mock";

function normalizeScene(raw) {
  return {
    id: raw.id,
    title: raw.title,
    logline: raw.logline,
    panels: (raw.panels || []).map((p) => ({
      id: p.id,
      prompt: p.prompt,
      caption: p.caption,
      imageUrl: p.imageUrl ?? null,
      videoUrl: p.videoUrl ?? null,
      audioUrl: p.audioUrl ?? null,
      durationMs: p.durationMs ?? 5200,
      kind: p.videoUrl ? "video" : p.kind ?? "image",
    })),
    choices: raw.choices || [],
  };
}

// --- Helper to format aspect ratio and resolution ---
function getMediaSizeLabel(width, height) {
  if (!width || !height) return "";
  const ratio = width / height;
  const tolerance = 0.05;
  let ratioStr = "";
  if (Math.abs(ratio - 9/16) < tolerance) {
    ratioStr = "9:16";
  } else if (Math.abs(ratio - 16/9) < tolerance) {
    ratioStr = "16:9";
  } else if (Math.abs(ratio - 4/3) < tolerance) {
    ratioStr = "4:3";
  } else if (Math.abs(ratio - 3/4) < tolerance) {
    ratioStr = "3:4";
  } else if (Math.abs(ratio - 1/1) < tolerance) {
    ratioStr = "1:1";
  } else if (Math.abs(ratio - 16/10) < tolerance) {
    ratioStr = "16:10";
  } else {
    const gcd = (a, b) => (b ? gcd(b, a % b) : a);
    const divisor = gcd(Math.round(width), Math.round(height));
    const w = Math.round(width / divisor);
    const h = Math.round(height / divisor);
    if (w < 50 && h < 50 && w > 0 && h > 0) {
      ratioStr = `${w}:${h}`;
    } else {
      ratioStr = ratio.toFixed(2) + ":1";
    }
  }
  return `${ratioStr} (${Math.round(width)}x${Math.round(height)})`;
}

// --- Icons ---------------------------------------------------------------------
const I = {
  play: <path d="M8 5v14l11-7z" />,
  pause: (
    <>
      <rect x="6" y="5" width="4" height="14" rx="1" />
      <rect x="14" y="5" width="4" height="14" rx="1" />
    </>
  ),
  prev: <path d="M7 6v12M9 12l9 6V6z" />,
  next: <path d="M17 6v12M15 12L6 6v12z" />,
  speaker: <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>,
  speakerMute: <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.21.05-.42.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>,
};

const Icon = ({ d, stroke, size = "22" }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill={stroke ? "none" : "currentColor"}
    stroke={stroke ? "currentColor" : "none"}
    strokeWidth="1.8"
    strokeLinejoin="round"
    strokeLinecap="round"
  >
    {d}
  </svg>
);

// --- Visual for a panel: real video, real image, or a styled placeholder -------
function PanelVisual({ panel, index, playing, videoRef, onLayout }) {
  const kb = `kb-${index % 2 === 0 ? "a" : "b"} ${playing ? "kb-on" : ""}`;
  if (panel.videoUrl) {
    return (
      <video
        ref={videoRef}
        className={`stage-media ${kb}`}
        src={panel.videoUrl}
        muted={Boolean(panel.audioUrl)}
        playsInline
        preload="auto"
        onLoadedMetadata={(e) => {
          if (e.target.videoWidth && e.target.videoHeight) {
            onLayout(e.target.videoWidth, e.target.videoHeight);
          }
        }}
      />
    );
  }
  if (panel.imageUrl) {
    return (
      <img
        className={`stage-media ${kb}`}
        src={panel.imageUrl}
        alt={panel.caption}
        onLoad={(e) => {
          if (e.target.naturalWidth && e.target.naturalHeight) {
            onLayout(e.target.naturalWidth, e.target.naturalHeight);
          }
        }}
      />
    );
  }
  // placeholders so the demo renders without assets
  const isVideo = panel.kind === "video";
  return (
    <div className={`panel-ph ${isVideo ? "panel-ph-video" : ""}`}>
      {isVideo && <span className="veo-shimmer" aria-hidden="true" />}
      <span className="panel-ph-no">Panel {index + 1}{isVideo ? " · video" : ""}</span>
      <p className="panel-ph-prompt">{panel.prompt}</p>
      <span className="panel-ph-tag">
        {isVideo ? "Veo clip pending · {videoUrl}" : "image pending · {imageUrl}"}
      </span>
    </div>
  );
}

// --- Player Stage & Controls ---------------------------------------------------
function PlayerStage({ scene, onChoose, breadcrumb }) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [atChoices, setAtChoices] = useState(false);
  const [progress, setProgress] = useState(0);
  const [showCaptions, setShowCaptions] = useState(true);
  const [voiceoverEnabled, setVoiceoverEnabled] = useState(true);
  const synthRef = useRef(window.speechSynthesis);
  const utteranceRef = useRef(null);
  const [mediaDimensions, setMediaDimensions] = useState({
    width: 0,
    height: 0,
    ratio: 16 / 10,
    isEstimated: true
  });
  const audioRef = useRef(null);
  const videoRef = useRef(null);

  const panels = scene.panels;
  const panel = panels[index];
  const isLast = index === panels.length - 1;

  useEffect(() => {
    const handleVoices = () => {};
    if (synthRef.current) {
      synthRef.current.addEventListener("voiceschanged", handleVoices);
    }
    return () => {
      if (synthRef.current) {
        synthRef.current.removeEventListener("voiceschanged", handleVoices);
      }
    };
  }, []);

  useEffect(() => {
    setIndex(0);
    setPlaying(true);
    setAtChoices(false);
    setProgress(0);
  }, [scene.id]);

  useEffect(() => {
    // Default fallback ratios: vertical 9:16 for videos, landscape 16:10 for images/placeholders
    const isVideo = panel.videoUrl || panel.kind === "video";
    setMediaDimensions({
      width: isVideo ? 720 : 1600,
      height: isVideo ? 1280 : 1000,
      ratio: isVideo ? 9 / 16 : 16 / 10,
      isEstimated: true
    });
  }, [panel.id, panel.videoUrl, panel.kind]);

  const handleMediaLayout = useCallback((width, height) => {
    setMediaDimensions({
      width,
      height,
      ratio: width / height,
      isEstimated: false
    });
  }, []);

  const goNext = useCallback(() => {
    setProgress(0);
    if (isLast) {
      setAtChoices(true);
      setPlaying(false);
    } else {
      setIndex((i) => i + 1);
    }
  }, [isLast]);

  const goPrev = useCallback(() => {
    setProgress(0);
    setAtChoices(false);
    setIndex((i) => Math.max(0, i - 1));
  }, []);

  // playback driver: audio ▸ voiceover ▸ video ▸ timer
  useEffect(() => {
    if (!playing || atChoices) {
      if (synthRef.current) {
        synthRef.current.cancel();
      }
      return;
    }
    const dur = panel.durationMs || 5200;
    const audio = panel.audioUrl ? audioRef.current : null;
    const video = panel.videoUrl ? videoRef.current : null;

    if (video) video.play().catch(() => {});

    if (audio) {
      audio.play().catch(() => {});
      const onTime = () => audio.duration && setProgress(audio.currentTime / audio.duration);
      const onEnd = () => goNext();
      audio.addEventListener("timeupdate", onTime);
      audio.addEventListener("ended", onEnd);
      return () => {
        audio.pause();
        if (video) video.pause();
        audio.removeEventListener("timeupdate", onTime);
        audio.removeEventListener("ended", onEnd);
      };
    }

    if (voiceoverEnabled && panel.caption && synthRef.current) {
      synthRef.current.cancel();

      const timeoutId = setTimeout(() => {
        if (!playing || atChoices) return;

        const utterance = new SpeechSynthesisUtterance(panel.caption);
        const voices = synthRef.current.getVoices();
        // Prioritize high-quality British Male voices (Daniel, Oliver, or Google UK English Male)
        const targetVoice = voices.find(v => 
          (v.lang.startsWith("en-GB") || v.lang.startsWith("en_GB")) && 
          (v.name.includes("Daniel") || v.name.includes("Oliver") || v.name.includes("Male") || v.name.includes("Google"))
        ) || voices.find(v => 
          (v.lang.startsWith("en-GB") || v.lang.startsWith("en_GB"))
        ) || voices.find(v => 
          v.lang.startsWith("en") && (v.name.includes("Natural") || v.name.includes("Google"))
        );

        if (targetVoice) {
          utterance.voice = targetVoice;
        }

        utterance.rate = 1.0;
        utteranceRef.current = utterance;

        utterance.onstart = () => {
          if (video) video.play().catch(() => {});
        };

        utterance.onend = () => {
          goNext();
        };

        utterance.onerror = (e) => {
          if (e.error !== "interrupted") {
            console.warn("Speech synthesis error", e);
          }
        };

        synthRef.current.speak(utterance);
      }, 100);

      // Track progress roughly using an interval since SpeechSynthesis doesn't have fine timeupdate
      const startTime = performance.now();
      const interval = setInterval(() => {
        const elapsed = performance.now() - startTime;
        setProgress(Math.min(0.99, elapsed / dur));
      }, 100);

      return () => {
        clearTimeout(timeoutId);
        clearInterval(interval);
        if (synthRef.current) {
          synthRef.current.cancel();
        }
        if (video) video.pause();
      };
    }

    if (video) {
      const onTime = () => video.duration && setProgress(video.currentTime / video.duration);
      const onEnd = () => goNext();
      video.addEventListener("timeupdate", onTime);
      video.addEventListener("ended", onEnd);
      return () => {
        video.pause();
        video.removeEventListener("timeupdate", onTime);
        video.removeEventListener("ended", onEnd);
      };
    }
    let raf;
    const start = performance.now() - progress * dur;
    const tick = (now) => {
      const p = Math.min(1, (now - start) / dur);
      setProgress(p);
      if (p >= 1) {
        goNext();
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, index, atChoices, scene.id, voiceoverEnabled]);

  useEffect(() => {
    const onKey = (e) => {
      // Don't hijack keys while the user is typing in a field (e.g. the lore composer
      // drawer opened over the player) — otherwise Space/Arrows never reach the input.
      const t = e.target;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.code === "Space") {
        e.preventDefault();
        if (!atChoices) setPlaying((p) => !p);
      } else if (e.code === "ArrowRight") {
        goNext();
      } else if (e.code === "ArrowLeft") {
        goPrev();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goNext, goPrev, atChoices]);

  const replay = () => {
    setIndex(0);
    setProgress(0);
    setAtChoices(false);
    setPlaying(true);
  };

  return (
    <div className="player">
      <div className="player-head">
        <div className="crumbs">
          {breadcrumb.map((t, i) => (
            <span key={i} className="crumb">
              {t}
              {i < breadcrumb.length - 1 && <span className="crumb-sep">›</span>}
            </span>
          ))}
        </div>
        <h1 className="scene-title">{scene.title}</h1>
        <p className="scene-logline">{scene.logline}</p>
      </div>

      <div className="stage" style={{ aspectRatio: mediaDimensions.ratio }}>
        <div className="stage-active" key={panel.id}>
          <PanelVisual panel={panel} index={index} playing={playing && !atChoices} videoRef={videoRef} onLayout={handleMediaLayout} />
        </div>

        {panel.audioUrl && <audio key={panel.id} ref={audioRef} src={panel.audioUrl} preload="auto" />}

        {!atChoices && showCaptions && (
          <div className="caption">
            <p>{panel.caption}</p>
          </div>
        )}

        {atChoices && (
          <div className="choices">
            <p className="choices-eyebrow">The path forks</p>
            <div className="choices-row">
              {scene.choices.map((c, i) => (
                <button
                  key={i}
                  className="choice"
                  onClick={() => (c.to ? onChoose(c.to) : null)}
                  disabled={!c.to}
                >
                  <span className="choice-label">{c.label}</span>
                  <span className="choice-arrow">{c.to ? "→" : "the path continues…"}</span>
                </button>
              ))}
            </div>
            <button className="replay-link" onClick={replay}>↺ Replay this scene</button>
          </div>
        )}

        <div className="segs">
          {panels.map((p, i) => (
            <span
              key={p.id}
              className="seg"
              onClick={() => {
                setIndex(i);
                setProgress(0);
                setAtChoices(false);
              }}
            >
              <span
                className="seg-fill"
                style={{ width: i < index ? "100%" : i === index ? `${progress * 100}%` : "0%" }}
              />
            </span>
          ))}
        </div>
      </div>

      <div className="controls">
        <button className="ctrl" onClick={goPrev} aria-label="Previous panel">
          <Icon d={I.prev} stroke />
        </button>
        <button
          className="ctrl ctrl-main"
          onClick={() => (atChoices ? replay() : setPlaying((p) => !p))}
          aria-label={playing ? "Pause" : "Play"}
        >
          <Icon d={atChoices ? I.play : playing ? I.pause : I.play} />
        </button>
        <button className="ctrl" onClick={goNext} aria-label="Next panel">
          <Icon d={I.next} stroke />
        </button>
        <span className="counter">{Math.min(index + 1, panels.length)} / {panels.length}</span>
        {mediaDimensions && mediaDimensions.width > 0 && mediaDimensions.height > 0 && (
          <span
            className={`media-size-badge ${mediaDimensions.isEstimated ? "is-estimated" : ""}`}
            title={mediaDimensions.isEstimated ? "Estimated size" : "Real size read from media"}
          >
            {getMediaSizeLabel(mediaDimensions.width, mediaDimensions.height)}
          </span>
        )}
        <button
          className={`cc ${showCaptions ? "on" : ""}`}
          onClick={() => setShowCaptions((s) => !s)}
          aria-pressed={showCaptions}
        >
          CC
        </button>
        <button
          className={`cc ${voiceoverEnabled ? "on" : ""}`}
          onClick={() => {
            setVoiceoverEnabled((v) => {
              if (v && synthRef.current) {
                synthRef.current.cancel();
              }
              return !v;
            });
          }}
          aria-label={voiceoverEnabled ? "Mute voiceover" : "Unmute voiceover"}
          title="Toggle Voiceover Narration"
          style={{ marginLeft: '8px' }}
        >
          <Icon d={voiceoverEnabled ? I.speaker : I.speakerMute} size="14" />
        </button>
      </div>
    </div>
  );
}

// --- Main exported StorylinePlayer component (loads scene from API or demo) ---
export default function ScenePlayer({ startSceneId }) {
  const api = useApi();
  const [sceneId, setSceneId] = useState(startSceneId);
  const [scene, setScene] = useState(null);
  const [error, setError] = useState(null);
  const [path, setPath] = useState([startSceneId]);
  const [titles, setTitles] = useState({ [startSceneId]: "Start" });

  useEffect(() => {
    let live = true;
    setScene(null);
    setError(null);
    api
      .getScene(sceneId)
      .then((s) => {
        if (!live) return;
        const normalized = normalizeScene(s);
        setScene(normalized);
        setTitles((t) => ({ ...t, [normalized.id]: normalized.title }));
      })
      .catch((err) => {
        console.error("Failed to load scene", err);
        if (live) setError("Could not load this scene.");
      });
    return () => {
      live = false;
    };
  }, [api, sceneId]);

  const choose = (to) => {
    setSceneId(to);
    setPath((p) => [...p, to]);
  };
  const breadcrumb = path.map((id) => titles[id] || id);

  return (
    <div className="player-wrapper">
      {error ? (
        <p className="msg">{error}</p>
      ) : !scene ? (
        <p className="msg">Loading scene…</p>
      ) : (
        <PlayerStage scene={scene} onChoose={choose} breadcrumb={breadcrumb} />
      )}
    </div>
  );
}
