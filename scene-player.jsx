import { useState, useEffect, useRef, useCallback } from "react";

/**
 * ScenePlayer — narrated, branching motion-comic player for the explorable graph.
 * Now supports IMAGE or VIDEO panels, and loads scenes from your backend.
 *
 * SCENE SHAPE (what /scenes/:id should return; the backend builds it from your
 * Storyboarding agent's job + the canon node + the cached media URLs):
 *   {
 *     id, title, logline,
 *     panels: [{
 *       id,
 *       prompt,        // "Scene N Prompt" from the storyboard sheet
 *       caption,       // narration text the ElevenLabs VO speaks
 *       imageUrl,      // Imagen still  (used when no videoUrl)
 *       videoUrl,      // Veo clip      (takes precedence; runs muted, VO on top)
 *       audioUrl,      // ElevenLabs VO in Firebase
 *       durationMs,    // fallback timing only (no audio + no video)
 *     }],
 *     choices: [{ label, to }],   // `to` = next scene id (graph edge); null = ending
 *   }
 *
 * TIMING PRIORITY per panel:  audioUrl (VO) ▸ videoUrl (clip) ▸ durationMs (demo timer).
 * Generate image/video + VO once at commit time and cache in Firebase, so play is instant.
 */

// Set to your deployed API base (e.g. import.meta.env.VITE_API_BASE_URL in your Vite app).
// "" => uses the built-in demo graph so this stays runnable with no backend.
const API_BASE = "";

// --- Demo graph: your Eldoria sheet; panel 3 flagged as a video panel ----------
const DEMO = {
  eldoria: {
    id: "eldoria",
    title: "The Warmth of Eldoria",
    logline:
      "A weary traveler finds comfort in the peaceful mountain village of Eldoria — from its steaming hot springs to its cozy tavern hearth.",
    panels: [
      { id: "p1", caption: "At the edge of the white pass, the traveler saw it at last — Eldoria, glowing gold against the dark.",
        prompt: "Wide shot. A weary traveler on a snow-covered mountain path; the golden lights of Eldoria nestle among snowy peaks. Dusk, deep blues and purples." },
      { id: "p2", caption: "The village lay cupped in the valley, steam rising from the springs like breath on the cold air.",
        prompt: "High-angle establishing shot. Eldoria in a snowy valley, rustic cabins, warm windows, thick steam from mineral hot springs. Starry sky." },
      { id: "p3", kind: "video", caption: "He sank into the hot spring, and the journey's ache lifted into the steam and the stars.",
        prompt: "Medium shot. The traveler soaks in a stone hot spring, eyes closed; ethereal steam drifts upward, catching soft light. Brilliant starry sky." },
      { id: "p4", caption: "The tavern door gave way to warmth — light, voices, the smell of something good.",
        prompt: "Low-angle dynamic shot. The traveler pushes open a heavy wooden door into a bustling warm tavern; golden light pours out." },
      { id: "p5", caption: "By the hearth he cradled the mug, and for the first time in weeks, he smiled.",
        prompt: "Medium close-up. The traveler in a plush armchair by a roaring stone hearth, holding a steaming mug, gentle smile, warm firelight." },
      { id: "p6", caption: "Snow fell soft over the sleeping village, and Eldoria kept its quiet, glowing watch.",
        prompt: "POV from inside a cabin looking out a wooden window; soft snow over the sleeping village at night, glowing windows, cool blue tones." },
    ],
    choices: [
      { label: "Stay by the hearth a while longer", to: "hearth" },
      { label: "Set out over the pass at first light", to: "pass" },
    ],
  },
  hearth: {
    id: "hearth", title: "Tales by the Hearth",
    logline: "The fire burns low, and a stranger's story rewrites the traveler's route.",
    panels: [
      { id: "h1", caption: "An old fisher pulled up a stool and began a tale of the lake that never freezes.",
        prompt: "Cozy tavern interior, close on an old fisher telling a story by firelight, attentive faces, warm shadows." },
      { id: "h2", caption: "By the time the fire burned low, he had a map drawn on a napkin — and a reason to stay.",
        prompt: "Close-up of a napkin with a rough ink map, a mug ring staining one corner, a hand resting beside it." },
    ],
    choices: [
      { label: "Follow the napkin map at dawn", to: "pass" },
      { label: "Let Eldoria hold you one more night", to: "eldoria" },
    ],
  },
  pass: {
    id: "pass", title: "Over the Pass",
    logline: "The climb out of the valley opens onto a world the traveler hasn't named yet.",
    panels: [
      { id: "s1", caption: "Dawn broke hard and bright; the pass climbed into a sky scrubbed clean of cloud.",
        prompt: "Wide shot at dawn. A steep snowy pass climbing into a clear bright sky, a small figure ascending." },
      { id: "s2", caption: "At the summit the world fell away on every side — and somewhere below, a new valley waited.",
        prompt: "Summit panorama. The world falls away on every side; far below a new green valley beyond the snowline." },
    ],
    choices: [
      { label: "Descend toward the new valley", to: null },
      { label: "Look back at Eldoria one last time", to: "eldoria" },
    ],
  },
};

