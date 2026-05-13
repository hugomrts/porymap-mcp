"""Pure parsers/serializers for pokeemerald-family on-disk formats.

Modules in this package are side-effect-free: each exposes ``read(...)`` and
``write(...)`` functions over ``bytes`` (or string/dict for text formats),
with no logging, no global state, no I/O outside the explicit read/write
entry points. The MCP tool layer composes them.

See ``.claude/agents/porymap-format-expert.md`` for the authoritative format
references this code targets.
"""

from __future__ import annotations
