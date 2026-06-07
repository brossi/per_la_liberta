"""Step 8: Typeset bilingual edition as HTML and PDF.

Produces a Loeb Classical Library-style facing-page layout:
Italian on the left (verso), English on the right (recto),
with source page citations linked to Internet Archive scans.
"""

import json
import os
import re
from pathlib import Path

IA_ITEM_ID = "perlalibertdal00cres"
SITE_BASE = "https://brossi.github.io/PER_LA_LIBERTA"
# Offset between PDF leaf numbers and printed book page numbers.
# PDF leaf 7 = book page 1 (leaves 1-6 are cover + front matter).
PDF_PAGE_OFFSET = 6
FONT_DIR = Path(__file__).parent / "assets" / "fonts"
CSS_PATH = Path(__file__).parent / "static" / "bilingual.css"


def _parse_chapters(markdown_text: str) -> list[dict]:
    """Parse a markdown file into chapters with title, level, and paragraphs."""
    chapters = []
    current = None
    current_lines = []

    for line in markdown_text.split("\n"):
        if line.startswith("## ") or line.startswith("### "):
            if current is not None:
                current["paragraphs"] = _split_paragraphs("\n".join(current_lines))
                if current["paragraphs"]:
                    chapters.append(current)

            level = 2 if line.startswith("## ") else 3
            title = line.lstrip("#").strip()

            # Skip book title
            if title in ("Per la Libertà!", "For Freedom!"):
                current = None
                current_lines = []
                continue

            # Part headers have no body text — include them immediately
            structural_parts = {"Parte Prima", "Parte Seconda", "Part One", "Part Two"}
            if title in structural_parts:
                chapters.append({"title": title, "level": level, "page_range": None, "paragraphs": []})
                current = None
                current_lines = []
                continue

            current = {"title": title, "level": level, "page_range": None}
            current_lines = []
        elif line.startswith("---"):
            continue
        elif line.startswith("*") and current is None:
            continue  # Skip metadata lines before first chapter
        elif current is not None:
            # Extract page marker
            page_match = re.match(r"<!-- pages:(\d+)-(\d+) -->", line.strip())
            if page_match:
                current["page_range"] = (int(page_match.group(1)), int(page_match.group(2)))
            else:
                current_lines.append(line)

    if current is not None:
        current["paragraphs"] = _split_paragraphs("\n".join(current_lines))
        if current["paragraphs"]:
            chapters.append(current)

    return chapters


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs on blank lines.

    Strips markdown headings (# lines) that the LLM may have included
    at the top of translated chapters.
    """
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return [p for p in paras if not re.match(r"^#{1,3}\s", p)]


def _align_chapters(italian_chapters: list[dict], english_chapters: list[dict]) -> list[dict]:
    """Align Italian and English chapters by position into bilingual pairs.

    Structural headers (Parte Prima / Part One) are preserved in-order
    so the typesetter can render part divider pages.
    """
    structural_it = {"Parte Prima": "Part One", "Parte Seconda": "Part Two"}
    structural_en = {"Part One", "Part Two"}

    # Separate structural from content chapters, preserving order via indices
    it_content = []
    it_structural = {}  # index-in-content → structural chapter
    content_idx = 0
    for ch in italian_chapters:
        if ch["title"] in structural_it:
            it_structural[content_idx] = ch
        else:
            it_content.append(ch)
            content_idx += 1

    en_content = [ch for ch in english_chapters if ch["title"] not in structural_en]

    pairs = []
    for i in range(max(len(it_content), len(en_content))):
        # Insert part divider before this chapter if needed
        if i in it_structural:
            st = it_structural[i]
            pairs.append({
                "italian_title": st["title"],
                "english_title": structural_it.get(st["title"], ""),
                "italian_paragraphs": [],
                "english_paragraphs": [],
                "page_range": None,
                "level": st["level"],
            })

        it_ch = it_content[i] if i < len(it_content) else None
        en_ch = en_content[i] if i < len(en_content) else None

        pair = {
            "italian_title": it_ch["title"] if it_ch else "",
            "english_title": en_ch["title"] if en_ch else "",
            "italian_paragraphs": it_ch["paragraphs"] if it_ch else [],
            "english_paragraphs": en_ch["paragraphs"] if en_ch else [],
            "page_range": it_ch["page_range"] if it_ch else None,
            "level": it_ch["level"] if it_ch else (en_ch["level"] if en_ch else 3),
        }
        pairs.append(pair)

    return pairs


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _para_to_html(text: str) -> str:
    """Convert a paragraph to HTML, preserving markdown italics."""
    text = _escape_html(text)
    # Convert *italic* to <em>
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    return text


def _qr_data_uri(url: str, scale: int = 3) -> str:
    """Generate a QR code as a PNG data URI."""
    import base64
    import io

    import segno

    qr = segno.make(url)
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=scale, border=1)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def _generate_scan_viewer(output_path: Path) -> None:
    """Generate a lightweight standalone scan viewer page.

    Reads start/end page from the URL hash (e.g., scan.html#127-134)
    and displays the page image with prev/next navigation.
    """
    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Per la Libertà! — Source Scan</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #1a1a1a; color: #ccc; font-family: system-ui, sans-serif;
         display: flex; flex-direction: column; height: 100vh; height: 100dvh; }}
  .header {{ padding: 0.5em 1em; font-size: 0.9em; color: #999;
             border-bottom: 1px solid #333; flex-shrink: 0;
             display: flex; justify-content: space-between; align-items: center; }}
  .header a {{ color: #c47; text-decoration: none; }}
  .viewer {{ flex: 1; overflow: auto; display: flex; align-items: flex-start;
             justify-content: center; padding: 0.5em; }}
  .viewer img {{ max-width: 100%; max-height: 100%; height: auto;
                 border: 1px solid #333; }}
  .nav {{ padding: 0.6em 1em; border-top: 1px solid #333; flex-shrink: 0;
          display: flex; justify-content: space-between; align-items: center; }}
  .nav button {{ background: #333; border: 1px solid #555; color: #ccc;
                 padding: 0.5em 1.2em; border-radius: 4px; font-size: 1em;
                 cursor: pointer; }}
  .nav button:active {{ background: #555; }}
  .nav button:disabled {{ opacity: 0.3; }}
  .nav .page-info {{ font-size: 0.9em; }}
</style>
</head>
<body>
<div class="header">
  <span id="title">Source Scan</span>
  <a id="ia-link" href="#" target="_blank">Internet Archive</a>
</div>
<div class="viewer">
  <img id="img" src="" alt="Source page scan">
</div>
<div class="nav">
  <button id="prev">&lsaquo; Prev</button>
  <span class="page-info" id="page-info"></span>
  <button id="next">Next &rsaquo;</button>
</div>
<script>
const OFFSET = {PDF_PAGE_OFFSET};
const IA_ITEM = '{IA_ITEM_ID}';
const m = location.hash.match(/^#(\\d+)-(\\d+)$/);
if (!m) {{ document.body.innerHTML = '<p style="padding:2em;color:#999">No page range specified. URL should be scan.html#START-END</p>'; }}
else {{
  let cur = parseInt(m[1]), start = cur, end = parseInt(m[2]);
  const img = document.getElementById('img');
  const info = document.getElementById('page-info');
  const iaLink = document.getElementById('ia-link');
  const prevBtn = document.getElementById('prev');
  const nextBtn = document.getElementById('next');
  function show(n) {{
    cur = Math.max(start, Math.min(n, end));
    const pad = String(cur).padStart(4, '0');
    img.src = 'assets/page_images/page_' + pad + '.png';
    info.textContent = 'p. ' + (cur - OFFSET) + ' of ' + (start - OFFSET) + '\\u2013' + (end - OFFSET);
    prevBtn.disabled = cur <= start;
    nextBtn.disabled = cur >= end;
    iaLink.href = 'https://archive.org/details/' + IA_ITEM + '/page/n' + (cur - 1) + '/mode/1up';
    document.getElementById('title').textContent = 'p. ' + (cur - OFFSET);
  }}
  prevBtn.addEventListener('click', () => show(cur - 1));
  nextBtn.addEventListener('click', () => show(cur + 1));
  document.addEventListener('keydown', e => {{
    if (e.key === 'ArrowLeft') show(cur - 1);
    if (e.key === 'ArrowRight') show(cur + 1);
  }});
  // Swipe support for mobile
  let touchX = 0;
  document.addEventListener('touchstart', e => {{ touchX = e.touches[0].clientX; }});
  document.addEventListener('touchend', e => {{
    const dx = e.changedTouches[0].clientX - touchX;
    if (Math.abs(dx) > 50) show(cur + (dx < 0 ? 1 : -1));
  }});
  show(start);
}}
</script>
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")


def _load_revision_changes(state_dir: Path | None) -> dict[str, list[dict]]:
    """Load revision change metadata indexed by chapter_id.

    Returns {chapter_id: [changes]} for the most recent version of each chapter.
    Returns empty dict if no revisions exist.
    """
    if not state_dir:
        return {}
    changes_dir = state_dir / "translation_revisions" / "changes"
    if not changes_dir.exists():
        return {}

    accumulated: dict[str, dict[tuple, dict]] = {}
    for path in sorted(changes_dir.glob("v*_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ch_id = data.get("chapter_id", "")
            changes = data.get("changes", [])
            if ch_id and changes:
                if ch_id not in accumulated:
                    accumulated[ch_id] = {}
                for change in changes:
                    old = change.get("old", "")
                    new = change.get("new", "")
                    if old and new and old != new:  # skip no-ops
                        # Later versions win for same old→new pair
                        accumulated[ch_id][(old, new)] = change
        except (json.JSONDecodeError, KeyError):
            continue
    return {ch_id: list(changes.values()) for ch_id, changes in accumulated.items()}


def _load_provenance_data(state_dir: Path | None) -> dict[str, dict]:
    """Load provenance logs indexed by chapter_id.

    Returns {chapter_id: {primary_draft, incorporations, edgren_influences}}.
    """
    if not state_dir:
        return {}
    drafts_dir = state_dir / "multi_drafts"
    if not drafts_dir.exists():
        return {}
    result = {}
    for prov_path in drafts_dir.glob("*/provenance.json"):
        try:
            data = json.loads(prov_path.read_text(encoding="utf-8"))
            ch_id = prov_path.parent.name
            result[ch_id] = data
        except (json.JSONDecodeError, KeyError):
            continue
    return result


def _draft_label(from_draft: str | None) -> str:
    """Convert draft filename to a readable label.

    e.g. 'draft_gemini__pro.md' -> 'Gemini Pro'
    """
    if not from_draft:
        return "Alternative draft"
    name = from_draft.replace("draft_", "").replace(".md", "")
    name = name.replace("__", " ").replace("_", " ")
    return name.title()


def _find_italian_word(word: str, para_text: str) -> str | None:
    """Find an Italian word (or its conjugated form) in a paragraph.

    Tries exact match first, then 4-char and 3-char stem prefix matching.
    Returns the actual matched word from the paragraph, or None.
    """
    lower = para_text.lower()
    word_lower = word.lower()
    # Exact substring
    if word_lower in lower:
        # Find the original-case version
        idx = lower.index(word_lower)
        return para_text[idx : idx + len(word_lower)]
    # Stem matching (4-char then 3-char)
    for stem_len in (4, 3):
        if len(word_lower) < stem_len:
            continue
        stem = re.escape(word_lower[:stem_len])
        m = re.search(r"\b(\w*" + stem + r"\w*)", para_text, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _extract_italian_from_reason(reason: str) -> list[str]:
    """Extract Italian words/phrases quoted in a provenance reason string.

    Looks for patterns like: Italian 'cadaveri', Italian "la dolce preparazione"
    """
    matches = re.findall(r"""[Ii]talian[oe]?\s+['"]([^'"]+)['"]""", reason)
    return matches


def _precompute_provenance(
    provenance_data: dict[str, dict],
    pairs: list[dict],
    content_chapter_ids: list[str],
) -> dict[str, dict]:
    """Pre-compute provenance annotations for both Italian and English columns.

    Returns {chapter_id: {
        'english': {para_num: [(prov_id, target_text, margin_html)]},
        'italian': {para_num: [(prov_id, italian_word)]},
    }}

    prov IDs are globally unique across the entire book.
    """
    result: dict[str, dict] = {}
    counter = 0
    ch_idx = 0

    for pair in pairs:
        # Skip structural entries (part headers)
        if not pair.get("english_paragraphs"):
            continue
        if ch_idx >= len(content_chapter_ids):
            break
        ch_id = content_chapter_ids[ch_idx]
        ch_idx += 1

        ch_prov = provenance_data.get(ch_id, {})
        incorporations = ch_prov.get("incorporations", [])
        edgren = ch_prov.get("edgren_influences", [])
        if not incorporations and not edgren:
            continue

        it_paras = pair["italian_paragraphs"]
        en_paras = pair["english_paragraphs"]
        en_annot: dict[int, list] = {}
        it_annot: dict[int, list] = {}

        # Incorporations
        for inc in incorporations:
            para_num = inc.get("paragraph", 0)
            replacement = inc.get("replacement", "")
            if not replacement or para_num < 1 or para_num > len(en_paras):
                continue
            if replacement not in en_paras[para_num - 1]:
                continue

            prov_id = f"prov-{counter}"
            counter += 1

            source_label = _draft_label(inc.get("from_draft"))
            original = inc.get("original", "")
            reason = inc.get("reason", "")
            margin_html = (
                f'<span class="marginalia prov" data-prov="{prov_id}">'
                f'<span class="margin-source">{_escape_html(source_label)}</span>'
                f'<span class="margin-old">{_escape_html(original)}</span>'
                f'<span class="margin-reason">{_escape_html(reason)}</span>'
                f'</span>'
            )
            en_annot.setdefault(para_num, []).append((prov_id, replacement, margin_html))

            # Try to find Italian word for cross-column linking
            italian_phrases = _extract_italian_from_reason(reason)
            if italian_phrases and para_num <= len(it_paras):
                it_para = it_paras[para_num - 1]
                for phrase in italian_phrases:
                    found = _find_italian_word(phrase, it_para)
                    if found:
                        it_annot.setdefault(para_num, []).append((prov_id, found))
                        break

        # Edgren influences
        for edg in edgren:
            para_num = edg.get("paragraph", 0)
            choice = edg.get("english_choice", "")
            if not choice or para_num < 1 or para_num > len(en_paras):
                continue
            if choice not in en_paras[para_num - 1]:
                continue

            prov_id = f"prov-{counter}"
            counter += 1

            italian_word = edg.get("italian_word", "")
            definition = edg.get("edgren_definition", "")
            note = edg.get("note", "")
            margin_html = (
                f'<span class="marginalia prov" data-prov="{prov_id}">'
                f'<span class="margin-source">Edgren 1901</span>'
                f'<span class="margin-edgren">{_escape_html(italian_word)} \u2014 {_escape_html(definition)}</span>'
                f'<span class="margin-reason">{_escape_html(note)}</span>'
                f'</span>'
            )
            en_annot.setdefault(para_num, []).append((prov_id, choice, margin_html))

            # Find Italian word for cross-column linking
            if italian_word and para_num <= len(it_paras):
                it_para = it_paras[para_num - 1]
                found = _find_italian_word(italian_word, it_para)
                if found:
                    it_annot.setdefault(para_num, []).append((prov_id, found))

        if en_annot or it_annot:
            result[ch_id] = {"english": en_annot, "italian": it_annot}

    return result


def _build_overlay_nav(
    sp_chapters: list[dict],
    content_chapter_ids: list[str],
    overlay_chapters: list[dict],
) -> list[dict]:
    """Build the CHAPTERS array for the overlay nav dropdown.

    Merges non-content entries from the mapping file (front matter, cover,
    index, back matter) with content chapter entries, preserving order.
    """
    content_set = set(content_chapter_ids)
    # Index into overlay_chapters (content chapters in order)
    oc_idx = 0
    result = []
    for entry in sp_chapters:
        if entry["id"] in content_set:
            # Insert the corresponding overlay chapter entry
            if oc_idx < len(overlay_chapters):
                result.append(overlay_chapters[oc_idx])
                oc_idx += 1
        else:
            result.append({
                "label": entry.get("label", entry["id"].replace("_", " ").title()),
                "page": entry["start_scan"],
                "chId": "",
                "group": "",
            })
    # Append any remaining content chapters
    while oc_idx < len(overlay_chapters):
        result.append(overlay_chapters[oc_idx])
        oc_idx += 1
    return result


def generate_html(
    italian_path: Path,
    english_path: Path,
    output_path: Path,
    source_pages_path: Path | None = None,
    state_dir: Path | None = None,
    site_base: str | None = None,
) -> Path:
    """Generate bilingual HTML from Italian and English markdown."""
    italian_text = italian_path.read_text(encoding="utf-8")
    english_text = english_path.read_text(encoding="utf-8")

    it_chapters = _parse_chapters(italian_text)
    en_chapters = _parse_chapters(english_text)

    pairs = _align_chapters(it_chapters, en_chapters)

    # Load revision change data for marginalia
    revision_changes = _load_revision_changes(state_dir)
    provenance_data = _load_provenance_data(state_dir)

    # Build ordered list of content chapter IDs from Italian source.
    # Can't use title-based dict: Part 1 and Part 2 share chapter names
    # (e.g., both have "Capitolo Primo"), so a dict would clobber entries.
    from translate import parse_italian_markdown
    italian_parsed = parse_italian_markdown(italian_text)
    _content_chapter_ids = [ch["id"] for ch in italian_parsed if not ch.get("is_structural")]
    _content_ch_idx = 0  # consumed in pair loop below

    # Pre-compute provenance annotations for both columns (IDs assigned here)
    prov_annotations = _precompute_provenance(provenance_data, pairs, _content_chapter_ids)

    # Load chapter start pages mapping (authoritative, manually editable)
    _start_pages_path = Path(__file__).parent / "data" / "chapter_start_pages.json"
    _ch_page_ranges: dict[str, tuple[int, int]] = {}
    if _start_pages_path.exists():
        _sp_data = json.loads(_start_pages_path.read_text(encoding="utf-8"))
        _sp_chapters = _sp_data.get("chapters", [])
        _last_scan = _sp_data.get("_last_scan_page", 278)
        for idx, entry in enumerate(_sp_chapters):
            start = entry["start_scan"]
            end = _sp_chapters[idx + 1]["start_scan"] - 1 if idx + 1 < len(_sp_chapters) else _last_scan
            _ch_page_ranges[entry["id"]] = (start, end)

    # Apply page ranges from mapping file
    _content_ch_idx2 = 0
    for pair in pairs:
        if pair["level"] == 2 and pair["italian_title"] in ("Parte Prima", "Parte Seconda"):
            continue
        if _content_ch_idx2 < len(_content_chapter_ids):
            ch_id = _content_chapter_ids[_content_ch_idx2]
            pair["page_range"] = _ch_page_ranges.get(ch_id)
            _content_ch_idx2 += 1

    # Load source pages for IA links
    source_pages = {}
    if source_pages_path and source_pages_path.exists():
        source_pages_data = json.loads(source_pages_path.read_text(encoding="utf-8"))
        # Build lookup by page range
        for ch_data in source_pages_data.values():
            if ch_data.get("pages"):
                key = (ch_data["pages"][0], ch_data["pages"][-1])
                source_pages[key] = ch_data.get("ia_url", "")

    # Resolve paths relative to the HTML output file
    try:
        css_rel = CSS_PATH.resolve().relative_to(output_path.parent.resolve())
    except ValueError:
        css_rel = Path(os.path.relpath(CSS_PATH.resolve(), output_path.parent.resolve()))

    # Path to page images relative to output HTML (canonical copy in docs/assets/)
    page_img_dir = Path(__file__).parent / "docs" / "assets" / "page_images"
    try:
        page_img_rel = page_img_dir.resolve().relative_to(output_path.parent.resolve())
    except ValueError:
        page_img_rel = Path(os.path.relpath(page_img_dir.resolve(), output_path.parent.resolve()))

    import hashlib
    css_hash = hashlib.md5(CSS_PATH.read_bytes()).hexdigest()[:8]

    html_parts = [
        "<!DOCTYPE html>",
        '<html lang="mul">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>Per la Libertà! / For Freedom!</title>",
        f'<link rel="stylesheet" href="{css_rel}?v={css_hash}">',
        "</head>",
        "<body>",
        "",
        "<!-- Restore the viewer's last configuration before first paint (avoids flash) -->",
        "<script>",
        "(function () { try {",
        "  var b = document.body, d = document.documentElement;",
        "  d.setAttribute('data-theme', localStorage.getItem('theme') || 'mid');",
        "  var fs = localStorage.getItem('fontSize');",
        "  if (fs) d.style.fontSize = parseInt(fs, 10) + 'px';",
        "  var lf = localStorage.getItem('langFocus');",
        "  if (lf === 'it') b.classList.add('lang-it-only');",
        "  else if (lf === 'en') b.classList.add('lang-en-only');",
        "  if (localStorage.getItem('hideMarginalia') !== 'false') {",
        "    b.classList.add('no-marginalia'); b.classList.add('no-provenance');",
        "  }",
        "} catch (e) {} })();",
        "</script>",
        "",
        "<!-- Slide-in overlay for source page images -->",
        '<div id="page-overlay" class="page-overlay">',
        '  <div class="page-overlay-header">',
        '    <label class="page-overlay-page-label">p.&thinsp;<input id="page-overlay-page-input" type="number" title="Jump to book page"></label>',
        '    <select id="page-overlay-chapter-select" title="Jump to chapter"></select>',
        '    <span id="page-overlay-scan-label" class="page-overlay-scan-label"></span>',
        '    <button id="page-overlay-close" aria-label="Close">&times;</button>',
        "  </div>",
        '  <div class="page-overlay-body">',
        '    <img id="page-overlay-img" src="" alt="Source page scan">',
        "  </div>",
        '  <div class="page-overlay-nav">',
        '    <button id="page-overlay-prev">&lsaquo; Prev</button>',
        '    <span class="page-overlay-zoom-controls">',
        '      <button id="page-overlay-zoom-out" aria-label="Zoom out" title="Zoom out">&minus;</button>',
        '      <button id="page-overlay-zoom-reset" aria-label="Reset zoom" title="Reset zoom">1:1</button>',
        '      <button id="page-overlay-zoom-in" aria-label="Zoom in" title="Zoom in">+</button>',
        '    </span>',
        '    <a id="page-overlay-ia-link" href="#" target="_blank">View on Internet Archive</a>',
        '    <button id="page-overlay-next">Next &rsaquo;</button>',
        "  </div>",
        "</div>",
        "",
        "<!-- Fixed TOC trigger -->",
        '<button id="toc-trigger" class="toc-trigger" aria-label="Table of contents">&#9776;</button>',
        "",
        "<!-- Top-right controls -->",
        '<div class="top-right-controls">',
        '  <div class="lang-focus-controls" role="group" aria-label="Language display">',
        '    <button id="lang-it" aria-label="Show Italian only" title="Italian only">IT</button>',
        '    <button id="lang-both" aria-label="Show both languages" title="Both languages">Both</button>',
        '    <button id="lang-en" aria-label="Show English only" title="English only">EN</button>',
        '  </div>',
        '  <div class="font-size-controls">',
        '    <button id="font-smaller" aria-label="Decrease font size">&minus;</button>',
        '    <button id="font-larger" aria-label="Increase font size">&plus;</button>',
        '    <button id="toggle-marginalia" aria-label="Toggle marginalia" title="Toggle marginalia">&#9998;</button>',
        '  </div>',
        '  <div class="theme-controls">',
        '    <button id="theme-trigger" aria-label="Colour theme" title="Colour theme" aria-haspopup="true" aria-expanded="false">&#9681;</button>',
        '    <div id="theme-menu" class="theme-menu" role="menu" aria-label="Colour theme">',
        '      <div class="group-label">Light</div>',
        '      <button class="theme-opt" role="menuitemradio" data-set-theme="original"><span class="theme-swatch sw-original">A</span>Original</button>',
        '      <button class="theme-opt" role="menuitemradio" data-set-theme="warm"><span class="theme-swatch sw-warm">A</span>Warm tan</button>',
        '      <button class="theme-opt" role="menuitemradio" data-set-theme="cream"><span class="theme-swatch sw-cream">A</span>Lighter cream</button>',
        '      <button class="theme-opt" role="menuitemradio" data-set-theme="mid"><span class="theme-swatch sw-mid">A</span>Cream (default)</button>',
        '      <button class="theme-opt" role="menuitemradio" data-set-theme="ivory"><span class="theme-swatch sw-ivory">A</span>Calm ivory</button>',
        '      <button class="theme-opt" role="menuitemradio" data-set-theme="bright"><span class="theme-swatch sw-bright">A</span>Bright cream</button>',
        '      <div class="group-label">Dark</div>',
        '      <button class="theme-opt" role="menuitemradio" data-set-theme="cocoa"><span class="theme-swatch sw-cocoa">A</span>Warm cocoa</button>',
        '      <button class="theme-opt" role="menuitemradio" data-set-theme="ash"><span class="theme-swatch sw-ash">A</span>Neutral ash</button>',
        '      <button class="theme-opt" role="menuitemradio" data-set-theme="slate"><span class="theme-swatch sw-slate">A</span>Cool slate</button>',
        '    </div>',
        '  </div>',
        '</div>',
        "",
        "<!-- Slide-in chapter index -->",
        '<nav id="toc-panel" class="toc-panel">',
        '  <div class="toc-panel-header">',
        '    <span>Contents</span>',
        '    <button id="toc-close" aria-label="Close">&times;</button>',
        '  </div>',
        '  <ul id="toc-list" class="toc-list"></ul>',
        '</nav>',
        '<div id="toc-backdrop" class="toc-backdrop"></div>',
        "",
        '<div class="title-page">',
        '  <div class="spread">',
        '    <div class="verso title-col" lang="it">',
        '      <h1 class="title-text">PER LA LIBERTÀ!</h1>',
        '      <p class="subtitle">Dalle mie conversazioni col Conte Carlo di Rudio,<br>complice di Felice Orsini</p>',
        '      <p class="author">Cesare Crespi (1913)</p>',
        '    </div>',
        '    <div class="recto title-col" lang="en">',
        '      <h1 class="title-text">FOR FREEDOM!</h1>',
        '      <p class="subtitle">From my conversations with Count Carlo di Rudio,<br>accomplice of Felice Orsini</p>',
        '      <p class="author">Cesare Crespi (1913)</p>',
        '    </div>',
        '  </div>',
        "</div>",
        "",
    ]

    _rev_counter = [0]  # mutable counter for revision IDs
    current_part_it = ""
    current_part_en = ""
    # Collect chapter entries for overlay navigation: [{label, page, chId}, ...]
    _overlay_chapters: list[dict] = []

    for pair in pairs:
        # Detect part transitions
        title = pair["italian_title"]
        if pair["level"] == 2 and title not in ("Prefazione",):
            # Part header — render as a separator page
            current_part_it = pair["italian_title"]
            current_part_en = pair["english_title"]
            en_title = pair["english_title"]
            part_id = re.sub(r"[^a-z0-9]", "-", title.lower()).strip("-")
            html_parts.extend([
                f'<div class="part-page" id="part-{part_id}">',
                f'  <h2 lang="it">{_escape_html(title)}</h2>',
                f'  <h2 lang="en">{_escape_html(en_title)}</h2>' if en_title else "",
                "</div>",
                "",
            ])
            continue

        # Chapter
        level_tag = "h2" if pair["level"] == 2 else "h3"

        # Page citation (injected into first English paragraph as margin note)
        page_cite_html = ""
        if pair["page_range"]:
            start, end = pair["page_range"]
            ia_url = source_pages.get((start, end), "")
            if not ia_url:
                ia_url = f"https://archive.org/details/{IA_ITEM_ID}/page/n{start - 1}/mode/1up"
            book_start = start - PDF_PAGE_OFFSET
            book_end = end - PDF_PAGE_OFFSET
            page_label = f"Source pp. {book_start}\u2013{book_end}"
            _base = site_base or SITE_BASE
            qr_url = f"{_base}/scan.html#{start}-{end}"
            qr_src = _qr_data_uri(qr_url, scale=10)
            page_cite_html = (
                f'<span class="page-cite">'
                f'<a href="#" class="page-citation" '
                f'data-page-start="{start}" data-page-end="{end}" '
                f'data-page-offset="{PDF_PAGE_OFFSET}" '
                f'data-ia-url="{ia_url}" '
                f'data-img-dir="{page_img_rel}" '
                f'title="View original scan">{page_label}</a>'
                f'<button class="qr-toggle" aria-label="Show QR code" '
                f'title="Scan to view on another device">'
                f'<svg viewBox="0 0 24 24" fill="currentColor">'
                f'<rect x="1" y="1" width="9" height="9" rx="1" fill="none" stroke="currentColor" stroke-width="2"/>'
                f'<rect x="4" y="4" width="3" height="3"/>'
                f'<rect x="1" y="14" width="9" height="9" rx="1" fill="none" stroke="currentColor" stroke-width="2"/>'
                f'<rect x="4" y="17" width="3" height="3"/>'
                f'<rect x="14" y="1" width="9" height="9" rx="1" fill="none" stroke="currentColor" stroke-width="2"/>'
                f'<rect x="17" y="4" width="3" height="3"/>'
                f'<rect x="14" y="14" width="3" height="3"/>'
                f'<rect x="20" y="14" width="3" height="3"/>'
                f'<rect x="14" y="20" width="3" height="3"/>'
                f'<rect x="20" y="20" width="3" height="3"/>'
                f'<rect x="17" y="17" width="3" height="3"/>'
                f'</svg></button>'
                f'<span class="qr-popover" role="dialog">'
                f'<span class="qr-popover-inner">'
                f'<img class="scan-qr" src="{qr_src}" alt="QR: {page_label}">'
                f'<span class="qr-caption">Scan to view on another device</span>'
                f'</span></span></span>'
            )

        part_prefix = re.sub(r"[^a-z0-9]", "-", current_part_it.lower()).strip("-") + "-" if current_part_it else ""
        ch_id = part_prefix + re.sub(r"[^a-z0-9]", "-", pair["italian_title"].lower()).strip("-")
        # Record chapter for overlay navigation
        ch_label = pair["english_title"] or pair["italian_title"]
        ch_start_page = pair["page_range"][0] if pair["page_range"] else None
        if ch_start_page is not None:
            _overlay_chapters.append({"label": ch_label, "page": ch_start_page, "chId": f"ch-{ch_id}", "group": current_part_en})
        part_label_it = f'<span class="part-label">{_escape_html(current_part_it)}</span>' if current_part_it else ""
        part_label_en = f'<span class="part-label">{_escape_html(current_part_en)}</span>' if current_part_en else ""
        html_parts.extend([
            f'<section class="chapter" id="ch-{ch_id}">',
            '  <div class="chapter-header">',
            '    <div class="spread chapter-title-spread">',
            f'      <div class="chapter-title-col" lang="it">{part_label_it}<{level_tag} class="chapter-title">{_escape_html(pair["italian_title"])}</{level_tag}></div>',
            f'      <div class="chapter-title-col" lang="en">{part_label_en}<{level_tag} class="chapter-title">{_escape_html(pair["english_title"])}</{level_tag}></div>' if pair["english_title"] else '      <div class="chapter-title-col"></div>',
            '    </div>',
            "",
            "  </div>",
            '  <div class="spread">',
            '    <div class="verso" lang="it">',
        ])

        # Resolve chapter ID for annotations
        ch_id = _content_chapter_ids[_content_ch_idx] if _content_ch_idx < len(_content_chapter_ids) else ""
        _content_ch_idx += 1
        ch_annot = prov_annotations.get(ch_id, {})
        ch_it_annot = ch_annot.get("italian", {})
        ch_en_annot = ch_annot.get("english", {})

        # Italian paragraphs (with cross-column provenance links)
        for para_idx, p in enumerate(pair["italian_paragraphs"]):
            para_html = _para_to_html(p)
            para_num = para_idx + 1
            for prov_id, it_word in ch_it_annot.get(para_num, []):
                escaped_word = _escape_html(it_word)
                if escaped_word in para_html:
                    para_html = para_html.replace(
                        escaped_word,
                        f'<span class="italian-linked" data-prov="{prov_id}">{escaped_word}</span>',
                        1,
                    )
            html_parts.append(f"      <p>{para_html}</p>")

        html_parts.extend([
            "    </div>",
            '    <div class="recto" lang="en">',
        ])

        # English paragraphs (with marginalia for revision + provenance changes)
        ch_changes = revision_changes.get(ch_id, [])

        page_cite_injected = False
        for para_idx, p in enumerate(pair["english_paragraphs"]):
            para_html = _para_to_html(p)
            para_num = para_idx + 1

            # Revision changes
            para_marginalia = []
            for change in ch_changes:
                old_text = change.get("old", "")
                new_text = change.get("new", "")
                reason = change.get("reason", "")
                if old_text and new_text and new_text in p:
                    rev_id = f"rev-{_rev_counter[0]}"
                    _rev_counter[0] += 1
                    escaped_new = _escape_html(new_text)
                    para_html = para_html.replace(
                        escaped_new,
                        f'<span class="revised" data-rev="{rev_id}">{escaped_new}</span>',
                        1,
                    )
                    para_marginalia.append(
                        f'<span class="marginalia" data-rev="{rev_id}">'
                        f'<span class="margin-old">{_escape_html(old_text)}</span>'
                        f'<span class="margin-reason">{_escape_html(reason)}</span>'
                        f'</span>'
                    )

            # Provenance annotations (pre-computed with IDs)
            for prov_id, target_text, margin_html in ch_en_annot.get(para_num, []):
                escaped_target = _escape_html(target_text)
                if escaped_target in para_html:
                    para_html = para_html.replace(
                        escaped_target,
                        f'<span class="provenance-mark" data-prov="{prov_id}">{escaped_target}</span>',
                        1,
                    )
                    para_marginalia.append(margin_html)

            # Inject page citation into first paragraph, marginalia into all
            cite_html = ""
            if not page_cite_injected and page_cite_html:
                cite_html = page_cite_html
                page_cite_injected = True
            margin_html = "".join(para_marginalia)

            html_parts.append(f"      <p>{cite_html}{margin_html}{para_html}</p>")

        html_parts.extend([
            "    </div>",
            "  </div>",
            "</section>",
            "",
        ])

    # Colophon
    html_parts.extend([
        '<div class="colophon" id="colophon">',
        "  <h2>Colophon</h2>",
        "  <p>This bilingual edition was produced from two independent OCR scans of the",
        "  1913 first edition published by Canessa Printing Co., San Francisco. The scans were",
        "  reconciled via three-way collation with a Gemini Pro vision-OCR witness, then cleaned",
        "  through automated and LLM-assisted correction against period Italian dictionaries.</p>",
        "  <p>Translation followed a multi-witness process: independent draft translations were",
        "  generated by Claude Sonnet 4.6 (Anthropic) and Gemini Pro (Google), then evaluated",
        "  on six literary-quality dimensions. A synthesis model (Claude Opus 4.6) selected the",
        "  strongest draft as a base and incorporated superior phrasings from the other where",
        "  evaluation evidence supported it. Lexical choices were cross-referenced against the",
        "  <em>Italian and English Dictionary</em> by Hjalmar Edgren (1901) to prefer",
        "  period-appropriate English renderings over modern equivalents.</p>",
        '  <p>Blue annotations in the margin (<span style="color:var(--color-provenance)">\u2696</span>)',
        "  trace each editorial decision to its source: which draft contributed a phrasing,",
        "  or which dictionary entry informed a word choice. Red annotations",
        '  (<span style="color:var(--color-accent)">\u270e</span>) mark post-synthesis refinements.</p>',
        "  <p>Translation and typesetting by Ben Rossi, March\u2013April 2026.</p>",
        f'  <p>Source scans: <a href="https://archive.org/details/{IA_ITEM_ID}">Internet Archive</a></p>',
        "  <p>Typeface: Bodoni Moda</p>",
        "</div>",
        "",
        "",
        "<script>",
        "// Slide-in overlay for source page images",
        "(() => {",
        "  const overlay = document.getElementById('page-overlay');",
        "  const img = document.getElementById('page-overlay-img');",
        "  const pageInput = document.getElementById('page-overlay-page-input');",
        "  const scanLabel = document.getElementById('page-overlay-scan-label');",
        "  const chapterSelect = document.getElementById('page-overlay-chapter-select');",
        "  const iaLink = document.getElementById('page-overlay-ia-link');",
        "  const closeBtn = document.getElementById('page-overlay-close');",
        "  const prevBtn = document.getElementById('page-overlay-prev');",
        "  const nextBtn = document.getElementById('page-overlay-next');",
        "  const FIRST_PAGE = 1, LAST_PAGE = " + str(max(int(p.stem.split('_')[1]) for p in (Path(__file__).parent / 'docs' / 'assets' / 'page_images').glob('page_*.png'))) + ";",
        "  const CHAPTERS = " + json.dumps(
            _build_overlay_nav(_sp_chapters, _content_chapter_ids, _overlay_chapters)
        ) + ";",
        "  const zoomIn = document.getElementById('page-overlay-zoom-in');",
        "  const zoomOut = document.getElementById('page-overlay-zoom-out');",
        "  const zoomReset = document.getElementById('page-overlay-zoom-reset');",
        "  const body = document.querySelector('.page-overlay-body');",
        "  let zoomLevel = 1;",
        "  const ZOOM_STEP = 1.3, ZOOM_MAX = 5;",
        "  let currentPage = 0, imgDir = '', pageOffset = " + str(PDF_PAGE_OFFSET) + ";",
        "",
        "  // Populate chapter select with optgroup separators",
        "  let curGroup = null;",
        "  let groupEl = null;",
        "  CHAPTERS.forEach((ch, i) => {",
        "    if (ch.group !== curGroup) {",
        "      curGroup = ch.group;",
        "      groupEl = curGroup ? document.createElement('optgroup') : null;",
        "      if (groupEl) { groupEl.label = curGroup; chapterSelect.appendChild(groupEl); }",
        "    }",
        "    const opt = document.createElement('option');",
        "    opt.value = i;",
        "    opt.textContent = ch.label;",
        "    (groupEl || chapterSelect).appendChild(opt);",
        "  });",
        "",
        "  function showPage(n) {",
        "    resetZoom();",
        "    currentPage = Math.max(FIRST_PAGE, Math.min(n, LAST_PAGE));",
        "    const padded = String(currentPage).padStart(4, '0');",
        "    img.src = imgDir + '/page_' + padded + '.png';",
        "    pageInput.value = currentPage - pageOffset;",
        "    scanLabel.textContent = 'scan ' + currentPage;",
        "    // Highlight the chapter containing the current page",
        "    let best = 0;",
        "    for (let i = 0; i < CHAPTERS.length; i++) {",
        "      if (CHAPTERS[i].page <= currentPage) best = i;",
        "    }",
        "    chapterSelect.value = best;",
        "    prevBtn.disabled = currentPage <= FIRST_PAGE;",
        "    nextBtn.disabled = currentPage >= LAST_PAGE;",
        "    const iaBase = 'https://archive.org/details/' + '" + IA_ITEM_ID + "' + '/page/n' + (currentPage - 1) + '/mode/1up';",
        "    iaLink.href = iaBase;",
        "  }",
        "",
        "  // Page input: jump to typed page number",
        "  pageInput.addEventListener('change', () => {",
        "    const n = parseInt(pageInput.value);",
        "    if (!isNaN(n)) showPage(n + pageOffset);",
        "  });",
        "",
        "  // Chapter select: jump to chapter start and scroll main view",
        "  chapterSelect.addEventListener('change', () => {",
        "    const ch = CHAPTERS[parseInt(chapterSelect.value)];",
        "    if (!ch) return;",
        "    showPage(ch.page);",
        "    if (ch.chId) {",
        "      const el = document.getElementById(ch.chId);",
        "      if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});",
        "    }",
        "  });",
        "",
        "  document.querySelectorAll('.page-citation').forEach(a => {",
        "    a.addEventListener('click', e => {",
        "      e.preventDefault();",
        "      pageOffset = parseInt(a.dataset.pageOffset || '0');",
        "      imgDir = a.dataset.imgDir;",
        "      pageInput.min = FIRST_PAGE - pageOffset;",
        "      pageInput.max = LAST_PAGE - pageOffset;",
        "      showPage(parseInt(a.dataset.pageStart));",
        "      overlay.classList.add('open');",
        "    });",
        "  });",
        "",
        "  closeBtn.addEventListener('click', () => overlay.classList.remove('open'));",
        "  prevBtn.addEventListener('click', () => showPage(currentPage - 1));",
        "  nextBtn.addEventListener('click', () => showPage(currentPage + 1));",
        "",
        "  // Close on Escape key",
        "  document.addEventListener('keydown', e => {",
        "    if (e.key === 'Escape') overlay.classList.remove('open');",
        "    if (overlay.classList.contains('open')) {",
        "      if (e.key === 'ArrowLeft') showPage(currentPage - 1);",
        "      if (e.key === 'ArrowRight') showPage(currentPage + 1);",
        "    }",
        "  });",
        "",
        "  // Close when clicking outside the panel",
        "  overlay.addEventListener('click', e => {",
        "    if (e.target === overlay) overlay.classList.remove('open');",
        "  });",
        "",
        "  // Zoom controls",
        "  function applyZoom() {",
        "    if (zoomLevel > 1.05) {",
        "      body.classList.add('zoomed');",
        "      img.style.maxWidth = 'none';",
        "      img.style.width = (body.clientWidth * zoomLevel) + 'px';",
        "    } else {",
        "      body.classList.remove('zoomed');",
        "      img.style.maxWidth = '';",
        "      img.style.width = '';",
        "    }",
        "    zoomOut.disabled = zoomLevel <= 1.05;",
        "    zoomReset.disabled = zoomLevel <= 1.05;",
        "    zoomIn.disabled = zoomLevel >= ZOOM_MAX;",
        "  }",
        "  function resetZoom() {",
        "    zoomLevel = 1;",
        "    applyZoom();",
        "  }",
        "  zoomIn.addEventListener('click', () => {",
        "    zoomLevel = Math.min(zoomLevel * ZOOM_STEP, ZOOM_MAX);",
        "    const cx = body.scrollLeft + body.clientWidth / 2;",
        "    const cy = body.scrollTop + body.clientHeight / 2;",
        "    applyZoom();",
        "    requestAnimationFrame(() => {",
        "      body.scrollLeft = cx * ZOOM_STEP - body.clientWidth / 2;",
        "      body.scrollTop = cy * ZOOM_STEP - body.clientHeight / 2;",
        "    });",
        "  });",
        "  zoomOut.addEventListener('click', () => {",
        "    zoomLevel = Math.max(zoomLevel / ZOOM_STEP, 1);",
        "    applyZoom();",
        "  });",
        "  zoomReset.addEventListener('click', () => {",
        "    resetZoom();",
        "    body.scrollTop = 0;",
        "  });",
        "})();",
        "",
        "// QR popover: click to toggle, close on outside click or Escape",
        "(() => {",
        "  document.addEventListener('click', e => {",
        "    const btn = e.target.closest('.qr-toggle');",
        "    if (btn) {",
        "      e.stopPropagation();",
        "      const popover = btn.nextElementSibling;",
        "      const wasOpen = popover.classList.contains('open');",
        "      document.querySelectorAll('.qr-popover.open').forEach(p => p.classList.remove('open'));",
        "      if (!wasOpen) popover.classList.add('open');",
        "      return;",
        "    }",
        "    if (!e.target.closest('.qr-popover-inner')) {",
        "      document.querySelectorAll('.qr-popover.open').forEach(p => p.classList.remove('open'));",
        "    }",
        "  });",
        "  document.addEventListener('keydown', e => {",
        "    if (e.key === 'Escape') {",
        "      document.querySelectorAll('.qr-popover.open').forEach(p => p.classList.remove('open'));",
        "    }",
        "  });",
        "})();",
        "",
        "// Chapter index panel",
        "(() => {",
        "  const trigger = document.getElementById('toc-trigger');",
        "  const panel = document.getElementById('toc-panel');",
        "  const backdrop = document.getElementById('toc-backdrop');",
        "  const closeBtn = document.getElementById('toc-close');",
        "  const list = document.getElementById('toc-list');",
        "",
        "  // Build TOC from part pages and chapter sections",
        "  let currentDetails = null;",
        "  let currentSublist = null;",
        "  document.querySelectorAll('.part-page, section.chapter').forEach(el => {",
        "    const close = () => { panel.classList.remove('open'); backdrop.classList.remove('open'); };",
        "    if (el.classList.contains('part-page')) {",
        "      const h2 = el.querySelector('h2[lang=\"en\"]') || el.querySelector('h2');",
        "      if (!h2) return;",
        "      const li = document.createElement('li');",
        "      li.className = 'toc-part';",
        "      const details = document.createElement('details');",
        "      details.open = true;",
        "      const summary = document.createElement('summary');",
        "      const a = document.createElement('a');",
        "      a.href = '#' + el.id;",
        "      a.textContent = h2.textContent;",
        "      a.addEventListener('click', close);",
        "      summary.appendChild(a);",
        "      details.appendChild(summary);",
        "      currentSublist = document.createElement('ul');",
        "      details.appendChild(currentSublist);",
        "      li.appendChild(details);",
        "      list.appendChild(li);",
        "      currentDetails = details;",
        "      return;",
        "    }",
        "    const enCol = el.querySelector('.chapter-title-col[lang=\"en\"] .chapter-title');",
        "    const itCol = el.querySelector('.chapter-title-col[lang=\"it\"] .chapter-title');",
        "    const title = enCol ? enCol.textContent : (itCol ? itCol.textContent : null);",
        "    if (!title) return;",
        "    const li = document.createElement('li');",
        "    const a = document.createElement('a');",
        "    a.href = '#' + el.id;",
        "    a.textContent = title;",
        "    a.addEventListener('click', close);",
        "    li.appendChild(a);",
        "    if (currentSublist) { currentSublist.appendChild(li); }",
        "    else { list.appendChild(li); }",
        "  });",
        "",
        "  // Add colophon link (top-level, like Preface)",
        "  const cLi = document.createElement('li');",
        "  cLi.className = 'toc-standalone';",
        "  const cA = document.createElement('a');",
        "  cA.href = '#colophon';",
        "  cA.textContent = 'Colophon';",
        "  cA.addEventListener('click', () => { panel.classList.remove('open'); backdrop.classList.remove('open'); });",
        "  cLi.appendChild(cA);",
        "  list.appendChild(cLi);",
        "",
        "  function toggle(open) {",
        "    panel.classList.toggle('open', open);",
        "    backdrop.classList.toggle('open', open);",
        "  }",
        "  trigger.addEventListener('click', () => toggle(!panel.classList.contains('open')));",
        "  closeBtn.addEventListener('click', () => toggle(false));",
        "  backdrop.addEventListener('click', () => toggle(false));",
        "  document.addEventListener('keydown', e => { if (e.key === 'Escape') toggle(false); });",
        "})();",
        "",
        "// Font size controls",
        "(() => {",
        "  const root = document.documentElement;",
        "  const STEP = 1;",
        "  const MIN = 10;",
        "  const MAX = 24;",
        "  let size = 16;",
        "  const saved = localStorage.getItem('fontSize');",
        "  if (saved) { size = parseInt(saved); root.style.fontSize = size + 'px'; }",
        "",
        "  document.getElementById('font-smaller').addEventListener('click', () => {",
        "    size = Math.max(MIN, size - STEP);",
        "    root.style.fontSize = size + 'px';",
        "    localStorage.setItem('fontSize', size);",
        "  });",
        "  document.getElementById('font-larger').addEventListener('click', () => {",
        "    size = Math.min(MAX, size + STEP);",
        "    root.style.fontSize = size + 'px';",
        "    localStorage.setItem('fontSize', size);",
        "  });",
        "})();",
        "",
        "// Colour theme: swatch popover writing data-theme on <html>, persisted",
        "(() => {",
        "  const root = document.documentElement;",
        "  const trigger = document.getElementById('theme-trigger');",
        "  const menu = document.getElementById('theme-menu');",
        "  const opts = Array.from(menu.querySelectorAll('.theme-opt'));",
        "  function mark(theme) {",
        "    opts.forEach(o => {",
        "      const on = o.dataset.setTheme === theme;",
        "      o.classList.toggle('active', on);",
        "      o.setAttribute('aria-checked', on ? 'true' : 'false');",
        "    });",
        "  }",
        "  function apply(theme) {",
        "    root.setAttribute('data-theme', theme);",
        "    localStorage.setItem('theme', theme);",
        "    mark(theme);",
        "  }",
        "  function open(show) {",
        "    menu.classList.toggle('open', show);",
        "    trigger.setAttribute('aria-expanded', show ? 'true' : 'false');",
        "  }",
        "  mark(root.getAttribute('data-theme') || 'mid');",
        "  trigger.addEventListener('click', e => { e.stopPropagation(); open(!menu.classList.contains('open')); });",
        "  opts.forEach(o => o.addEventListener('click', () => { apply(o.dataset.setTheme); open(false); }));",
        "  document.addEventListener('click', e => { if (!menu.contains(e.target) && e.target !== trigger) open(false); });",
        "  document.addEventListener('keydown', e => { if (e.key === 'Escape') open(false); });",
        "})();",
        "",
        "// Language focus: segmented radio — Italian only / both / English only",
        "(() => {",
        "  const body = document.body;",
        "  const btns = { it: document.getElementById('lang-it'),",
        "                 '': document.getElementById('lang-both'),",
        "                 en: document.getElementById('lang-en') };",
        "  function apply(focus) {",
        "    body.classList.toggle('lang-it-only', focus === 'it');",
        "    body.classList.toggle('lang-en-only', focus === 'en');",
        "    for (const k in btns) btns[k].classList.toggle('active', k === focus);",
        "    if (focus) localStorage.setItem('langFocus', focus); else localStorage.removeItem('langFocus');",
        "    window.dispatchEvent(new Event('resize'));",  # re-align marginalia after layout change
        "  }",
        "  apply(localStorage.getItem('langFocus') || '');",
        "  for (const k in btns) btns[k].addEventListener('click', () => apply(k));",
        "})();",
        "",
        "// Marginalia: alignment, hover linking, click-to-activate, keyboard nav",
        "(() => {",
        "  const allNotes = () => Array.from(document.querySelectorAll('.marginalia'));",
        "  const revNotes = () => Array.from(document.querySelectorAll('.marginalia:not(.prov)'));",
        "  const provNotes = () => Array.from(document.querySelectorAll('.marginalia.prov'));",
        "  let activeId = null;",
        "",
        "  // Find the linked text span for any marginalia note (revision or provenance)",
        "  function getLinked(note) {",
        "    const rev = note.dataset.rev;",
        "    if (rev) return document.querySelector('.revised[data-rev=\"' + rev + '\"]');",
        "    const prov = note.dataset.prov;",
        "    if (prov) return document.querySelector('.provenance-mark[data-prov=\"' + prov + '\"]');",
        "    return null;",
        "  }",
        "",
        "  // Get the unique ID of a note (either data-rev or data-prov)",
        "  function noteId(note) { return note.dataset.rev || note.dataset.prov || null; }",
        "",
        "  // Align marginalia vertically, stacking globally across paragraphs within each recto column",
        "  function alignMarginalia() {",
        "    document.querySelectorAll('.recto').forEach(recto => {",
        "      const notes = Array.from(recto.querySelectorAll('p > .marginalia'));",
        "      if (!notes.length) return;",
        "      // Build array of {note, linkedAbsTop, parentEl} for visible notes",
        "      const items = [];",
        "      for (const note of notes) {",
        "        if (note.offsetParent === null) continue;",
        "        const linked = getLinked(note);",
        "        const absTop = linked ? linked.getBoundingClientRect().top + window.scrollY : 0;",
        "        items.push({ note, absTop, parent: note.parentElement });",
        "      }",
        "      // Sort by the absolute vertical position of their linked text",
        "      items.sort((a, b) => a.absTop - b.absTop);",
        "      // Stack: track the next available absolute Y, clearing page citations",
        "      let nextAbsBottom = 0;",
        "      for (const item of items) {",
        "        const pRect = item.parent.getBoundingClientRect();",
        "        const pAbsTop = pRect.top + window.scrollY;",
        "        // Clear page citation if present in this paragraph",
        "        const cite = item.parent.querySelector('.page-cite');",
        "        if (cite) {",
        "          const citeAbsBottom = cite.getBoundingClientRect().bottom + window.scrollY + 4;",
        "          if (nextAbsBottom < citeAbsBottom) nextAbsBottom = citeAbsBottom;",
        "        }",
        "        // Ideal: align with linked text; actual: at least nextAbsBottom",
        "        const idealAbs = item.absTop;",
        "        const actualAbs = Math.max(idealAbs, nextAbsBottom);",
        "        // Convert absolute position to parent-relative top",
        "        item.note.style.top = (actualAbs - pAbsTop) + 'px';",
        "        nextAbsBottom = actualAbs + item.note.getBoundingClientRect().height + 4;",
        "      }",
        "    });",
        "  }",
        "  alignMarginalia();",
        "  window.addEventListener('resize', alignMarginalia);",
        "  new MutationObserver(alignMarginalia).observe(document.documentElement,",
        "    { attributes: true, attributeFilter: ['style'] });",
        "",
        "  // Reverse lookup: find the marginalia note linked to a text span",
        "  function getNote(span) {",
        "    const rev = span.dataset && span.dataset.rev;",
        "    if (rev) return document.querySelector('.marginalia[data-rev=\"' + rev + '\"]');",
        "    const prov = span.dataset && span.dataset.prov;",
        "    if (prov) return document.querySelector('.marginalia[data-prov=\"' + prov + '\"]');",
        "    return null;",
        "  }",
        "",
        "  // Cross-column: find the Italian-linked span for a prov ID",
        "  function getItalian(provId) {",
        "    return provId ? document.querySelector('.italian-linked[data-prov=\"' + provId + '\"]') : null;",
        "  }",
        "",
        "  // Highlight/unhighlight a provenance group (English span + marginalia + Italian span)",
        "  function highlightProv(provId, on) {",
        "    const it = getItalian(provId);",
        "    if (it) it.classList.toggle('highlight', on);",
        "  }",
        "",
        "  // Hover: bidirectional highlight between text, marginalia, and Italian source",
        "  document.addEventListener('mouseover', e => {",
        "    const note = e.target.closest('.marginalia');",
        "    if (note) {",
        "      const linked = getLinked(note);",
        "      if (linked) linked.classList.add('highlight');",
        "      note.classList.add('highlight');",
        "      highlightProv(note.dataset.prov, true);",
        "      return;",
        "    }",
        "    const span = e.target.closest('.revised, .provenance-mark');",
        "    if (span) {",
        "      const linked = getNote(span);",
        "      if (linked) linked.classList.add('highlight');",
        "      span.classList.add('highlight');",
        "      highlightProv(span.dataset && span.dataset.prov, true);",
        "      return;",
        "    }",
        "    const itSpan = e.target.closest('.italian-linked');",
        "    if (itSpan) {",
        "      itSpan.classList.add('highlight');",
        "      const provId = itSpan.dataset.prov;",
        "      const en = provId && document.querySelector('.provenance-mark[data-prov=\"' + provId + '\"]');",
        "      const mn = provId && document.querySelector('.marginalia[data-prov=\"' + provId + '\"]');",
        "      if (en) en.classList.add('highlight');",
        "      if (mn) mn.classList.add('highlight');",
        "    }",
        "  });",
        "  document.addEventListener('mouseout', e => {",
        "    const note = e.target.closest('.marginalia');",
        "    if (note) {",
        "      const linked = getLinked(note);",
        "      if (linked) linked.classList.remove('highlight');",
        "      note.classList.remove('highlight');",
        "      highlightProv(note.dataset.prov, false);",
        "      return;",
        "    }",
        "    const span = e.target.closest('.revised, .provenance-mark');",
        "    if (span) {",
        "      const linked = getNote(span);",
        "      if (linked) linked.classList.remove('highlight');",
        "      span.classList.remove('highlight');",
        "      highlightProv(span.dataset && span.dataset.prov, false);",
        "      return;",
        "    }",
        "    const itSpan = e.target.closest('.italian-linked');",
        "    if (itSpan) {",
        "      itSpan.classList.remove('highlight');",
        "      const provId = itSpan.dataset.prov;",
        "      const en = provId && document.querySelector('.provenance-mark[data-prov=\"' + provId + '\"]');",
        "      const mn = provId && document.querySelector('.marginalia[data-prov=\"' + provId + '\"]');",
        "      if (en) en.classList.remove('highlight');",
        "      if (mn) mn.classList.remove('highlight');",
        "    }",
        "  });",
        "",
        "  // Click: set active marginalia for keyboard navigation",
        "  function setActive(note) {",
        "    document.querySelectorAll('.marginalia.active').forEach(n => n.classList.remove('active'));",
        "    document.querySelectorAll('.revised.highlight, .provenance-mark.highlight, .italian-linked.highlight').forEach(r => r.classList.remove('highlight'));",
        "    if (note) {",
        "      note.classList.add('active');",
        "      const linked = getLinked(note);",
        "      if (linked) linked.classList.add('highlight');",
        "      highlightProv(note.dataset.prov, true);",
        "      activeId = noteId(note);",
        "    } else {",
        "      activeId = null;",
        "    }",
        "  }",
        "",
        "  document.addEventListener('click', e => {",
        "    const note = e.target.closest('.marginalia');",
        "    if (note) { setActive(note); return; }",
        "    if (!e.target.closest('.marginalia, .revised, .provenance-mark')) setActive(null);",
        "  });",
        "",
        "  // Toggle all marginalia (revision + provenance) visibility",
        "  const revBtn = document.getElementById('toggle-marginalia');",
        "  // Marginalia default to OFF; shown only if the viewer explicitly enabled them.",
        "  const savedHide = localStorage.getItem('hideMarginalia');",
        "  if (savedHide !== 'false') { document.body.classList.add('no-marginalia'); document.body.classList.add('no-provenance'); }",
        "  else { revBtn.classList.add('active'); }",
        "  revBtn.addEventListener('click', () => {",
        "    const hidden = document.body.classList.toggle('no-marginalia');",
        "    if (hidden) document.body.classList.add('no-provenance'); else document.body.classList.remove('no-provenance');",
        "    revBtn.classList.toggle('active', !hidden);",
        "    localStorage.setItem('hideMarginalia', hidden);",
        "    if (hidden) setActive(null);",
        "    alignMarginalia();",
        "  });",
        "",
        "  // Keyboard navigation helper",
        "  function navigateNotes(notesFn, e) {",
        "    const all = notesFn();",
        "    if (!all.length) return;",
        "    let idx = -1;",
        "    if (activeId) {",
        "      idx = all.findIndex(n => noteId(n) === activeId);",
        "    }",
        "    let target;",
        "    if (idx >= 0) {",
        "      const next = e.shiftKey ? idx - 1 : idx + 1;",
        "      target = all[Math.max(0, Math.min(next, all.length - 1))];",
        "    } else {",
        "      const scrollY = window.scrollY + window.innerHeight / 3;",
        "      if (e.shiftKey) {",
        "        for (let i = all.length - 1; i >= 0; i--) {",
        "          if (all[i].getBoundingClientRect().top + window.scrollY < scrollY - 10) { target = all[i]; break; }",
        "        }",
        "      } else {",
        "        for (const n of all) {",
        "          if (n.getBoundingClientRect().top + window.scrollY > scrollY + 10) { target = n; break; }",
        "        }",
        "      }",
        "    }",
        "    if (target) {",
        "      setActive(target);",
        "      target.scrollIntoView({ behavior: 'smooth', block: 'center' });",
        "    }",
        "  }",
        "",
        "  // m/M: navigate revision notes; p/P: navigate provenance notes",
        "  document.addEventListener('keydown', e => {",
        "    if (e.key === 'm' || e.key === 'M') {",
        "      if (!document.body.classList.contains('no-marginalia')) navigateNotes(revNotes, e);",
        "    } else if (e.key === 'p' || e.key === 'P') {",
        "      if (!document.body.classList.contains('no-provenance')) navigateNotes(provNotes, e);",
        "    }",
        "  });",
        "})();",
        "</script>",
        "",
        "</body>",
        "</html>",
    ])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(html_parts), encoding="utf-8")
    print(f"  HTML: {output_path} ({len(html_parts)} lines)")
    return output_path


def generate_pdf(html_path: Path, output_path: Path) -> Path:
    """Render bilingual HTML to PDF via WeasyPrint."""
    from weasyprint import HTML

    HTML(filename=str(html_path), base_url=str(html_path.parent)).write_pdf(str(output_path))
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  PDF: {output_path} ({size_mb:.1f} MB)")
    return output_path


def typeset(output_dir: Path, state_dir: Path | None = None, site_base: str | None = None) -> None:
    """Generate bilingual HTML and PDF from Italian + English markdown."""
    italian_path = output_dir / "italian_clean.md"
    english_path = output_dir / "english_translation.md"
    source_pages_path = output_dir / "source_pages.json"

    if not italian_path.exists():
        print("  Error: italian_clean.md not found")
        return

    has_english = english_path.exists()
    if not has_english:
        print("  Warning: english_translation.md not found — generating Italian-only edition")

    # Generate HTML
    html_path = output_dir / "bilingual.html"
    generate_html(
        italian_path,
        english_path if has_english else italian_path,
        html_path,
        source_pages_path=source_pages_path,
        state_dir=state_dir,
        site_base=site_base,
    )

    # Generate standalone scan viewer for QR code targets
    scan_path = output_dir / "scan.html"
    _generate_scan_viewer(scan_path)
    print(f"  Scan viewer: {scan_path}")

    # Sync to docs/ for GitHub Pages deployment
    docs_dir = Path(__file__).parent / "docs"
    if docs_dir.exists():
        import shutil

        # Copy HTML, fixing relative paths for docs/ structure
        docs_html = (html_path.read_text(encoding="utf-8")
                     .replace("../static/bilingual.css", "static/bilingual.css")
                     .replace("../docs/assets/page_images", "assets/page_images"))
        (docs_dir / "index.html").write_text(docs_html, encoding="utf-8")
        shutil.copy2(scan_path, docs_dir / "scan.html")
        # Copy CSS, fixing font paths for docs/ structure
        docs_css = CSS_PATH.read_text(encoding="utf-8").replace("../docs/assets/", "../assets/")
        (docs_dir / "static" / "bilingual.css").write_text(docs_css, encoding="utf-8")
        print(f"  Synced to docs/")

    # PDF generation disabled — WeasyPrint requires DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
    # To re-enable, uncomment the block below.
    # pdf_path = output_dir / "bilingual.pdf"
    # try:
    #     generate_pdf(html_path, pdf_path)
    # except ImportError:
    #     print("  Warning: weasyprint not installed — skipping PDF generation")
    #     print("  Install with: uv add weasyprint")
    # except Exception as e:
    #     print(f"  PDF generation failed: {e}")


if __name__ == "__main__":
    base = Path(__file__).parent
    typeset(base / "output")
