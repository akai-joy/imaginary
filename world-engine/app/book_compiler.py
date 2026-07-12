# Copyright 2026 akai-joy
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Season-Finale Book Compiler — renders a drop into a single-file HTML anthology.

When a themed drop closes, the world becomes a read-only collectible. This module
binds that collectible into a *book*: one self-contained `.html` folio — dark
leather cover, vellum interior pages, print-to-PDF ready — containing the cover,
a foreword of season statistics, every storyline tree as an ordered chapter
(ranked by votes, the prime timeline first), the codex as an appendix, the
agent-painted atlas plate, and a colophon crediting every contributor.

Design (and why it matters):

* **Deterministic and read-only by construction.** No LLM is invoked and nothing
  is written to canon. The compiler only *arranges* what the crowd wrote and the
  controller accepted — the AI stays the referee, never the author, all the way
  into the finished book.
* **Built on the same read path as the MCP server.** It walks `CanonStore` +
  `assemble_trees` (the identical lineage walk the showcase pipeline and REST
  layer use), so the book can never drift from the canonical story.
* **Self-contained artifact.** Local atlas imagery (`gcs_mock/…`) is embedded as
  data URIs; remote showcase media is deliberately not fetched so compilation is
  offline and reproducible. The file needs no server to be read, shared, or
  printed.

Run it:

    uv run python -m app.book_compiler                 # active world -> books/
    uv run python -m app.book_compiler --world <id> --out my_book.html
"""

import argparse
import base64
import html
from datetime import UTC, datetime
from pathlib import Path

from app.agents.showcase_tally import assemble_trees
from app.core.store import CanonStore, get_store
from app.core.types import CanonEntry, WorldStatus

# Embedding cap: a keepsake should stay portable. Local images above this size are
# referenced by caption only instead of inlined as base64.
MAX_EMBED_BYTES = 10 * 1024 * 1024

# Codex appendix sections, in book order. Every canon type gets a home so no
# accepted entry is ever left out of the anthology.
CODEX_SECTIONS: list[tuple[str, str, str]] = [
    ("character", "Dramatis Personae", "❖"),
    ("beast", "Bestiary", "⟡"),
    ("spell", "Grimoire", "✧"),
    ("location", "Gazetteer", "⌖"),
    ("faction", "Orders & Factions", "⚑"),
    ("plot", "Chronicle of Deeds", "✦"),
    ("lore", "Lore & Fragments", "✒"),
    ("other", "Miscellany", "·"),
]

_ROMAN = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
    (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]


def _roman(n: int) -> str:
    out = []
    for value, numeral in _ROMAN:
        while n >= value:
            out.append(numeral)
            n -= value
    return "".join(out) or "I"


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _naive_utc(dt: datetime | None) -> datetime | None:
    """Normalize to naive UTC so seed dates (utcnow, naive) compare against aware
    timestamps without raising — mirrors the MCP/REST layers' handling."""
    if dt is None:
        return None
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def _paragraphs(body: str) -> str:
    """User text -> escaped <p> blocks (blank lines split paragraphs)."""
    parts = [p.strip() for p in body.replace("\r\n", "\n").split("\n\n")]
    return "".join(
        f"<p>{_esc(p)}</p>" for p in parts if p
    ) or f"<p>{_esc(body)}</p>"


def _local_asset_data_uri(url: str | None) -> str | None:
    """Resolve a `gcs_mock/…` media URL to an embeddable data URI.

    Only local mock-bucket files are embedded (remote GCS URLs would make the
    compile non-deterministic and require the network). Returns None when the
    file is missing, oversized, or the URL is not a local mock asset.
    """
    if not url or "gcs_mock/" not in url:
        return None
    rel = url.split("gcs_mock/", 1)[1]
    if not rel or ".." in rel:
        return None
    for base in (Path("gcs_mock"), Path(__file__).resolve().parents[1] / "gcs_mock"):
        path = base / rel
        if path.is_file():
            suffix = path.suffix.lower().lstrip(".")
            if suffix not in {"png", "jpg", "jpeg", "webp", "gif"}:
                return None
            if path.stat().st_size > MAX_EMBED_BYTES:
                return None
            mime = "image/jpeg" if suffix == "jpg" else f"image/{suffix}"
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            return f"data:{mime};base64,{data}"
    return None


