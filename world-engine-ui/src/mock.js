// Demo data so the UI is fully clickable with no backend.
// Shapes mirror the API contract documented in README.md.

export const mockStorylines = [
  {
    tree_id: 'tre_ember',
    title: 'The Ember Accord',
    summary: 'A fragile truce between the Ashwrights and the river-clans, sworn in cooled slag and smoke.',
    type: 'plot',
    member_count: 9,
    vote_total: 142,
    composite_score: 88,
    version: 4,
    voted: false,
    derived_from: null,
    nodes: [
      { id: 'cn_a1f', type: 'faction', title: 'The Ashwrights', contributor: 'mara', version: 2, derived_from: [],
        body: 'Smiths who bind every oath into a poured ingot. Break the word, and the metal is melted before the clan.' },
      { id: 'cn_b2c', type: 'character', title: 'Sorrel of the Low Fords', contributor: 'idris', version: 1, derived_from: ['cn_a1f'],
        body: 'A river-clan envoy carrying a borrowed name and a real grievance. Negotiates the Accord against her own people’s wishes.' },
      { id: 'cn_c3d', type: 'location', title: 'The Slag Court', contributor: 'mara', version: 1, derived_from: ['cn_a1f'],
        body: 'Where oaths are poured. A cooling floor of black glass that rings when walked.' },
      { id: 'cn_d4e', type: 'plot', title: 'The First Pour', contributor: 'idris', version: 3, derived_from: ['cn_b2c', 'cn_c3d'],
        body: 'Sorrel and the Ashwright matriarch pour a shared oath — and someone has salted the metal so it will crack.' },
    ],
  },
  {
    tree_id: 'tre_tide',
    title: 'Salt in the Archive',
    summary: 'A drowned library surfaces once a generation, and the records it carries rewrite who owns the coast.',
    type: 'lore',
    member_count: 6,
    vote_total: 97,
    composite_score: 81,
    version: 2,
    voted: false,
    derived_from: 'tre_ember',
    nodes: [
      { id: 'cn_e5f', type: 'location', title: 'The Tideward Archive', contributor: 'noor', version: 2, derived_from: ['cn_c3d'],
        body: 'A library that sinks and rises with a century-long tide. Its ledgers are law when they are dry.' },
      { id: 'cn_f6a', type: 'character', title: 'Keeper Vol', contributor: 'theo', version: 1, derived_from: ['cn_e5f'],
        body: 'The only one who can read the salt-stained ledgers, and the only one with reason to forge them.' },
    ],
  },
  {
    tree_id: 'tre_lantern',
    title: 'The Lantern That Owes',
    summary: 'A debt-spirit bound into a streetlamp pays back every favour — at compounding, ruinous interest.',
    type: 'character',
    member_count: 4,
    vote_total: 64,
    composite_score: 76,
    version: 1,
    voted: false,
    derived_from: null,
    nodes: [
      { id: 'cn_g7b', type: 'character', title: 'The Lantern', contributor: 'pia', version: 1, derived_from: [],
        body: 'It remembers every kindness done beneath it and insists on repaying, whether you want it to or not.' },
      { id: 'cn_h8c', type: 'plot', title: 'A Small Mercy', contributor: 'pia', version: 1, derived_from: ['cn_g7b'],
        body: 'A child shares bread under the Lantern. By morning the whole street owes a debt none of them can name.' },
    ],
  },
]

