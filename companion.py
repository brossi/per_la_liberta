"""Render the Reader's Companion markdown into standalone web pages.

Phase 1 of pairing the companion apparatus with the bilingual edition: each
``output/companion/*.md`` file becomes a ``docs/companion/*.html`` page that
shares the edition's CSS/theme shell, deep-links its chapter citations into the
reading page, cross-links to its sibling companion pages, and keeps the
companion's distinct rights notices visible.

The companion markdown is authored by hand and is the single source of truth;
this module only renders it. It also emits two machine-readable indexes
(entity index + citation map) that Phase 2's in-text entity popovers and
per-chapter orientation drawers will consume.
"""

import hashlib
import json
import re
import shutil
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token

import translate
from typeset import (
    CSS_PATH,
    PDF_PAGE_OFFSET,
    SITE_BASE,
    _font_controls_block,
    _font_size_js,
    _slug,
    _theme_controls_block,
    _theme_js,
    _theme_restore_js,
)

ROOT = Path(__file__).parent
COMPANION_SRC = ROOT / "output" / "companion"
DOCS_COMPANION = ROOT / "docs" / "companion"
DOCS_INDEX = ROOT / "docs" / "index.html"
ITALIAN_MD = ROOT / "output" / "italian_clean.md"
CHAPTER_PAGES = ROOT / "data" / "chapter_pages.json"
DATA_DIR = ROOT / "data"

# Ordered top-level pages for the in-companion reading nav (filename stem → label).
NAV = [
    ("index", "Overview"),
    ("summary", "Summary"),
    ("timeline", "Timeline"),
    ("personae", "Personae"),
    ("events", "Events"),
    ("themes", "Themes"),
    ("glossary", "Glossary"),
    ("follow-up", "Research leads"),
]
# Rights / apparatus pages, surfaced in the footer rather than the reading nav.
FOOTER = [
    ("COPYRIGHT", "Copyright & licensing"),
    ("images/CREDITS", "Image credits"),
    ("sources/index", "Primary sources"),
]

# Chapter citations as the companion writes them: "P1 Ch. 6 (pp. 34–39)",
# "Part 2, Ch. 10", "P1 Ch. 17–19". Captures part (1/2) and the first chapter
# number; any trailing range (–19) is consumed but the link targets the first.
CITATION_RE = re.compile(
    r"(?:Part\s*|P)\s*([12])\s*,?\s*Ch\.?\s*(\d+)(?:\s*[–-]\s*\d+)?"
)


# --------------------------------------------------------------------------- #
# Citation → edition-anchor map
# --------------------------------------------------------------------------- #
def build_citation_map() -> dict[str, dict]:
    """Map "P{part} Ch.{n}" → the edition's chapter anchor + page range.

    Chapter order is authoritative: the Nth content chapter in a part is
    "P{part} Ch.{N}". The edition's HTML id is recomputed with typeset's own
    ``_slug`` on the Italian title, so companion deep-links can never drift
    from the section ids ``typeset.py`` emits.
    """
    chapters = translate.parse_italian_markdown(ITALIAN_MD.read_text(encoding="utf-8"))
    titles: dict[str, list[str]] = {"1": [], "2": []}
    for ch in chapters:
        cid = ch["id"]
        if cid.startswith("p1_"):
            titles["1"].append(ch["title"])
        elif cid.startswith("p2_"):
            titles["2"].append(ch["title"])

    pages = json.loads(CHAPTER_PAGES.read_text(encoding="utf-8")) if CHAPTER_PAGES.exists() else {}
    part_prefix = {"1": "parte-prima", "2": "parte-seconda"}

    cmap: dict[str, dict] = {}
    for part, part_titles in titles.items():
        for idx, title in enumerate(part_titles, 1):
            anchor = f"ch-{part_prefix[part]}-{_slug(title)}"
            scan = pages.get(f"p{part}_ch{idx:02d}")
            entry = {"anchor": anchor, "title": title}
            if scan:
                entry["scan_pages"] = [scan[0], scan[-1]]
                entry["book_pages"] = [scan[0] - PDF_PAGE_OFFSET, scan[-1] - PDF_PAGE_OFFSET]
            cmap[f"{part}:{idx}"] = entry
    return cmap


