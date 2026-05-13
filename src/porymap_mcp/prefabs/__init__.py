"""Built-in prefab library for ``paint_prefab`` (ADR-0008).

Prefabs are declared as :class:`Prefab` dataclass instances in
:mod:`porymap_mcp.prefabs.library`. The public surface is:

  - :class:`Prefab` and :class:`PrefabTile` types.
  - :data:`LIBRARY` — the canonical registry.
  - :func:`get` — convenience accessor.
"""

from __future__ import annotations

from porymap_mcp.prefabs.library import LIBRARY, Prefab, PrefabTile, get

__all__ = ["LIBRARY", "Prefab", "PrefabTile", "get"]
