"""Kho tri thuc ky thuat tan cong cong cho RedLine (Week 2).

Public API:
    load_knowledge()   -> dict goc cua knowledge_base.json
    load_entries()     -> danh sach entry da gan type (owasp | atlas | technique)
    search_knowledge() -> tim kiem deterministic theo ten ky thuat/alias/ma OWASP-ATLAS
    find_by_id()       -> tra cuu chinh xac theo entry id
"""

from __future__ import annotations

from typing import Any

_EXPORTS = (
    "KNOWLEDGE_PATH",
    "find_by_id",
    "load_entries",
    "load_knowledge",
    "search_knowledge",
)

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    """Lazy import de ``python -m redteam.attacks.knowledge.search`` khong bi warning."""

    if name in _EXPORTS:
        from redteam.attacks.knowledge import search as _search

        return getattr(_search, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
