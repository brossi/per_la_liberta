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
from urllib.parse import quote

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

# Pages whose H3/H4 heading hierarchy is wrapped into nested <details>/<summary>
# disclosures: a book overview stays visible, then each part (H3) opens to its
# summary and a list of chapter (H4) disclosures. See _wrap_details.
NESTED_DETAILS_PAGES = {"summary"}

# Source citations in the "Historical note"/"Scholarship" callouts are written as
# `*(Source: Wikipedia, "Charles DeRudio".)*`, sometimes chaining several articles
# under one marker (`Wikipedia, "Felice Orsini"; "Orsini affair"`) and sometimes
# sitting beside other publishers (`Wikipedia, "Orsini affair"; Britannica,
# "Felice Orsini."`). We linkify only the quoted titles that follow a *recognised
# publisher marker*, chaining through consecutive quoted titles and stopping at the
# first non-quoted source, so a neighbour's title is never mislinked.
#
# Wikipedia titles map to URLs by rule (deterministic slug). Britannica and
# ExecutedToday do not — their path segment / dated post-slug can't be derived
# from the title — so those are a small curated, verified registry. Untitled
# mentions of any publisher (a bare "Britannica") name no article and stay plain.
SOURCE_TITLE = re.compile(r'"([^"]+)"')
# Separator between chained quoted titles: `; ` or `, `, only if a quote follows.
SOURCE_TITLE_SEP = re.compile(r'\s*[;,]\s*(?=")')


def _wiki_url(title: str) -> str:
    """Quoted article title → canonical en.wikipedia.org URL.

    Strips a trailing period pulled inside the closing quote (American style:
    ``"Charles DeRudio."``) before building the slug; spaces → underscores;
    accents, en-dashes, and other non-ASCII are percent-encoded.
    """
    slug = title.strip().rstrip(".").strip().replace(" ", "_")
    return "https://en.wikipedia.org/wiki/" + quote(slug, safe="_(),'")


def _curated_resolver(table: dict[str, str]):
    """Build a resolver that looks a title up in a curated map (trailing '.' tolerant)."""
    return lambda title: table.get(title.strip().rstrip(".").strip())


# Curated, verified URLs for publishers whose links aren't rule-derivable.
BRITANNICA_URLS = {
    "Felice Orsini": "https://www.britannica.com/biography/Felice-Orsini",
}
EXECUTEDTODAY_URLS = {
    "1858: Felice Orsini": "https://www.executedtoday.com/2009/03/13/1858-felice-orsini-italian-revolutionary/",
}

# (publisher marker, title→URL resolver). A resolver returning None leaves the
# title as plain text (e.g. a Britannica article we haven't curated a URL for).
SOURCE_PUBLISHERS = [
    (re.compile(r"Wikipedia,?\s*(?=\")"), _wiki_url),
    (re.compile(r"Britannica,?\s*(?=\")"), _curated_resolver(BRITANNICA_URLS)),
    (re.compile(r"ExecutedToday,?\s*(?=\")"), _curated_resolver(EXECUTEDTODAY_URLS)),
]


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


# Visible references to a sibling companion page — bare prose, a link label, or a
# code span like `images/CREDITS.md`. The pages are published as HTML, so the text
# the reader sees must read .html (link *hrefs* are handled by _rewrite_link_href).
_MD_REF_RE = re.compile(r"([\w./-]+)\.md\b")


def _md_refs_to_html(text: str) -> str:
    """Rewrite visible ``name.md`` companion-page references to ``name.html``."""
    return _MD_REF_RE.sub(lambda m: m.group(1) + ".html", text)


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


def _cited_title_spans(text: str) -> list[tuple[int, int, str]]:
    """Inner-text spans of quoted titles attributable to a recognised publisher.

    Returns ``(start, end, url)`` for each linkable title. Scans every publisher
    marker, chaining through consecutive quoted titles; a resolver returning None
    (an uncurated title) is skipped without breaking the chain.
    """
    spans: list[tuple[int, int, str]] = []
    for marker, resolve in SOURCE_PUBLISHERS:
        for m in marker.finditer(text):
            j = m.end()
            while j < len(text) and text[j] == '"':
                qm = SOURCE_TITLE.match(text, j)
                if not qm:
                    break
                url = resolve(qm.group(1))
                if url:
                    spans.append((qm.start(1), qm.end(1), url))
                sep = SOURCE_TITLE_SEP.match(text, qm.end())
                if not sep:
                    break
                j = sep.end()  # lookahead leaves us on the next opening quote
    return spans