def _assert_citation_targets(citation_map: dict[str, dict]) -> None:
    """Fail loudly if any citation anchor is missing from the published edition."""
    if not DOCS_INDEX.exists():
        print("  Warning: docs/index.html not found — skipping citation-target check.")
        print("  Run `pipeline.py --step typeset` first to verify deep-links resolve.")
        return
    edition = DOCS_INDEX.read_text(encoding="utf-8")
    missing = sorted(
        {e["anchor"] for e in citation_map.values()}
        - set(re.findall(r'id="(ch-[^"]+)"', edition))
    )
    if missing:
        raise AssertionError(
            "Companion citation anchors absent from docs/index.html (slug drift?): "
            + ", ".join(missing)
        )


# --------------------------------------------------------------------------- #
# Markdown → HTML token transforms
# --------------------------------------------------------------------------- #
def _gh_slug(text: str) -> str:
    """GitHub-style heading anchor — matches the companion's existing cross-refs.

    Lowercase, drop characters outside [word, space, hyphen], then turn each
    space into a hyphen (without collapsing runs, so an em-dash flanked by
    spaces yields the "--" the corpus links already use).
    """
    s = re.sub(r"<[^>]+>", " ", text)           # inline HTML (e.g. <br>) → space
    # NB: do not collapse runs of spaces — an em-dash flanked by spaces must
    # survive as the "--" the corpus's existing cross-refs rely on.
    s = re.sub(r"[^\w\- ]", "", s.strip().lower())
    return s.strip().replace(" ", "-")


def _rewrite_link_href(href: str) -> str:
    """Companion-relative ``.md`` links → ``.html``; directory links → index."""
    if re.match(r"^(https?:|mailto:|#)", href):
        return href
    if href.endswith("/"):
        return href + "index.html"
    m = re.match(r"^([^#]*)(#.*)?$", href)
    path, anchor = m.group(1), m.group(2) or ""
    if path.endswith(".md"):
        path = path[:-3] + ".html"
    return path + anchor


def _text_token(content: str) -> Token:
    t = Token("text", "", 0)
    t.content = content
    return t


def _split_citations(text: str, citation_map: dict, docs_root: str) -> list[Token]:
    """Replace chapter citations in a text run with links into the edition."""
    out: list[Token] = []
    pos = 0
    for m in CITATION_RE.finditer(text):
        entry = citation_map.get(f"{m.group(1)}:{int(m.group(2))}")
        if not entry:
            continue
        if m.start() > pos:
            out.append(_text_token(text[pos:m.start()]))
        link_open = Token("link_open", "a", 1)
        link_open.attrSet("href", f"{docs_root}index.html#{entry['anchor']}")
        link_open.attrSet("class", "chapter-cite")
        link_open.attrSet("title", "Open this chapter in the edition")
        out += [link_open, _text_token(m.group(0)), Token("link_close", "a", -1)]
        pos = m.end()
    if not out:
        return [_text_token(text)]
    if pos < len(text):
        out.append(_text_token(text[pos:]))
    return out


def _rewrite_inline_children(children: list[Token], citation_map: dict, docs_root: str) -> list[Token]:
    """Rewrite links and chapter citations within one inline token's children."""
    out: list[Token] = []
    link_depth = 0
    for ch in children:
        if ch.type == "link_open":
            ch.attrSet("href", _rewrite_link_href(ch.attrGet("href") or ""))
            link_depth += 1
            out.append(ch)
        elif ch.type == "link_close":
            link_depth -= 1
            out.append(ch)
        elif ch.type == "text" and link_depth == 0:
            out.extend(_split_citations(ch.content, citation_map, docs_root))
        else:
            out.append(ch)
    return out


def _callout_kind(tokens: list[Token], i: int) -> str | None:
    """Classify a blockquote by its first inline line: historical / scholarship."""
    depth = 0
    for j in range(i, len(tokens)):
        t = tokens[j]
        if t.type == "blockquote_open":
            depth += 1
        elif t.type == "blockquote_close":
            depth -= 1
            if depth == 0:
                return None
        elif t.type == "inline":
            content = t.content.lstrip()
            if content.startswith("**Historical note**"):
                return "historical"
            if content.startswith("**Scholarship**"):
                return "scholarship"
            return None
    return None