# ---------------------------------------------------------------------------
# Assembly (deterministic, no LLM, no side effects)
# ---------------------------------------------------------------------------
def _assemble_book_trees(
    store: CanonStore, entries: list[CanonEntry]
) -> tuple[list[dict], set[str]]:
    """Assemble storyline trees into chapter dicts, ranked for the book.

    Chapters are trees that actually *grew* (>= 2 members) — a story someone
    continued. Singleton entries remain codex material. Returns the ranked
    chapter list and the set of entry ids that made it into chapters.
    """
    by_id = {e.id: e for e in entries}
    chapters: list[dict] = []
    chaptered_ids: set[str] = set()

    for root_id, member_ids in assemble_trees(entries):
        if len(member_ids) < 2:
            continue
        root = by_id.get(root_id)
        if root is None:
            continue
        members = [by_id[m] for m in member_ids if m in by_id]
        # Chronological order == narrative reading order (the fold is appended
        # over time) — same rule as the MCP server's get_story.
        members.sort(key=lambda e: _naive_utc(e.created_at) or datetime.min)
        votes = store.get_votes_for_tree(root_id)
        chapters.append(
            {
                "tree_id": root_id,
                "title": root.title,
                "opening": root.body,
                "members": members,
                "vote_total": int(sum(v.weight for v in votes)),
            }
        )
        chaptered_ids.update(m.id for m in members)

    chapters.sort(
        key=lambda c: (-c["vote_total"], -len(c["members"]), c["title"].lower())
    )
    return chapters, chaptered_ids


def _render_chapter(index: int, chapter: dict, by_id: dict[str, CanonEntry]) -> str:
    crowned = index == 0 and chapter["vote_total"] > 0
    badge = (
        f'<p class="crown">✦ The Prime Timeline — crowned by '
        f'{chapter["vote_total"]} votes</p>'
        if crowned
        else (
            f'<p class="crown alt">{chapter["vote_total"]} votes</p>'
            if chapter["vote_total"]
            else ""
        )
    )

    sections = []
    previous_id: str | None = None
    for i, entry in enumerate(chapter["members"]):
        byline = f'<span class="byline">inscribed by {_esc(entry.contributor_id)}</span>'
        marks = [f'<span class="kind">{_esc(entry.type.value)}</span>']
        # A visible fork: this passage builds on an earlier passage, not the one
        # directly above it — the reader should see the timeline branch.
        if entry.derived_from and previous_id not in entry.derived_from:
            parents = ", ".join(
                _esc(by_id[p].title) for p in entry.derived_from if p in by_id
            )
            if parents:
                marks.append(f'<span class="fork">⑂ forks from “{parents}”</span>')
        if entry.references:
            refs = ", ".join(
                _esc(by_id[r].title) for r in entry.references if r in by_id
            )
            if refs:
                marks.append(f'<span class="refs">featuring {refs}</span>')
        body_class = "passage dropcap" if i == 0 else "passage"
        sections.append(
            f'<section class="{body_class}">'
            f"<h3>{_esc(entry.title)}</h3>"
            f'<div class="meta">{byline} {" ".join(marks)}</div>'
            f"{_paragraphs(entry.body)}"
            f"</section>"
        )
        previous_id = entry.id

    return (
        f'<article class="page chapter">'
        f'<div class="chapter-no">Chapter {_roman(index + 1)}</div>'
        f"<h2>{_esc(chapter['title'])}</h2>"
        f"{badge}"
        f"{''.join(sections)}"
        f'<div class="fleuron">✦ ✦ ✦</div>'
        f"</article>"
    )


def _render_codex(entries: list[CanonEntry]) -> str:
    grouped: dict[str, list[CanonEntry]] = {}
    for e in entries:
        grouped.setdefault(e.type.value, []).append(e)

    blocks = []
    for kind, heading, glyph in CODEX_SECTIONS:
        kind_entries = grouped.get(kind)
        if not kind_entries:
            continue
        kind_entries.sort(key=lambda e: e.title.lower())
        cards = "".join(
            f'<div class="card"><h4>{glyph} {_esc(e.title)}</h4>'
            f'<div class="meta"><span class="byline">by {_esc(e.contributor_id)}'
            f"</span>"
            + (
                f'<span class="refs"> · {_esc(e.map_meta.region)}</span>'
                if e.map_meta and e.map_meta.region
                else ""
            )
            + f"</div>{_paragraphs(e.body)}</div>"
            for e in kind_entries
        )
        blocks.append(
            f'<section class="codex-kind"><h3>{heading}</h3>'
            f'<div class="cards">{cards}</div></section>'
        )

    if not blocks:
        return ""
    return (
        '<article class="page codex"><div class="chapter-no">Appendix</div>'
        "<h2>The Codex</h2>"
        '<p class="lede">The world bible — every soul, beast, spell, and place '
        "the crowd wrote into canon.</p>" + "".join(blocks) + "</article>"
    )