def _link_sources(text: str) -> list[Token]:
    """Wrap publisher-attributed quoted titles in external links; leave quotes in place."""
    spans = sorted(set(_cited_title_spans(text)))
    if not spans:
        return [_text_token(text)]
    out: list[Token] = []
    pos = 0
    for start, end, url in spans:
        if start < pos:  # overlap guard (duplicate marker scans)
            continue
        if start > pos:
            out.append(_text_token(text[pos:start]))
        title = text[start:end]
        link_open = Token("link_open", "a", 1)
        link_open.attrSet("href", url)
        link_open.attrSet("class", "source-cite")
        # Citations leave the reading surface — open in a new tab so the reader
        # keeps their place; rel guards the opener. The ::after icon (CSS, keyed
        # on target=_blank) warns of the jump, per WCAG G200.
        link_open.attrSet("target", "_blank")
        link_open.attrSet("rel", "noopener")
        out += [link_open, _text_token(title), Token("link_close", "a", -1)]
        pos = end
    if pos < len(text):
        out.append(_text_token(text[pos:]))
    return out


def _rewrite_inline_children(children: list[Token], citation_map: dict, docs_root: str) -> list[Token]:
    """Rewrite links and chapter citations within one inline token's children."""
    out: list[Token] = []
    link_depth = 0
    for ch in children:
        if ch.type == "link_open":
            href = _rewrite_link_href(ch.attrGet("href") or "")
            ch.attrSet("href", href)
            # External destinations open in a new tab (same rule as the generated
            # source-cite links); internal companion/edition links stay same-tab
            # so the Back button works as the reader expects.
            if re.match(r"^https?:", href):
                ch.attrSet("target", "_blank")
                ch.attrSet("rel", "noopener")
            link_depth += 1
            out.append(ch)
        elif ch.type == "link_close":
            link_depth -= 1
            out.append(ch)
        elif ch.type == "code_inline":
            # Code spans naming a sibling page (`images/CREDITS.md`) are visible
            # text; point them at the rendered .html.
            ch.content = _md_refs_to_html(ch.content)
            out.append(ch)
        elif ch.type == "text":
            # Visible .md references → .html, at any depth (bare prose *and* link
            # labels like [images/CREDITS.md](…)); hrefs are handled above.
            content = _md_refs_to_html(ch.content)
            if link_depth == 0:
                # Chapter deep-links first, then external source citations within
                # the remaining plain-text runs (the two never share a span).
                for piece in _split_citations(content, citation_map, docs_root):
                    if piece.type == "text":
                        out.extend(_link_sources(piece.content))
                    else:
                        out.append(piece)
            else:
                ch.content = content  # inside a link label — convert, don't nest links
                out.append(ch)
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


def _html_block(content: str) -> Token:
    t = Token("html_block", "", 0)
    t.content = content
    return t


def _h3_has_h4(tokens: list[Token], start: int) -> bool:
    """Does the H3 opening at ``start`` contain an H4 before the next H3 / EOF?"""
    for j in range(start + 1, len(tokens)):
        t = tokens[j]
        if t.type == "heading_open":
            if t.tag == "h3":
                return False
            if t.tag == "h4":
                return True
    return False


# Chapter outline headings spell the citation out ("Part 1, Chapter 6 …"), which
# the abbreviated CITATION_RE ("P1 Ch. 6") deliberately does not match — so the
# headings were never auto-linked, and the disclosure summary toggles cleanly.
CHAPTER_HEADING_RE = re.compile(r"Part\s+([12])\s*,?\s*Chapter\s+(\d+)", re.IGNORECASE)