// --- Data layer: load a scene from the backend, fall back to demo ---------------
function normalizeScene(raw) {
  return {
    id: raw.id,
    title: raw.title,
    logline: raw.logline,
    panels: (raw.panels || []).map((p) => ({
      id: p.id, prompt: p.prompt, caption: p.caption,
      imageUrl: p.imageUrl ?? null, videoUrl: p.videoUrl ?? null,
      audioUrl: p.audioUrl ?? null, durationMs: p.durationMs ?? 5200,
      kind: p.videoUrl ? "video" : p.kind ?? "image",
    })),
    choices: raw.choices || [],
  };
}

async function loadScene(id) {
  if (!API_BASE) return DEMO[id] || DEMO.eldoria; // demo mode
  const res = await fetch(`${API_BASE}/scenes/${id}`);
  if (!res.ok) throw new Error(`${res.status}`);
  return normalizeScene(await res.json());
}

// --- Icons ---------------------------------------------------------------------
const I = {
  play: <path d="M8 5v14l11-7z" />,
  pause: (<><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></>),
  prev: <path d="M7 6v12M9 12l9 6V6z" />,
  next: <path d="M17 6v12M15 12L6 6v12z" />,
};
const Icon = ({ d, stroke }) => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill={stroke ? "none" : "currentColor"} stroke={stroke ? "currentColor" : "none"} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round">{d}</svg>
);

