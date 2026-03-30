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


def generate_html(
    italian_path: Path,
    english_path: Path,
    output_path: Path,
    source_pages_path: Path | None = None,
) -> Path:
    """Generate bilingual HTML from Italian and English markdown."""
    italian_text = italian_path.read_text(encoding="utf-8")
    english_text = english_path.read_text(encoding="utf-8")

    it_chapters = _parse_chapters(italian_text)
    en_chapters = _parse_chapters(english_text)

    pairs = _align_chapters(it_chapters, en_chapters)

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

    # Path to page images relative to output HTML
    page_img_dir = Path(__file__).parent / "assets" / "page_images"
    try:
        page_img_rel = page_img_dir.resolve().relative_to(output_path.parent.resolve())
    except ValueError:
        page_img_rel = Path(os.path.relpath(page_img_dir.resolve(), output_path.parent.resolve()))

    html_parts = [
        "<!DOCTYPE html>",
        '<html lang="mul">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>Per la Libertà! / For Freedom!</title>",
        f'<link rel="stylesheet" href="{css_rel}">',
        "</head>",
        "<body>",
        "",
        "<!-- Slide-in overlay for source page images -->",
        '<div id="page-overlay" class="page-overlay">',
        '  <div class="page-overlay-header">',
        '    <span id="page-overlay-title"></span>',
        '    <button id="page-overlay-close" aria-label="Close">&times;</button>',
        "  </div>",
        '  <div class="page-overlay-body">',
        '    <img id="page-overlay-img" src="" alt="Source page scan">',
        "  </div>",
        '  <div class="page-overlay-nav">',
        '    <button id="page-overlay-prev">&lsaquo; Prev</button>',
        '    <a id="page-overlay-ia-link" href="#" target="_blank">View on Internet Archive</a>',
        '    <button id="page-overlay-next">Next &rsaquo;</button>',
        "  </div>",
        "</div>",
        "",
        "<!-- Fixed TOC trigger -->",
        '<button id="toc-trigger" class="toc-trigger" aria-label="Table of contents">&#9776;</button>',
        "",
        "<!-- Font size controls -->",
        '<div class="font-size-controls">',
        '  <button id="font-smaller" aria-label="Decrease font size">&minus;</button>',
        '  <button id="font-larger" aria-label="Increase font size">&plus;</button>',
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

    current_part_it = ""
    current_part_en = ""

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

        # Page citation with overlay trigger
        ia_link = ""
        page_label = ""
        if pair["page_range"]:
            raw_start, end = pair["page_range"]
            # Chapter page ranges overlap: start page is shared with the
            # previous chapter's last page.  Bump by 1 so the link opens
            # on this chapter's own first page (except for the very first
            # chapter, where there is no prior overlap).
            start = raw_start + 1 if raw_start > 7 else raw_start
            ia_url = source_pages.get((raw_start, end), "")
            if not ia_url:
                ia_url = f"https://archive.org/details/{IA_ITEM_ID}/page/n{start - 1}/mode/1up"
            book_start = start - PDF_PAGE_OFFSET
            book_end = end - PDF_PAGE_OFFSET
            page_label = f"pp. {book_start}\u2013{book_end}"
            ia_link = (
                f'<a href="#" class="page-citation" '
                f'data-page-start="{start}" data-page-end="{end}" '
                f'data-page-offset="{PDF_PAGE_OFFSET}" '
                f'data-ia-url="{ia_url}" '
                f'data-img-dir="{page_img_rel}" '
                f'title="View original scan">{page_label}</a>'
            )

        part_prefix = re.sub(r"[^a-z0-9]", "-", current_part_it.lower()).strip("-") + "-" if current_part_it else ""
        ch_id = part_prefix + re.sub(r"[^a-z0-9]", "-", pair["italian_title"].lower()).strip("-")
        part_label_it = f'<span class="part-label">{_escape_html(current_part_it)}</span>' if current_part_it else ""
        part_label_en = f'<span class="part-label">{_escape_html(current_part_en)}</span>' if current_part_en else ""
        html_parts.extend([
            f'<section class="chapter" id="ch-{ch_id}">',
            '  <div class="chapter-header">',
            '    <div class="spread chapter-title-spread">',
            f'      <div class="chapter-title-col" lang="it">{part_label_it}<{level_tag} class="chapter-title">{_escape_html(pair["italian_title"])}</{level_tag}></div>',
            f'      <div class="chapter-title-col" lang="en">{part_label_en}<{level_tag} class="chapter-title">{_escape_html(pair["english_title"])}</{level_tag}></div>' if pair["english_title"] else '      <div class="chapter-title-col"></div>',
            '    </div>',
            f'    <span class="page-ref">{ia_link}</span>' if ia_link else "",
            "  </div>",
            '  <div class="spread">',
            '    <div class="verso" lang="it">',
        ])

        # Italian paragraphs
        for p in pair["italian_paragraphs"]:
            html_parts.append(f"      <p>{_para_to_html(p)}</p>")

        html_parts.extend([
            "    </div>",
            '    <div class="recto" lang="en">',
        ])

        # English paragraphs
        for p in pair["english_paragraphs"]:
            html_parts.append(f"      <p>{_para_to_html(p)}</p>")

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
        f'  1913 first edition published by Canessa Printing Co., reconciled via three-way',
        "  collation with a Gemini Pro vision-OCR witness, and translated by Claude Sonnet 4.6 (Anthropic).</p>",
        "  <p>Translation processing by Ben Rossi on March 30, 2026.</p>",
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
        "  const title = document.getElementById('page-overlay-title');",
        "  const iaLink = document.getElementById('page-overlay-ia-link');",
        "  const closeBtn = document.getElementById('page-overlay-close');",
        "  const prevBtn = document.getElementById('page-overlay-prev');",
        "  const nextBtn = document.getElementById('page-overlay-next');",
        "  let currentPage = 0, startPage = 0, endPage = 0, imgDir = '', pageOffset = 0;",
        "",
        "  function showPage(n) {",
        "    currentPage = Math.max(startPage, Math.min(n, endPage));",
        "    const padded = String(currentPage).padStart(4, '0');",
        "    img.src = imgDir + '/page_' + padded + '.png';",
        "    title.textContent = 'Page ' + (currentPage - pageOffset);",
        "    prevBtn.disabled = currentPage <= startPage;",
        "    nextBtn.disabled = currentPage >= endPage;",
        "    const iaBase = 'https://archive.org/details/' + '" + IA_ITEM_ID + "' + '/page/n' + (currentPage - 1) + '/mode/1up';",
        "    iaLink.href = iaBase;",
        "  }",
        "",
        "  document.querySelectorAll('.page-citation').forEach(a => {",
        "    a.addEventListener('click', e => {",
        "      e.preventDefault();",
        "      startPage = parseInt(a.dataset.pageStart);",
        "      endPage = parseInt(a.dataset.pageEnd);",
        "      pageOffset = parseInt(a.dataset.pageOffset || '0');",
        "      imgDir = a.dataset.imgDir;",
        "      showPage(startPage);",
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
        "  document.querySelectorAll('.part-page, section.chapter').forEach(el => {",
        "    if (el.classList.contains('part-page')) {",
        "      const h2 = el.querySelector('h2[lang=\"en\"]') || el.querySelector('h2');",
        "      if (!h2) return;",
        "      const li = document.createElement('li');",
        "      li.className = 'toc-part';",
        "      const a = document.createElement('a');",
        "      a.href = '#' + el.id;",
        "      a.textContent = h2.textContent;",
        "      a.addEventListener('click', () => { panel.classList.remove('open'); backdrop.classList.remove('open'); });",
        "      li.appendChild(a);",
        "      list.appendChild(li);",
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
        "    a.addEventListener('click', () => { panel.classList.remove('open'); backdrop.classList.remove('open'); });",
        "    li.appendChild(a);",
        "    list.appendChild(li);",
        "  });",
        "",
        "  // Add colophon link",
        "  const cLi = document.createElement('li');",
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


def typeset(output_dir: Path) -> None:
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
    )

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
