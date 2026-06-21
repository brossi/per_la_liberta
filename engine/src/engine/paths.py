"""``BookWorkspace`` — every generated artifact lives under ``books/<id>/work/``.

This is the isolation primitive the whole forward-fork rests on (plan §"Keeping the live
edition safe"): the engine must never write into the live PLL tree (``data/``, ``output/``,
``state/``, …) at the repo root. A step asks the workspace for an output path via
``resolve``, which *asserts the path stays inside the work tree* and raises on any escape
(``..`` traversal or an absolute path). The three areas mirror the live pipeline's
``DATA_DIR``/``OUTPUT_DIR``/``STATE_DIR`` seam (``pipeline.py:12-15``), now per-book and
sandboxed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# paths.py -> engine(pkg) -> src -> engine/ (project root)
ENGINE_ROOT = Path(__file__).resolve().parents[2]

#: Root for read-only heavy assets. During dev these are symlinks into the live tree
#: (``assets/dictionary`` → period dicts, ``assets/frequency`` → the frequency dict,
#: ``assets/fonts`` → OFL fonts); at extraction they become real copies. Resolving every
#: asset path through here keeps symlink-vs-copy invisible to step code (plan §"Heavy assets").
ASSETS_ROOT = ENGINE_ROOT / "assets"


def asset_path(rel: str) -> Path:
    """Resolve an assets-relative path (e.g. ``"frequency/it_combined.txt"``) to absolute.

    Does not assert existence — callers that require the file present check it (and
    ``tests/unit/test_assets.py`` asserts every config-referenced asset resolves).
    """
    return ASSETS_ROOT / rel


_AREAS = ("data", "output", "state")


@dataclass(frozen=True, slots=True)
class BookWorkspace:
    book_id: str
    root: Path  # books/<id>/work

    @classmethod
    def for_book(cls, book_id: str, books_dir: Path) -> BookWorkspace:
        return cls(book_id=book_id, root=(Path(books_dir) / book_id / "work").resolve())

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def state(self) -> Path:
        return self.root / "state"

    def ensure(self) -> BookWorkspace:
        """Create the work tree (the three areas). Idempotent."""
        for area in _AREAS:
            (self.root / area).mkdir(parents=True, exist_ok=True)
        return self

    def resolve(self, area: str, *parts: str) -> Path:
        """Resolve ``<work>/<area>/<*parts>``, guaranteeing the result stays in the work tree.

        Raises ``ValueError`` for an unknown area, an absolute part, or any ``..`` traversal
        that would escape ``root`` — the assertion that makes the live tree unreachable.
        """
        if area not in _AREAS:
            raise ValueError(f"unknown workspace area {area!r}; expected one of {_AREAS}")
        if any(Path(p).is_absolute() for p in parts):
            raise ValueError(f"workspace path parts must be relative, got {parts!r}")

        candidate = (self.root / area).joinpath(*parts).resolve()
        if candidate != self.root and not candidate.is_relative_to(self.root):
            raise ValueError(
                f"path {candidate} escapes workspace {self.root} (rejected)"
            )
        return candidate