def _chapter_edition_link(inline_content: str, citation_map: dict, docs_root: str) -> Token | None:
    """A body link into the edition for a chapter heading like 'Part 1, Chapter 6 …'."""
    m = CHAPTER_HEADING_RE.search(inline_content)
    if not m:
        return None
    entry = citation_map.get(f"{m.group(1)}:{int(m.group(2))}")
    if not entry:
        return None
    href = f"{docs_root}index.html#{entry['anchor']}"
    return _html_block(
        f'<p class="chapter-edition-link"><a class="chapter-cite" href="{href}" '
        f'title="Open this chapter in the edition">Read this chapter in the edition →</a></p>\n'
    )


def _wrap_details(tokens: list[Token], citation_map: dict, docs_root: str) -> list[Token]:
    """Wrap a summary page's H3 parts and H4 chapters into nested <details>/<summary>.

    Runs *after* ``_transform`` so heading ids (for anchors) and body deep-links are
    already in place. The book overview (everything before the first H3) passes
    through untouched and stays visible. From the first H3 on:

    - **H3** opens a top-level disclosure: a *part* (an H3 that has H4 children)
      renders ``open`` with its section-summary prose; a childless H3 (the
      Prefazione) renders closed.
    - **H4** opens a *chapter* disclosure nested in its part, rendered closed. Its
      title is flattened to plain text so the whole summary line toggles, and the
      edition deep-link is appended to the chapter body instead.

    Both heading kinds keep their ``<hN id>`` inside the ``<summary>`` so existing
    anchors survive (paired with the expand-on-navigate shim in the page shell).
    """
    start = next(
        (i for i, t in enumerate(tokens) if t.type == "heading_open" and t.tag == "h3"),
        None,
    )
    if start is None:
        return tokens

    out: list[Token] = tokens[:start]
    section_open = False
    chapter_open = False
    pending_link: Token | None = None

    def close_chapter() -> None:
        nonlocal chapter_open, pending_link
        if chapter_open:
            if pending_link is not None:
                out.append(pending_link)
                pending_link = None
            out.append(_html_block("</details>\n"))
            chapter_open = False

    def close_section() -> None:
        nonlocal section_open
        close_chapter()
        if section_open:
            out.append(_html_block("</details>\n"))
            section_open = False

    i, n = start, len(tokens)
    while i < n:
        tok = tokens[i]
        if tok.type == "heading_open" and tok.tag == "h3":
            close_section()
            is_part = _h3_has_h4(tokens, i)
            cls = "summary-part" if is_part else "summary-standalone"
            attr = " open" if is_part else ""
            out.append(_html_block(f'<details class="{cls}"{attr}>\n<summary>'))
            out.extend(tokens[i:i + 3])           # heading_open, inline, heading_close
            out.append(_html_block("</summary>\n"))
            section_open = True
            i += 3
            continue
        if tok.type == "heading_open" and tok.tag == "h4":
            close_chapter()
            out.append(_html_block('<details class="summary-chapter">\n<summary>'))
            inline = tokens[i + 1]
            # Flatten the auto-linked title to plain text (so the line toggles) and
            # move its edition deep-link into the chapter body.
            pending_link = _chapter_edition_link(inline.content, citation_map, docs_root)
            inline.children = [_text_token(inline.content)]
            out.extend(tokens[i:i + 3])
            out.append(_html_block("</summary>\n"))
            chapter_open = True
            i += 3
            continue
        out.append(tok)
        i += 1

    close_section()
    return out


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
        "<!-- Top-right controls (font size + color theme, shared with the edition) -->",
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
        "",
        "// Open the disclosure ancestors of a URL-targeted anchor (deep links into",
        "// a collapsed disclosure), and expand every disclosure before printing.",
        "(function () {",
        "  function openToHash() {",
        "    var el = null;",
        "    try { el = location.hash ? document.querySelector(location.hash) : null; }",
        "    catch (e) { return; }",
        "    for (var p = el; p; p = p.parentElement) {",
        "      if (p.tagName === 'DETAILS') p.open = true;",
        "    }",
        "    if (el) el.scrollIntoView();",
        "  }",
        "  addEventListener('hashchange', openToHash);",
        "  if (location.hash) addEventListener('load', openToHash);",
        "  addEventListener('beforeprint', function () {",
        "    document.querySelectorAll('details').forEach(function (d) { d.open = true; });",
        "  });",
        "})();",
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
        if stem in NESTED_DETAILS_PAGES:
            tokens = _wrap_details(tokens, citation_map, docs_root)

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
