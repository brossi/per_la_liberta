"""download step — scaffold stub.

Ported from the top-level ``download.py`` in M4a. The real signature is
``run(ws: BookWorkspace, cfg: ResolvedConfig, lang: LanguagePlugin, **opts)``:
the step takes the workspace + resolved config + active language plugin and
replaces every book/scan/language constant with a ``cfg.*`` / ``lang.*`` read.
"""

from __future__ import annotations

PORTED_IN = "M4a"


def run(*args, **kwargs):
    raise NotImplementedError(
        "engine.steps.download.run is an M0 scaffold stub; ported in M4a."
    )