def _transform(tokens: list[Token], citation_map: dict, docs_root: str,
               entities: list | None, page_stem: str) -> str | None:
    """Mutate the token stream in place; return the page's H1 text if present."""
    heading_ids: dict[str, int] = {}
    page_title: str | None = None

    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            inline = tokens[i + 1] if i + 1 < len(tokens) and tokens[i + 1].type == "inline" else None
            if inline is not None:
                base = _gh_slug(inline.content)
                seen = heading_ids.get(base, 0)
                anchor = base if not seen else f"{base}-{seen}"
                heading_ids[base] = seen + 1
                tok.attrSet("id", anchor)
                if tok.tag == "h1" and page_title is None:
                    plain = re.sub(r"<[^>]+>", " ", inline.content)
                    plain = re.sub(r"[*_`]", "", plain)
                    page_title = re.sub(r"\s+", " ", plain).strip()
                # Phase-2 prep: index personae figures by their h3 headings.
                if entities is not None and tok.tag == "h3":
                    entities.append(_personae_entity(inline.content, anchor, page_stem))
        elif tok.type == "blockquote_open":
            kind = _callout_kind(tokens, i)
            if kind:
                cls = (tok.attrGet("class") or "").strip()
                tok.attrSet("class", f"{cls} callout callout-{kind}".strip())
        elif tok.type == "inline" and tok.children:
            tok.children = _rewrite_inline_children(tok.children, citation_map, docs_root)

    return page_title


# --------------------------------------------------------------------------- #
# Phase-2 entity index
# --------------------------------------------------------------------------- #
def _citations_in(text: str) -> list[str]:
    return [f"{m.group(1)}:{int(m.group(2))}" for m in CITATION_RE.finditer(text)]


def _personae_entity(heading_content: str, anchor: str, page_stem: str) -> dict:
    """Extract {name, page, anchor, chapters} from a personae h3 heading."""
    name = re.split(r"\s*[—–]\s*|\s*\*?\(", heading_content)[0]
    name = name.strip().strip("*").strip()
    return {
        "name": name,
        "page": f"{page_stem}.html",
        "anchor": anchor,
        "chapters": _citations_in(heading_content),
    }


def _glossary_entities(md_text: str) -> list[dict]:
    """Index glossary bold-lead terms (**Term.**) to their section anchor."""
    ents: list[dict] = []
    section = ""
    for line in md_text.split("\n"):
        head = re.match(r"^#{2,3}\s+(.*)$", line)
        if head:
            section = _gh_slug(head.group(1))
            continue
        bold = re.match(r"^\*\*(.+?)\.?\*\*", line.strip())
        if bold:
            ents.append({
                "name": bold.group(1).strip().rstrip("."),
                "page": "glossary.html",
                "anchor": section,
                "chapters": _citations_in(line),
            })
    return ents


# --------------------------------------------------------------------------- #
# Page shell
# --------------------------------------------------------------------------- #
def _nav_links(active_stem: str, companion_root: str) -> str:
    items = []
    for stem, label in NAV:
        cls = ' class="active"' if stem == active_stem else ""
        items.append(f'<a href="{companion_root}{stem}.html"{cls}>{label}</a>')
    return "\n      ".join(items)


def _footer_links(companion_root: str) -> str:
    items = [f'<a href="{companion_root}{stem}.html">{label}</a>' for stem, label in FOOTER]
    return "\n      ".join(items)


def _page_html(title: str, body_html: str, depth: int, css_hash: str, active_stem: str) -> str:
    docs_root = "../" * (depth + 1)       # docs/companion/<depth>/  →  docs/
    companion_root = "../" * depth         # …                        →  docs/companion/
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{title} — Reader's Companion</title>",
        f'<link rel="stylesheet" href="{docs_root}static/bilingual.css?v={css_hash}">',
        "</head>",
        '<body class="companion">',
        "",
        *_theme_restore_js(reader=False),
        "",
        "<!-- Top-right controls (font size + colour theme, shared with the edition) -->",
        '<div class="top-right-controls">',
        *_font_controls_block(marginalia_toggle=False),
        *_theme_controls_block(),
        "</div>",
        "",
        '<header class="companion-topbar">',
        f'  <a class="companion-back" href="{docs_root}index.html">&larr; Back to the edition</a>',
        '  <nav class="companion-nav">',
        f"      {_nav_links(active_stem, companion_root)}",
        "  </nav>",
        "</header>",
        "",
        '<main class="companion-page">',
        body_html,
        "</main>",
        "",
        '<footer class="companion-footer">',
        "  <p>From <em>A Reader&rsquo;s Companion to Per la libert&agrave;!</em> — "
        "companion text &copy; 2026 Ben Rossi, all rights reserved. The 1913 book by "
        "Cesare Crespi is in the public domain; images are licensed separately "
        "(public domain, CC0, or CC BY-SA with attribution).</p>",
        f'  <p class="companion-footer-links">{_footer_links(companion_root)}</p>',
        "</footer>",
        "",
        "<script>",
        *_font_size_js(),
        "",
        *_theme_js(),
        "</script>",
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def _sources_index_html(depth: int, css_hash: str) -> str:
    """A small landing page listing the transcribed primary sources."""
    src_dir = COMPANION_SRC / "sources"
    rows = []
    for md_file in sorted(src_dir.glob("*.md")):
        if md_file.stem == "index":
            continue
        text = md_file.read_text(encoding="utf-8")
        h1 = re.search(r"^#\s+(.*)$", text, re.MULTILINE)
        label = h1.group(1).strip() if h1 else md_file.stem
        rows.append(f'<li><a href="{md_file.stem}.html">{label}</a></li>')
    body = (
        "<h1>Primary sources</h1>\n"
        "<p>Transcribed contemporary documents behind the book.</p>\n"
        f"<ul>\n{chr(10).join(rows)}\n</ul>"
    )
    return _page_html("Primary sources", body, depth, css_hash, active_stem="")


