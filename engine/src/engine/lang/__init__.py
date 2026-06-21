"""LanguagePlugin ABC + per-language implementations.

The core imports only ``get_language_plugin`` + the ``LanguagePlugin`` type; concrete
plugins (Italian, …) are reached through the registry, never directly.
"""

from __future__ import annotations

from .base import LanguagePlugin
from .registry import available_languages, get_language_plugin

__all__ = ["LanguagePlugin", "get_language_plugin", "available_languages"]
