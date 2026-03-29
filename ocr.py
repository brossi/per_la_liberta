"""Step 2a: Generate third OCR witness using Gemini Flash on the LOC PDF scan.

Renders each PDF page to an image, sends it to Gemini Flash for OCR,
and produces copy3_raw.txt with embedded page markers plus a page map JSON.
"""

import io
import json
import os
import time
from pathlib import Path

from PIL import Image


# Default PDF path (LOC scan, gitignored)
DEFAULT_PDF = "public-gdcmassbookdig-perlalibertdal00cres-perlalibertdal00cres.pdf"

# Page marker format embedded in copy3_raw.txt
PAGE_MARKER = "\u27e8PAGE:{}\u27e9"  # ⟨PAGE:N⟩

GEMINI_MODELS = {
    "flash": "gemini-2.5-flash",
    "pro": "gemini-3.1-pro-preview",
}

OCR_PROMPT = (
    "Transcribe all the text on this page exactly as printed. "
    "This is a page from a 1913 Italian book titled 'Per la libertà!' by Cesare Crespi. "
    "Rules:\n"
    "- Output only the text content, no commentary\n"
    "- Preserve line breaks as they appear on the page\n"
    "- Preserve all accented characters (à, è, ì, ò, ù, é)\n"
    "- Preserve punctuation exactly\n"
    "- If the page has a page number, include it on its own line\n"
    "- If the page is blank or has only decorative elements, output [BLANK]\n"
    "- Do not translate — output the Italian text as printed"
)


def _render_page(pdf_path: Path, page_num: int, *, dpi: int = 200) -> bytes:
    """Render a single PDF page to JPEG bytes."""
    import fitz

    doc = fitz.open(str(pdf_path))
    page = doc[page_num - 1]
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _get_page_count(pdf_path: Path) -> int:
    """Get total page count of a PDF."""
    import fitz

    doc = fitz.open(str(pdf_path))
    count = len(doc)
    doc.close()
    return count


def _ocr_page(client, img_bytes: bytes, model: str = "pro") -> str:
    """Send a page image to Gemini and get OCR text back."""
    from google.genai import types

    model_id = GEMINI_MODELS[model]
    response = client.models.generate_content(
        model=model_id,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    types.Part.from_text(text=OCR_PROMPT),
                ],
            )
        ],
    )
    return response.text.strip()


def ocr_pdf(pdf_path: Path, output_path: Path, *,
            page_range: tuple[int, int] | None = None,
            api_key: str | None = None,
            model: str = "pro",
            workers: int = 1) -> Path:
    """Run Gemini OCR on a PDF and write text + page map.

    Args:
        pdf_path: Path to the LOC scan PDF.
        output_path: Where to write the OCR text.
        page_range: Optional (start, end) 1-indexed page range.
        api_key: Gemini API key (or set GEMINI_API_KEY env var).
        model: "flash" for speed/page mapping, "pro" for quality third witness.
        workers: Number of concurrent OCR workers (default 1).

    Returns:
        output_path
    """
    from google import genai

    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("No Gemini API key. Set GEMINI_API_KEY or pass --api-key.")

    client = genai.Client(api_key=api_key)

    total_pages = _get_page_count(pdf_path)
    start = 1
    end = total_pages

    if page_range:
        start, end = page_range
        end = min(end, total_pages)

    page_count = end - start + 1
    model_id = GEMINI_MODELS[model]

    # Resume support: store per-page results in a progress directory
    progress_dir = output_path.parent / f"ocr_{model}_pages"
    progress_dir.mkdir(parents=True, exist_ok=True)

    # Find pages that still need processing
    completed = {
        int(f.stem.split("_")[1])
        for f in progress_dir.glob("page_*.json")
    }
    all_pages = list(range(start, end + 1))
    todo = [p for p in all_pages if p not in completed]

    if completed:
        print(f"  OCR [{model}]: resuming — {len(completed)} done, {len(todo)} remaining"
              + (f", {workers} workers" if workers > 1 else ""))
    else:
        print(f"  OCR [{model}]: {page_count} pages via {model_id}"
              + (f", {workers} workers" if workers > 1 else ""))

    if not todo:
        print("  All pages already complete")
    elif workers <= 1:
        _ocr_pages_sequential(client, pdf_path, todo, progress_dir, model, page_count)
    else:
        _ocr_pages_parallel(client, pdf_path, todo, progress_dir, model, page_count, workers)

    # Stitch per-page results into final output
    return _stitch_pages(progress_dir, start, end, output_path, model)

def _ocr_single_page(client, pdf_path: Path, page_num: int,
                      progress_dir: Path, model: str) -> int:
    """OCR a single page with retry. Returns page_num on success."""
    page_file = progress_dir / f"page_{page_num:04d}.json"
    if page_file.exists():
        return page_num

    img_bytes = _render_page(pdf_path, page_num)

    text = None
    for attempt in range(3):
        try:
            text = _ocr_page(client, img_bytes, model=model)
            break
        except Exception as e:
            if attempt < 2:
                delay = [2, 8, 16][attempt]
                time.sleep(delay)
            else:
                text = f"[OCR_ERROR: {e}]"

    page_file.write_text(
        json.dumps({"page": page_num, "text": text or ""}, ensure_ascii=False),
        encoding="utf-8",
    )
    return page_num


