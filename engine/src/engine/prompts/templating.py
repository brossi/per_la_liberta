"""Jinja2 StrictUndefined PromptTemplate. Scaffold stub (deferred M1 → M4).

Deferred to M4 deliberately: its first consumer is an OCR/translate prompt, and the
prompt-leakage genericity test (plan §"hard cases") needs real templates plus a non-PLL
fixture to bite. Built then, co-located with its first template, so its shape is
consumer-informed rather than guessed."""

from __future__ import annotations