def build() -> None:
    """Render the companion to docs/companion/ and emit the Phase-2 indexes."""
    if not COMPANION_SRC.exists():
        print(f"  Error: {COMPANION_SRC} not found")
        return

    md = MarkdownIt("commonmark", {"html": True}).enable("table")
    css_hash = hashlib.md5(CSS_PATH.read_bytes()).hexdigest()[:8]

    citation_map = build_citation_map()
    _assert_citation_targets(citation_map)

    # Keep docs/static/bilingual.css current — companion pages share it, and the
    # cache-buster hash above is computed from the canonical copy. Mirrors the
    # font-path rewrite typeset() applies on its own sync.
    docs_css = ROOT / "docs" / "static" / "bilingual.css"
    if docs_css.parent.exists():
        docs_css.write_text(
            CSS_PATH.read_text(encoding="utf-8").replace("../docs/assets/", "../assets/"),
            encoding="utf-8",
        )

    # Fresh tree (companion HTML is fully regenerable).
    if DOCS_COMPANION.exists():
        shutil.rmtree(DOCS_COMPANION)
    DOCS_COMPANION.mkdir(parents=True)

    entities: list[dict] = []
    page_count = 0

    for src in sorted(COMPANION_SRC.rglob("*.md")):
        rel = src.relative_to(COMPANION_SRC)
        depth = len(rel.parts) - 1
        stem = rel.with_suffix("").as_posix()
        docs_root = "../" * (depth + 1)

        text = src.read_text(encoding="utf-8")
        tokens = md.parse(text)

        collector = entities if rel.name == "personae.md" else None
        title = _transform(tokens, citation_map, docs_root, collector, stem)
        if rel.name == "glossary.md":
            entities.extend(_glossary_entities(text))

        body_html = md.renderer.render(tokens, md.options, {})
        page_title = title or rel.stem.replace("-", " ").title()
        active_stem = stem if any(stem == n for n, _ in NAV) else ""

        out_path = DOCS_COMPANION / rel.with_suffix(".html")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            _page_html(page_title, body_html, depth, css_hash, active_stem),
            encoding="utf-8",
        )
        page_count += 1

    # Mirror every non-markdown asset (images, etc.), preserving the tree.
    asset_count = 0
    for asset in COMPANION_SRC.rglob("*"):
        if asset.is_file() and asset.suffix != ".md":
            dest = DOCS_COMPANION / asset.relative_to(COMPANION_SRC)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset, dest)
            asset_count += 1

    # Landing page for the sources/ directory link.
    src_dir = DOCS_COMPANION / "sources"
    if (COMPANION_SRC / "sources").exists():
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "index.html").write_text(_sources_index_html(1, css_hash), encoding="utf-8")
        page_count += 1

    # Phase-2 indexes.
    (DATA_DIR / "companion_citation_map.json").write_text(
        json.dumps(citation_map, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (DATA_DIR / "companion_entity_index.json").write_text(
        json.dumps(entities, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"  Companion: {page_count} pages, {asset_count} assets → {DOCS_COMPANION}")
    print(f"  Indexes: data/companion_citation_map.json ({len(citation_map)} chapters), "
          f"data/companion_entity_index.json ({len(entities)} entities)")


if __name__ == "__main__":
    build()