def _ocr_pages_sequential(client, pdf_path, todo, progress_dir, model, page_count):
    """Process pages one at a time."""
    bar_width = 30
    done_count = page_count - len(todo)

    for page_num in todo:
        done_count += 1
        filled = int(bar_width * (done_count / page_count))
        bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
        print(f"\r  [{bar}] {done_count}/{page_count}  page {page_num}", end="", flush=True)

        _ocr_single_page(client, pdf_path, page_num, progress_dir, model)
        time.sleep(0.2)

    print(f"\r  [{'█' * bar_width}] {page_count}/{page_count}  done!{' ' * 20}")


def _ocr_pages_parallel(client, pdf_path, todo, progress_dir, model, page_count, workers):
    """Process pages concurrently with a thread pool."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    bar_width = 30
    done_count = page_count - len(todo)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_ocr_single_page, client, pdf_path, p, progress_dir, model): p
            for p in todo
        }
        for future in as_completed(futures):
            done_count += 1
            page_num = futures[future]
            filled = int(bar_width * (done_count / page_count))
            bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
            print(f"\r  [{bar}] {done_count}/{page_count}", end="", flush=True)

            try:
                future.result()
            except Exception as e:
                print(f"\n    Error on page {page_num}: {e}")

    print(f"\r  [{'█' * bar_width}] {page_count}/{page_count}  done!{' ' * 20}")


def _stitch_pages(progress_dir: Path, start: int, end: int,
                  output_path: Path, model: str) -> Path:
    """Stitch per-page JSON files into final output text + page map."""
    # Stitch all pages into final output
    parts = []
    page_map = []
    pos = 0

    for page_num in range(start, end + 1):
        page_file = progress_dir / f"page_{page_num:04d}.json"
        page_data = json.loads(page_file.read_text(encoding="utf-8"))
        text = page_data["text"]

        marker = PAGE_MARKER.format(page_num) + "\n"
        parts.append(marker)
        pos += len(marker)

        char_start = pos

        if text and text != "[BLANK]" and not text.startswith("[OCR_ERROR"):
            parts.append(text + "\n")
            pos += len(text) + 1

        parts.append("\n")
        pos += 1

        page_map.append({
            "page": page_num,
            "char_start": char_start,
            "char_end": pos - 1,
        })

    full_text = "".join(parts)

    # Write final outputs
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(full_text, encoding="utf-8")
    print(f"  OCR text: {output_path} ({len(full_text):,} chars)")

    page_map_path = output_path.parent / f"copy3_{model}_page_map.json"
    page_map_path.write_text(
        json.dumps(page_map, indent=2), encoding="utf-8"
    )
    print(f"  Page map: {page_map_path} ({len(page_map)} pages)")

    return output_path


def ocr_benchmark(pdf_path: Path, pages: list[int], api_key: str | None = None,
                   model: str = "pro") -> None:
    """OCR a few pages and print results for quality assessment."""
    from google import genai

    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("No Gemini API key. Set GEMINI_API_KEY or pass --api-key.")

    client = genai.Client(api_key=api_key)

    for page_num in pages:
        img_bytes = _render_page(pdf_path, page_num)
        text = _ocr_page(client, img_bytes, model=model)

        print(f"\n{'=' * 60}")
        print(f"  PAGE {page_num} [{model}]")
        print(f"{'=' * 60}")
        print(text)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Gemini OCR on the LOC PDF scan")
    parser.add_argument("--model", choices=["flash", "pro"], default="pro",
                        help="Gemini model: flash (fast/page mapping) or pro (quality)")
    parser.add_argument("--workers", type=int, default=1,
                        help="Concurrent OCR workers (default: 1, try 4-8 for Pro)")
    parser.add_argument("--benchmark", nargs="+", type=int,
                        help="Benchmark specific page numbers (e.g., --benchmark 50 51 52)")
    parser.add_argument("--pages", nargs=2, type=int, metavar=("START", "END"),
                        help="Only OCR pages START through END (1-indexed)")
    parser.add_argument("--api-key", help="Gemini API key (or set GEMINI_API_KEY env var)")
    args = parser.parse_args()

    base = Path(__file__).parent
    pdf_path = base / DEFAULT_PDF

    if not pdf_path.exists():
        print(f"Error: PDF not found at {pdf_path}")
        raise SystemExit(1)

    if args.benchmark:
        ocr_benchmark(pdf_path, args.benchmark, api_key=args.api_key, model=args.model)
    else:
        # Flash → copy3_flash.txt (page mapping), Pro → copy3_raw.txt (quality witness)
        if args.model == "flash":
            output_path = base / "data" / "copy3_flash.txt"
        else:
            output_path = base / "data" / "copy3_raw.txt"

        if output_path.exists():
            print(f"  {output_path.name} already exists ({output_path.stat().st_size:,} bytes)")
            print("  Delete it to re-run OCR.")
        else:
            ocr_pdf(pdf_path, output_path, page_range=tuple(args.pages) if args.pages else None,
                    api_key=args.api_key, model=args.model, workers=args.workers)
