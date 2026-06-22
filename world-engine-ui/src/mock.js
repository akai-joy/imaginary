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