export const mockShowcase = [
  {
    id: 'mda_ember_comic',
    tree_id: 'tre_ember',
    kind: 'comic',
    title: 'The Ember Accord',
    caption: 'The First Pour — and the salt that cracks it. (AI-generated)',
    hashtags: ['#worldengine', '#emberaccord'],
    contributor_ids: ['mara', 'idris'],
    gcs_url: null,
    panels: [
      'The Slag Court, black glass underfoot, two clans facing across the floor.',
      'Sorrel lifts the ladle; the matriarch lays in her oath-token.',
      'The metal hisses — a fault line of salt blooms white.',
      'Silence, then the long crack. The Accord breaks before it sets.',
    ],
  },
  {
    id: 'mda_tide_reel',
    tree_id: 'tre_tide',
    kind: 'reel',
    title: 'Salt in the Archive',
    caption: 'The Tideward Archive surfaces. Keeper Vol opens a dry ledger. (AI-generated)',
    hashtags: ['#worldengine', '#saltarchive'],
    contributor_ids: ['noor', 'theo'],
    gcs_url: null,
    scenes: ['The tide pulls back.', 'Stone shelves break the surface.', 'A ledger, dry for the first time in a century.'],
  },
]

// --- Living World: world / map / codex / canon (mirrors the additive REST surface) ---

export const mockWorld = {
  id: 'world_genesis',
  theme: 'Medieval Wizards',
  opening_line:
    'The last spell in the world guttered out at dusk, and every wizard who felt it die began to run.',
  art_style_directive:
    'Painterly high-fantasy storybook illustration; candlelit medieval palette; ink-and-watercolor linework.',
  // Populated by the Atlas agent once locations are painted; null in offline demo.
  map_image_url: '/map_background.jpg',
  status: 'active',
  // ~5 days of contribution window left — scarcity is the event energy.
  closes_at: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000 + 14 * 60 * 60 * 1000).toISOString(),
}

// Locations placed by the Cartographer on a 0–100 plane. `discovered` is per-user fog state.
export const mockMap = {
  world: mockWorld,
  regions: ['The Emberlands', 'The Drowned Coast', 'The Hollow North'],
  locations: [
    { id: 'cn_c3d', title: 'The Slag Court', region: 'The Emberlands', x: 38, y: 58,
      near: ['cn_a1f'], discovered: true, contributor_id: 'mara' },
    { id: 'cn_a1f', title: 'Forge of the Ashwrights', region: 'The Emberlands', x: 52, y: 66,
      near: ['cn_c3d'], discovered: true, contributor_id: 'mara' },
    { id: 'cn_e5f', title: 'The Tideward Archive', region: 'The Drowned Coast', x: 24, y: 30,
      near: ['cn_c3d'], discovered: true, contributor_id: 'noor' },
    { id: 'cn_eld', title: 'Eldoria', region: 'The Hollow North', x: 72, y: 22,
      near: [], discovered: true, contributor_id: 'pia' },
    { id: 'cn_pass', title: 'The White Pass', region: 'The Hollow North', x: 84, y: 38,
      near: ['cn_eld'], discovered: false, contributor_id: 'theo' },
    { id: 'cn_lamp', title: 'Lantern Row', region: 'The Drowned Coast', x: 18, y: 52,
      near: ['cn_e5f'], discovered: false, contributor_id: 'pia' },
    { id: 'cn_void', title: 'The Unspelled Waste', region: 'The Emberlands', x: 60, y: 86,
      near: ['cn_a1f'], discovered: false, contributor_id: 'idris' },
  ],
}

export const mockCodex = {
  characters: [
    { id: 'cn_b2c', title: 'Sorrel of the Low Fords', contributor_id: 'idris', discovered: true,
      body: 'A river-clan envoy carrying a borrowed name and a real grievance.' },
    { id: 'cn_f6a', title: 'Keeper Vol', contributor_id: 'theo', discovered: true,
      body: 'The only one who can read the salt-stained ledgers — and the only one with reason to forge them.' },
    { id: 'cn_g7b', title: 'The Lantern', contributor_id: 'pia', discovered: false,
      body: 'A debt-spirit bound into a streetlamp. It repays every kindness, at ruinous interest.' },
  ],
  beasts: [
    { id: 'cn_drk', title: 'The Slagmaw Drake', contributor_id: 'mara', discovered: true,
      body: 'It nests in cooling iron and swallows oaths whole; its breath sets poured metal cracking.' },
    { id: 'cn_tide', title: 'The Ledger Eel', contributor_id: 'noor', discovered: false,
      body: 'A century-long creature that surfaces only with the Archive, rewriting what it reads.' },
  ],
  spells: [
    { id: 'cn_emb', title: 'The Last Ember', contributor_id: 'mara', discovered: true,
      body: 'The dying spell every wizard felt go out. To cast it again is to be hunted.' },
    { id: 'cn_salt', title: 'Salt the Pour', contributor_id: 'idris', discovered: false,
      body: 'A saboteur’s working that seeds a fault into any oath sworn in metal.' },
  ],
}

