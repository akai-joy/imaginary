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
};

const Icon = ({ d, stroke }) => (
  <svg
    width="22"
    height="22"
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
function PanelVisual({ panel, index, playing, videoRef }) {
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
      />
    );
  }
  if (panel.imageUrl) {
    return <img className={`stage-media ${kb}`} src={panel.imageUrl} alt={panel.caption} />;
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
  const audioRef = useRef(null);
  const videoRef = useRef(null);

  const panels = scene.panels;
  const panel = panels[index];
  const isLast = index === panels.length - 1;

  useEffect(() => {
    setIndex(0);
    setPlaying(true);
    setAtChoices(false);
    setProgress(0);
  }, [scene.id]);

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

  // playback driver: audio ▸ video ▸ timer
  useEffect(() => {
    if (!playing || atChoices) return;
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
  }, [playing, index, atChoices, scene.id]);

  useEffect(() => {
    const onKey = (e) => {
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

      <div className="stage">
        <div className="stage-active" key={panel.id}>
          <PanelVisual panel={panel} index={index} playing={playing && !atChoices} videoRef={videoRef} />
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
        <button
          className={`cc ${showCaptions ? "on" : ""}`}
          onClick={() => setShowCaptions((s) => !s)}
          aria-pressed={showCaptions}
        >
          CC
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
