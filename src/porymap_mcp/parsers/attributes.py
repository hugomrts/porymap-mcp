"""Parser for ``data/tilesets/<kind>/<name>/metatile_attributes.bin``.

Each metatile carries a small bitfield ("attributes") indicating its
behavior (e.g. tall grass, water, ledge), terrain type, encounter type,
and layer type. The on-disk size and bit layout vary by project:

  - **Vanilla RSE / pokeemerald (size=2):** 16-bit word per metatile,
    with masks defined in ``porymap.project.cfg``. The expansion fork
    typically uses ``size=4`` and 32-bit words for wider fields.
  - **Masks come from :class:`ProjectConfig`** (ADR-0003 §"Decision");
    we never branch on ``base_game_version`` here.

References:
  - Porymap source: ``src/core/metatile.cpp`` (attribute decoding).
  - Field masks: ``porymap.project.cfg``'s ``metatile_*_mask`` keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from porymap_mcp.errors import FormatError

SUPPORTED_ATTRIBUTE_SIZES: Final = (1, 2, 4)


@dataclass(frozen=True, slots=True)
class AttributeMasks:
    """Bit masks for each attribute field, as declared by the project.

    Built from :attr:`ProjectConfig.metatile_behavior_mask` etc. A mask
    of ``0`` means the field is unused in this project (we then emit
    ``0`` for the decoded value and the field is simply uninformative).
    """

    behavior: int
    terrain_type: int
    encounter_type: int
    layer_type: int


@dataclass(frozen=True, slots=True)
class MetatileAttributes:
    """Decoded attribute fields for a single metatile.

    Each field is the value extracted by ``(raw & mask) >> shift``,
    where ``shift`` is the position of the lowest set bit of ``mask``.
    The :attr:`raw` int is the verbatim attribute word — useful when a
    fork uses extra bits we do not yet name.
    """

    behavior: int
    terrain_type: int
    encounter_type: int
    layer_type: int
    raw: int


def _shift_of(mask: int) -> int:
    """Return the bit position of the lowest set bit in ``mask`` (0 if mask=0)."""
    if mask == 0:
        return 0
    return (mask & -mask).bit_length() - 1


def decode(raw: int, masks: AttributeMasks) -> MetatileAttributes:
    """Decode a single raw attribute word using ``masks``."""
    return MetatileAttributes(
        behavior=(raw & masks.behavior) >> _shift_of(masks.behavior),
        terrain_type=(raw & masks.terrain_type) >> _shift_of(masks.terrain_type),
        encounter_type=(raw & masks.encounter_type) >> _shift_of(masks.encounter_type),
        layer_type=(raw & masks.layer_type) >> _shift_of(masks.layer_type),
        raw=raw,
    )


def read(
    data: bytes,
    *,
    attribute_size: int,
    masks: AttributeMasks,
    expected_count: int | None = None,
) -> tuple[MetatileAttributes, ...]:
    """Decode all metatile attributes in ``data``.

    Args:
      data: raw bytes from ``metatile_attributes.bin``.
      attribute_size: 1, 2, or 4 — per-metatile byte size (from
        :attr:`ProjectConfig.metatile_attributes_size`).
      masks: bit-mask layout from :class:`AttributeMasks`.
      expected_count: optional — when provided, cross-check the file
        size against an externally-known metatile count.

    Raises:
      FormatError: bad ``attribute_size`` or size mismatch.
    """
    if attribute_size not in SUPPORTED_ATTRIBUTE_SIZES:
        raise FormatError(
            f"metatile_attributes.bin: unsupported attribute_size {attribute_size}. "
            f"Supported: {SUPPORTED_ATTRIBUTE_SIZES}."
        )
    if len(data) % attribute_size != 0:
        raise FormatError(
            f"metatile_attributes.bin: size {len(data)} bytes is not a "
            f"multiple of {attribute_size}."
        )
    count = len(data) // attribute_size
    if expected_count is not None and count != expected_count:
        raise FormatError(
            f"metatile_attributes.bin: file declares {count} attributes but "
            f"the tileset has {expected_count} metatiles."
        )
    out: list[MetatileAttributes] = []
    for i in range(count):
        chunk = data[i * attribute_size : (i + 1) * attribute_size]
        raw = int.from_bytes(chunk, "little")
        out.append(decode(raw, masks))
    return tuple(out)
