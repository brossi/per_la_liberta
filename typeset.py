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

            # Skip structural-only headers
            if title in ("Per la Libertà!", "For Freedom!"):
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
    """Split text into paragraphs on blank lines."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return paras


def _align_chapters(italian_chapters: list[dict], english_chapters: list[dict]) -> list[dict]:
    """Align Italian and English chapters by position into bilingual pairs."""
    # Filter out structural headers (Parte Prima, Part One, etc.)
    structural = {"Parte Prima", "Parte Seconda", "Part One", "Part Two"}

    it_content = [ch for ch in italian_chapters if ch["title"] not in structural]
    en_content = [ch for ch in english_chapters if ch["title"] not in structural]

    pairs = []
    for i in range(max(len(it_content), len(en_content))):
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
        '<div class="title-page">',
        '<h1 class="title-it" lang="it">Per la Libertà!</h1>',
        '<h1 class="title-en" lang="en">For Freedom!</h1>',
        '<p class="subtitle" lang="it">Dalle mie conversazioni col Conte Carlo di Rudio,<br>complice di Felice Orsini</p>',
        '<p class="subtitle" lang="en">From my conversations with Count Carlo di Rudio,<br>accomplice of Felice Orsini</p>',
        '<p class="author">Cesare Crespi (1913)</p>',
        "</div>",
        "",
    ]

    current_part_it = None

    for pair in pairs:
        # Detect part transitions
        title = pair["italian_title"]
        if pair["level"] == 2 and title not in ("Prefazione",):
            # Part header — render as a separator page
            en_title = pair["english_title"]
            html_parts.extend([
                '<div class="part-page">',
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
            start, end = pair["page_range"]
            ia_url = source_pages.get((start, end), "")
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

        html_parts.extend([
            '<section class="chapter">',
            '  <div class="chapter-header">',
            f'    <{level_tag} class="chapter-title">',
            f'      <span lang="it">{_escape_html(pair["italian_title"])}</span>',
            f'      <span lang="en">{_escape_html(pair["english_title"])}</span>' if pair["english_title"] else "",
            f"    </{level_tag}>",
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
        '<div class="colophon">',
        "  <h2>Colophon</h2>",
        "  <p>This bilingual edition was produced from two independent OCR scans of the",
        f'  1913 first edition published by Canessa Printing Co., reconciled via three-way',
        "  collation with a Gemini Pro vision-OCR witness, and translated by Claude (Anthropic).</p>",
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

    # Generate PDF
    pdf_path = output_dir / "bilingual.pdf"
    try:
        generate_pdf(html_path, pdf_path)
    except ImportError:
        print("  Warning: weasyprint not installed — skipping PDF generation")
        print("  Install with: uv add weasyprint")
    except Exception as e:
        print(f"  PDF generation failed: {e}")


if __name__ == "__main__":
    base = Path(__file__).parent
    typeset(base / "output")