def _render_colophon(
    entries: list[CanonEntry], chapters: list[dict], generated_at: datetime
) -> str:
    tally: dict[str, int] = {}
    for e in entries:
        tally[e.contributor_id] = tally.get(e.contributor_id, 0) + 1
    rows = "".join(
        f"<tr><td>{_esc(name)}</td><td>{count}</td></tr>"
        for name, count in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    total_votes = sum(c["vote_total"] for c in chapters)
    return (
        '<article class="page colophon"><div class="chapter-no">Colophon</div>'
        "<h2>Credits</h2>"
        '<table class="credits"><thead><tr><th>Contributor</th>'
        "<th>Canon entries</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        f'<p class="lede">{len(tally)} contributors · {len(entries)} canon entries'
        f" · {total_votes} votes cast on storylines.</p>"
        '<p class="oath">This folio was compiled deterministically from canon on '
        f"{generated_at.strftime('%B %d, %Y')}. Every word within was written by a "
        "human hand; the agents only kept the gates — moderating, checking "
        "continuity, tracing provenance — so the world could stay open. "
        "The referee, never the author.</p>"
        '<div class="fleuron">✦</div></article>'
    )


# ---------------------------------------------------------------------------
# The folio template
# ---------------------------------------------------------------------------
_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@500;600;700&family=Spectral:ital,wght@0,300;0,400;0,500;0,600;1,400;1,500&display=swap');
:root {
  --desk: #0d0c0a; --leather: #171009; --leather-2: #241708;
  --vellum: #f1e7d0; --vellum-2: #e9dcbe; --ink: #241c10; --ink-soft: #6d5f45;
  --oxblood: #7d2d3d; --gold: #8a6a1f; --foil: #d3ab3c; --line: #cbb98f;
  --display: 'Cinzel', 'Hoefler Text', Georgia, serif;
  --serif: 'Spectral', 'Iowan Old Style', Palatino, Georgia, serif;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background:
    radial-gradient(120% 90% at 50% -10%, rgba(211,171,60,.10) 0%, transparent 42%),
    radial-gradient(100% 120% at 50% 120%, rgba(205,89,112,.07) 0%, transparent 50%),
    var(--desk);
  font-family: var(--serif); color: var(--ink);
  padding: 48px 16px 96px;
}
.folio { max-width: 780px; margin: 0 auto; display: grid; gap: 28px; }
.page {
  background: linear-gradient(160deg, var(--vellum) 0%, var(--vellum-2) 100%);
  border: 1px solid var(--line); border-radius: 3px;
  box-shadow: 0 2px 6px rgba(0,0,0,.55), 0 24px 60px rgba(0,0,0,.5),
    inset 0 0 90px rgba(122,95,52,.14);
  padding: 64px 72px;
}
/* ---- cover ---- */
.page.cover {
  background: linear-gradient(150deg, var(--leather-2) 0%, var(--leather) 55%, #0e0905 100%);
  color: #e8dcc0; text-align: center; padding: 96px 64px;
  outline: 1px solid rgba(211,171,60,.45); outline-offset: -14px;
  box-shadow: 0 2px 6px rgba(0,0,0,.65), 0 30px 70px rgba(0,0,0,.6),
    inset 0 0 120px rgba(0,0,0,.55);
}
.cover .kicker, .cover .edition {
  font-family: var(--display); font-size: 12px; letter-spacing: .34em;
  text-transform: uppercase; color: rgba(211,171,60,.85);
}
.cover h1 {
  font-family: var(--display); font-weight: 600; font-size: 46px;
  letter-spacing: .06em; margin: 26px 0 8px; color: var(--foil);
  text-shadow: 0 0 22px rgba(211,171,60,.35);
}
.cover .rule { color: rgba(211,171,60,.7); letter-spacing: .6em; margin: 22px 0; }
.cover .opening {
  font-style: italic; font-size: 19px; line-height: 1.7; max-width: 30em;
  margin: 0 auto 30px; color: #efe2c4;
}
.cover .edition { margin-top: 34px; }
.cover .window { margin-top: 10px; font-size: 13px; color: rgba(232,220,192,.55); }
/* ---- interior ---- */
.chapter-no {
  font-family: var(--display); font-size: 12px; letter-spacing: .3em;
  text-transform: uppercase; color: var(--gold); margin-bottom: 10px;
}
.page h2 {
  font-family: var(--display); font-weight: 600; font-size: 30px;
  letter-spacing: .02em; margin-bottom: 6px; color: var(--ink);
}
.crown { font-size: 13px; color: var(--oxblood); font-weight: 600; margin: 4px 0 6px; }
.crown.alt { color: var(--ink-soft); font-weight: 400; }
.lede { color: var(--ink-soft); font-size: 15px; margin: 6px 0 18px; }
.passage { margin-top: 30px; }
.passage h3 { font-family: var(--display); font-weight: 600; font-size: 19px; }
.meta { font-size: 12.5px; color: var(--ink-soft); margin: 3px 0 12px; }
.meta .byline { font-variant: small-caps; letter-spacing: .05em; }
.meta .kind { color: var(--gold); text-transform: uppercase; font-size: 11px; letter-spacing: .12em; margin-left: 8px; }
.meta .fork { color: var(--oxblood); margin-left: 8px; }
.meta .refs { font-style: italic; margin-left: 8px; }
.passage p { line-height: 1.75; font-size: 16.5px; margin-bottom: 12px; }
.passage.dropcap > p:first-of-type::first-letter {
  font-family: var(--display); font-size: 52px; line-height: .85;
  float: left; padding: 6px 10px 0 0; color: var(--oxblood);
}
.fleuron { text-align: center; color: var(--gold); letter-spacing: .8em; margin-top: 40px; }
/* ---- foreword stats ---- */
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 22px 0; }
.stat { border: 1px solid var(--line); border-radius: 3px; padding: 12px 14px; }
.stat b { font-family: var(--display); font-size: 22px; display: block; color: var(--oxblood); }
.stat span { font-size: 11.5px; letter-spacing: .1em; text-transform: uppercase; color: var(--ink-soft); }
/* ---- codex ---- */
.codex-kind { margin-top: 34px; }
.codex-kind h3 {
  font-family: var(--display); font-size: 16px; letter-spacing: .18em;
  text-transform: uppercase; color: var(--gold);
  border-bottom: 1px solid var(--line); padding-bottom: 6px; margin-bottom: 14px;
}
.cards { columns: 2; column-gap: 22px; }
.card { break-inside: avoid; margin-bottom: 18px; }
.card h4 { font-family: var(--display); font-size: 15px; }
.card p { font-size: 13.5px; line-height: 1.6; color: #3a3120; }
/* ---- atlas ---- */
.page.atlas { padding: 34px; }
.page.atlas img { width: 100%; display: block; border: 1px solid var(--line); }
.page.atlas figcaption { font-size: 12.5px; color: var(--ink-soft); text-align: center; padding: 12px 8px 2px; font-style: italic; }
/* ---- colophon ---- */
.credits { width: 100%; border-collapse: collapse; margin: 18px 0; }
.credits th, .credits td { text-align: left; padding: 7px 4px; border-bottom: 1px solid var(--line); font-size: 14.5px; }
.credits th { font-family: var(--display); font-size: 12px; letter-spacing: .14em; text-transform: uppercase; color: var(--gold); }
.oath { margin-top: 20px; font-style: italic; line-height: 1.75; color: #4a3f2a; }
/* ---- print: pure pages, no desk ---- */
@media print {
  body { background: none; padding: 0; }
  .folio { max-width: none; gap: 0; }
  .page { box-shadow: none; border: none; border-radius: 0; page-break-after: always; }
  .page.cover { print-color-adjust: exact; -webkit-print-color-adjust: exact; }
}
@media (max-width: 640px) {
  .page { padding: 36px 24px; }
  .stats, .cards { grid-template-columns: 1fr; columns: 1; }
}
"""


def compile_book(world_id: str | None = None, store: CanonStore | None = None) -> str:
    """Render one world into a complete, self-contained HTML anthology string."""
    store = store or get_store()
    world = store.get_world(world_id) if world_id else store.get_active_world()
    if world is None:
        raise ValueError(
            f"No world found ({world_id!r})" if world_id else "No active world."
        )

    entries = store.list_canon_entries(world.id)
    by_id = {e.id: e for e in entries}
    chapters, chaptered_ids = _assemble_book_trees(store, entries)
    contributors = {e.contributor_id for e in entries}
    generated_at = datetime.now(UTC)
    archived = world.status == WorldStatus.ARCHIVED

    edition = "Season Finale Edition" if archived else "Working Draft — window still open"
    opens = _naive_utc(world.opens_at)
    closes = _naive_utc(world.closes_at)
    window = (
        f"{opens.strftime('%B %d, %Y')} — "
        + (closes.strftime("%B %d, %Y") if closes else "the closing of the gate")
        if opens
        else ""
    )

    cover = (
        '<article class="page cover">'
        '<div class="kicker">World Engine · A Season Anthology</div>'
        f"<h1>{_esc(world.theme)}</h1>"
        '<div class="rule">✦ ✦ ✦</div>'
        f'<p class="opening">“{_esc(world.opening_line)}”</p>'
        f'<div class="edition">{_esc(edition)}</div>'
        + (f'<div class="window">{_esc(window)}</div>' if window else "")
        + "</article>"
    )

    codex_only = len(entries) - len(chaptered_ids)
    foreword = (
        '<article class="page"><div class="chapter-no">Foreword</div>'
        "<h2>How this world was written</h2>"
        '<section class="passage dropcap"><p>Anyone could write into this world — '
        "and a graph of autonomous agents held the gates: moderating every "
        "fragment, checking it against canon, tracing its lineage, and weaving "
        "what survived into the shared story. What follows is everything the "
        "crowd wrote and the agents accepted, exactly as it entered canon.</p>"
        f"<p>From the opening line, {len(chapters)} storylines grew"
        f"{f', and {codex_only} further fragments rest in the codex' if codex_only > 0 else ''}."
        " Chapters are ordered by the crowd's votes; where a timeline forks, the "
        "fork is marked.</p></section>"
        '<div class="stats">'
        f'<div class="stat"><b>{len(entries)}</b><span>canon entries</span></div>'
        f'<div class="stat"><b>{len(chapters)}</b><span>storylines</span></div>'
        f'<div class="stat"><b>{len(contributors)}</b><span>contributors</span></div>'
        "</div></article>"
    )

    chapter_html = "".join(
        _render_chapter(i, c, by_id) for i, c in enumerate(chapters)
    )

    atlas_html = ""
    map_uri = _local_asset_data_uri(world.map_image_url)
    if map_uri:
        atlas_html = (
            '<article class="page atlas"><figure>'
            f'<img src="{map_uri}" alt="The Living Atlas of {_esc(world.theme)}"/>'
            "<figcaption>The Living Atlas — geography proposed by the "
            "Cartographer, painted by the Atlas Illustrator (AI-generated "
            "imagery), placed only through the deterministic controller."
            "</figcaption></figure></article>"
        )

    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'/>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>",
        f"<title>{_esc(world.theme)} — A World Engine Anthology</title>",
        f"<style>{_CSS}</style></head><body><main class='folio'>",
        cover,
        foreword,
        chapter_html,
        _render_codex(entries),
        atlas_html,
        _render_colophon(entries, chapters, generated_at),
        "</main></body></html>",
    ]
    return "".join(parts)


def write_book(
    out_path: str | Path | None = None,
    world_id: str | None = None,
    store: CanonStore | None = None,
) -> Path:
    """Compile and write the anthology to disk; returns the written path."""
    store = store or get_store()
    world = store.get_world(world_id) if world_id else store.get_active_world()
    if world is None:
        raise ValueError("No world to compile.")
    html_text = compile_book(world.id, store)
    path = (
        Path(out_path)
        if out_path
        else Path("books") / f"{world.id}_anthology.html"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bind a World Engine drop into a single-file HTML anthology."
    )
    parser.add_argument("--world", help="World id (default: the active world).")
    parser.add_argument("--out", help="Output path (default: books/<world>_anthology.html).")
    args = parser.parse_args()

    path = write_book(out_path=args.out, world_id=args.world)
    size_kb = path.stat().st_size / 1024
    print(f"Bound the anthology: {path} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
