"""Atomic JSON I/O — ported from utils.atomic_write_json (utils.py:332-341).

The atomic write (temp file + os.replace) is how every sidecar in the pipeline is
written; reproducing it byte-for-byte keeps the engine's outputs diffable against the
committed live artifacts (indent=2, ensure_ascii=False).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def read_json(path: Path):
    """Load JSON from ``path`` (UTF-8)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_write_json(path: Path, data: dict | list) -> None:
    """Write JSON atomically: temp file in the same dir, then os.replace."""
    path = Path(path)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except BaseException:
        os.unlink(tmp_path)
        raise