const TYPE_BY_ID = {
  cn_c3d: 'location', cn_a1f: 'location', cn_e5f: 'location', cn_eld: 'location',
  cn_pass: 'location', cn_lamp: 'location', cn_void: 'location',
  cn_b2c: 'character', cn_f6a: 'character', cn_g7b: 'character',
  cn_drk: 'beast', cn_tide: 'beast', cn_emb: 'spell', cn_salt: 'spell',
}

// Detail records returned by GET /canon/:id. Falls back to a synthesized record below.
export const mockCanon = {
  cn_c3d: {
    id: 'cn_c3d', type: 'location', title: 'The Slag Court', contributor_id: 'mara', version: 1,
    body: 'Where oaths are poured. A cooling floor of black glass that rings when walked.',
    map_meta: { x: 38, y: 58, region: 'The Emberlands', near: ['cn_a1f'] },
    references: [{ id: 'cn_a1f', title: 'Forge of the Ashwrights', type: 'location' }],
    referenced_by: [
      { id: 'cn_b2c', title: 'Sorrel of the Low Fords', type: 'character' },
      { id: 'cn_drk', title: 'The Slagmaw Drake', type: 'beast' },
    ],
    storylines: ['tre_ember'],
  },
  cn_eld: {
    id: 'cn_eld', type: 'location', title: 'Eldoria', contributor_id: 'pia', version: 2,
    body: 'A village cupped in a snowy valley, steam rising from its springs like breath on the cold air.',
    map_meta: { x: 72, y: 22, region: 'The Hollow North', near: [] },
    references: [],
    referenced_by: [{ id: 'cn_f6a', title: 'Keeper Vol', type: 'character' }],
    storylines: ['tre_tide'],
  },
}

export function buildCanonFallback(id) {
  const fromMap = mockMap.locations.find((l) => l.id === id)
  if (fromMap) {
    return {
      id, type: 'location', title: fromMap.title, contributor_id: fromMap.contributor_id, version: 1,
      body: 'Uncharted lore. Be the first to write what is found here.',
      map_meta: { x: fromMap.x, y: fromMap.y, region: fromMap.region, near: fromMap.near },
      references: [], referenced_by: [], storylines: [],
    }
  }
  for (const kind of ['characters', 'beasts', 'spells']) {
    const e = mockCodex[kind].find((x) => x.id === id)
    if (e) {
      return {
        id, type: TYPE_BY_ID[id] || 'lore', title: e.title, contributor_id: e.contributor_id,
        version: 1, body: e.body, map_meta: null, references: [], referenced_by: [], storylines: [],
      }
    }
  }
  return null
}

export const DEMO = {
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
      { id: "p3", kind: "video", caption: "She sank into the hot spring, and the journey's ache lifted into the steam and the stars.",
        prompt: "Medium shot. The traveler soaks in a stone hot spring, eyes closed; ethereal steam drifts upward, catching soft light. Brilliant starry sky." },
      { id: "p4", caption: "The tavern door gave way to warmth — light, voices, the smell of something good.",
        prompt: "Low-angle dynamic shot. The traveler pushes open a heavy wooden door into a bustling warm tavern; golden light pours out." },
      { id: "p5", caption: "By the hearth she cradled the mug, and for the first time in weeks, she smiled.",
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
      { id: "h2", caption: "By the time the fire burned low, she had a map drawn on a napkin — and a reason to stay.",
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
}