// --- Visual for a panel: real video, real image, or a styled placeholder -------
function PanelVisual({ panel, index, playing, videoRef }) {
  const kb = `kb-${index % 2 === 0 ? "a" : "b"} ${playing ? "kb-on" : ""}`;
  if (panel.videoUrl) {
    return (
      <video ref={videoRef} className={`stage-media ${kb}`} src={panel.videoUrl}
        muted={Boolean(panel.audioUrl)} playsInline preload="auto" />
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
      <span className="panel-ph-tag">{isVideo ? "Veo clip pending · {videoUrl}" : "image pending · {imageUrl}"}</span>
    </div>
  );
}

// --- Player --------------------------------------------------------------------
function ScenePlayer({ scene, onChoose, breadcrumb }) {
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

  useEffect(() => { setIndex(0); setPlaying(true); setAtChoices(false); setProgress(0); }, [scene.id]);

  const goNext = useCallback(() => {
    setProgress(0);
    if (isLast) { setAtChoices(true); setPlaying(false); }
    else setIndex((i) => i + 1);
  }, [isLast]);

  const goPrev = useCallback(() => { setProgress(0); setAtChoices(false); setIndex((i) => Math.max(0, i - 1)); }, []);

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
      return () => { audio.pause(); if (video) video.pause(); audio.removeEventListener("timeupdate", onTime); audio.removeEventListener("ended", onEnd); };
    }
    if (video) {
      const onTime = () => video.duration && setProgress(video.currentTime / video.duration);
      const onEnd = () => goNext();
      video.addEventListener("timeupdate", onTime);
      video.addEventListener("ended", onEnd);
      return () => { video.pause(); video.removeEventListener("timeupdate", onTime); video.removeEventListener("ended", onEnd); };
    }
    let raf; const start = performance.now() - progress * dur;
    const tick = (now) => { const p = Math.min(1, (now - start) / dur); setProgress(p); if (p >= 1) { goNext(); return; } raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, index, atChoices, scene.id]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.code === "Space") { e.preventDefault(); if (!atChoices) setPlaying((p) => !p); }
      else if (e.code === "ArrowRight") goNext();
      else if (e.code === "ArrowLeft") goPrev();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goNext, goPrev, atChoices]);

  const replay = () => { setIndex(0); setProgress(0); setAtChoices(false); setPlaying(true); };

  return (
    <div className="player">
      <div className="player-head">
        <div className="crumbs">
          {breadcrumb.map((t, i) => (<span key={i} className="crumb">{t}{i < breadcrumb.length - 1 && <span className="crumb-sep">›</span>}</span>))}
        </div>
        <h1 className="scene-title">{scene.title}</h1>
        <p className="scene-logline">{scene.logline}</p>
      </div>

      <div className="stage">
        <div className="stage-active" key={panel.id}>
          <PanelVisual panel={panel} index={index} playing={playing && !atChoices} videoRef={videoRef} />
        </div>

        {panel.audioUrl && <audio key={panel.id} ref={audioRef} src={panel.audioUrl} preload="auto" />}

        {!atChoices && showCaptions && (<div className="caption"><p>{panel.caption}</p></div>)}

        {atChoices && (
          <div className="choices">
            <p className="choices-eyebrow">The path forks</p>
            <div className="choices-row">
              {scene.choices.map((c, i) => (
                <button key={i} className="choice" onClick={() => (c.to ? onChoose(c.to) : null)} disabled={!c.to}>
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
            <span key={p.id} className="seg" onClick={() => { setIndex(i); setProgress(0); setAtChoices(false); }}>
              <span className="seg-fill" style={{ width: i < index ? "100%" : i === index ? `${progress * 100}%` : "0%" }} />
            </span>
          ))}
        </div>
      </div>

      <div className="controls">
        <button className="ctrl" onClick={goPrev} aria-label="Previous panel"><Icon d={I.prev} stroke /></button>
        <button className="ctrl ctrl-main" onClick={() => (atChoices ? replay() : setPlaying((p) => !p))} aria-label={playing ? "Pause" : "Play"}>
          <Icon d={atChoices ? I.play : playing ? I.pause : I.play} />
        </button>
        <button className="ctrl" onClick={goNext} aria-label="Next panel"><Icon d={I.next} stroke /></button>
        <span className="counter">{Math.min(index + 1, panels.length)} / {panels.length}</span>
        <button className={`cc ${showCaptions ? "on" : ""}`} onClick={() => setShowCaptions((s) => !s)} aria-pressed={showCaptions}>CC</button>
      </div>
    </div>
  );
}

// --- App: graph traversal + scene loading --------------------------------------
export default function App() {
  const [sceneId, setSceneId] = useState("eldoria");
  const [scene, setScene] = useState(null);
  const [error, setError] = useState(null);
  const [path, setPath] = useState(["eldoria"]);
  const [titles, setTitles] = useState({ eldoria: "The Warmth of Eldoria" });

  useEffect(() => {
    let live = true;
    setScene(null); setError(null);
    loadScene(sceneId)
      .then((s) => { if (!live) return; setScene(s); setTitles((t) => ({ ...t, [s.id]: s.title })); })
      .catch(() => live && setError("Could not load this scene."));
    return () => { live = false; };
  }, [sceneId]);

  const choose = (to) => { setSceneId(to); setPath((p) => [...p, to]); };
  const breadcrumb = path.map((id) => titles[id] || id);

  return (
    <div className="root">
      <style>{CSS}</style>
      {error ? <p className="msg">{error}</p>
        : !scene ? <p className="msg">Loading scene…</p>
        : <ScenePlayer scene={scene} onChoose={choose} breadcrumb={breadcrumb} />}
    </div>
  );
}

const CSS = `
.root{ --paper:#e9ece4; --surface:#f7f8f4; --ink:#1b1c20; --ink-soft:#5b5d64; --line:#d3d8cd;
  --plum:#6d1f3c; --plum-deep:#511329; --ochre:#a9781f; --stage:#13141a;
  --serif:'Hoefler Text','Iowan Old Style',Palatino,Georgia,serif;
  --sans:system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,'SF Mono',Menlo,Consolas,monospace;
  font-family:var(--sans); color:var(--ink); background:var(--paper); min-height:100%; padding:26px; display:flex; justify-content:center; }
.msg{ color:var(--ink-soft); font-family:var(--mono); padding:60px; }
.player{ width:100%; max-width:720px; }
.player-head{ margin-bottom:14px; }
.crumbs{ font-family:var(--mono); font-size:11px; color:var(--ink-soft); margin-bottom:10px; }
.crumb-sep{ margin:0 7px; opacity:.5; }
.scene-title{ font-family:var(--serif); font-size:28px; font-weight:600; margin:0 0 4px; }
.scene-logline{ color:var(--ink-soft); margin:0; max-width:60ch; font-size:14px; }

.stage{ position:relative; aspect-ratio:16/10; background:var(--stage); border:1px solid var(--line); border-radius:6px; overflow:hidden; box-shadow:0 8px 30px rgba(20,21,26,.16); }
.stage-active{ position:absolute; inset:0; animation:fade .5s ease; }
@keyframes fade{ from{opacity:0} to{opacity:1} }
.stage-media{ width:100%; height:100%; object-fit:cover; display:block; }

.panel-ph{ position:absolute; inset:0; display:flex; flex-direction:column; justify-content:center; gap:14px; padding:34px; overflow:hidden;
  background:radial-gradient(120% 80% at 70% 10%, #20222c 0%, #14151b 60%, #0f1015 100%); }
.panel-ph-no{ font-family:var(--mono); font-size:12px; letter-spacing:.1em; text-transform:uppercase; color:#7f8493; }
.panel-ph-prompt{ font-family:var(--serif); font-size:19px; line-height:1.5; color:#e8e9ee; margin:0; max-width:46ch; }
.panel-ph-tag{ font-family:var(--mono); font-size:11px; color:#5b6070; }
.panel-ph-video .panel-ph-tag{ color:var(--ochre); }
.veo-shimmer{ position:absolute; inset:0; background:linear-gradient(110deg, transparent 30%, rgba(169,120,31,.16) 50%, transparent 70%); background-size:220% 100%; animation:shim 2.6s linear infinite; }
@keyframes shim{ from{background-position:200% 0} to{background-position:-20% 0} }

.kb-on.kb-a{ animation:kbA 6s ease-out forwards; }
.kb-on.kb-b{ animation:kbB 6s ease-out forwards; }
@keyframes kbA{ from{ transform:scale(1.02) translate(0,0);} to{ transform:scale(1.1) translate(-2%,-2%);} }
@keyframes kbB{ from{ transform:scale(1.1) translate(2%,1%);} to{ transform:scale(1.02) translate(0,0);} }

.caption{ position:absolute; left:0; right:0; bottom:16px; display:flex; justify-content:center; padding:0 22px; pointer-events:none; }
.caption p{ margin:0; max-width:54ch; text-align:center; color:#f3f1ea; font-family:var(--serif); font-size:17px; line-height:1.45;
  background:linear-gradient(transparent, rgba(10,11,15,.5) 40%); text-shadow:0 1px 10px rgba(0,0,0,.7); padding:10px 16px; }

.choices{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:18px; padding:28px; background:rgba(15,16,21,.86); backdrop-filter:blur(3px); }
.choices-eyebrow{ font-family:var(--mono); font-size:12px; letter-spacing:.14em; text-transform:uppercase; color:#a7a2ad; margin:0; }
.choices-row{ display:flex; flex-direction:column; gap:12px; width:100%; max-width:440px; }
.choice{ display:flex; align-items:center; justify-content:space-between; gap:16px; text-align:left; background:#f7f8f4; border:1px solid #f7f8f4; border-radius:5px; padding:14px 18px; cursor:pointer; transition:transform .12s, box-shadow .12s; }
.choice:hover:not(:disabled){ transform:translateY(-1px); box-shadow:0 6px 18px rgba(0,0,0,.3); }
.choice:disabled{ opacity:.7; cursor:default; }
.choice-label{ font-family:var(--serif); font-size:16px; color:var(--ink); }
.choice-arrow{ font-family:var(--mono); font-size:12px; color:var(--plum); white-space:nowrap; }
.replay-link{ background:none; border:none; color:#cfd2da; font-family:var(--mono); font-size:12px; cursor:pointer; }
.replay-link:hover{ color:#fff; }

.segs{ position:absolute; top:12px; left:14px; right:14px; display:flex; gap:5px; }
.seg{ flex:1; height:3px; background:rgba(255,255,255,.22); border-radius:2px; overflow:hidden; cursor:pointer; }
.seg-fill{ display:block; height:100%; background:#f0ede4; transition:width .1s linear; }

.controls{ display:flex; align-items:center; gap:10px; margin-top:14px; }
.ctrl{ display:grid; place-items:center; width:40px; height:40px; border-radius:50%; border:1px solid var(--line); background:var(--surface); color:var(--ink); cursor:pointer; }
.ctrl:hover{ border-color:var(--ink-soft); }
.ctrl-main{ width:52px; height:52px; background:var(--plum); border-color:var(--plum); color:#fff; }
.ctrl-main:hover{ background:var(--plum-deep); }
.counter{ font-family:var(--mono); font-size:13px; color:var(--ink-soft); margin-left:6px; }
.cc{ margin-left:auto; font-family:var(--mono); font-size:12px; letter-spacing:.06em; padding:6px 10px; border-radius:4px; border:1px solid var(--line); background:var(--surface); color:var(--ink-soft); cursor:pointer; }
.cc.on{ color:var(--plum); border-color:color-mix(in srgb,var(--plum) 35%,transparent); }

@media (prefers-reduced-motion: reduce){ .kb-on{ animation:none !important; } .veo-shimmer{ animation:none; } .stage-active{ animation:none; } }
@media (max-width:560px){ .scene-title{ font-size:23px; } .panel-ph-prompt{ font-size:16px; } .caption p{ font-size:15px; } }
`;
