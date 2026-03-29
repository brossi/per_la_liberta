"""Step 1: Download both OCR texts from Internet Archive."""

import requests
from pathlib import Path

COPY1_URL = "https://archive.org/download/perlalibertdal00cres/perlalibertdal00cres_djvu.txt"
COPY2_URL = "https://archive.org/download/perlalibertdall00cresgoog/perlalibertdall00cresgoog_djvu.txt"


def download_texts(data_dir: Path) -> tuple[Path, Path]:
    data_dir.mkdir(parents=True, exist_ok=True)
    copy1_path = data_dir / "copy1_raw.txt"
    copy2_path = data_dir / "copy2_raw.txt"

    for path, url, label in [
        (copy1_path, COPY1_URL, "Copy 1 (LOC)"),
        (copy2_path, COPY2_URL, "Copy 2 (Google/Harvard)"),
    ]:
        if path.exists():
            print(f"  {label}: already downloaded ({path.stat().st_size:,} bytes)")
            continue
        print(f"  {label}: downloading...")
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        path.write_text(resp.text, encoding="utf-8")
        print(f"  {label}: saved ({len(resp.text):,} chars)")

    return copy1_path, copy2_path


if __name__ == "__main__":
    download_texts(Path(__file__).parent / "data")
