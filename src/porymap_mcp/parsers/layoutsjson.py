"""Parser/serializer for ``data/layouts/layouts.json``.

Format (per Porymap source: ``Project::readMapLayouts`` and
``Project::saveMapLayouts`` in ``porymap/src/project.cpp``):

Top-level JSON object with exactly two keys, in this order:

  1. ``layouts_table_label`` — string, typically ``"gMapLayouts"`` (the C
     symbol of the layouts table).
  2. ``layouts`` — array of per-layout objects.

Each layout object has these keys (Porymap writes them in this exact order via
``OrderedJson``):

  ``id``, ``name``, ``width``, ``height``,
  (``border_width``, ``border_height``) — only when
      ``use_custom_border_size=1`` in ``porymap.project.cfg``,
  ``primary_tileset``, ``secondary_tileset``,
  ``border_filepath``, ``blockdata_filepath``

Tileset references are by C symbol name (e.g. ``gTileset_General``), not by
path or by friendly name. Resolution to ``tilesets/headers.json`` happens at
the ``Project`` layer, not here.

Formatting conventions:
  - 2-space indent, single trailing newline at EOF, LF line endings.
  - Path strings are POSIX, relative to the project root.
  - Layout array order is preserved verbatim — Porymap appends new layouts at
    the end and does not re-sort.

References:
  - Porymap reader: ``Project::readMapLayouts`` in
    ``porymap/src/project.cpp``.
  - pokeemerald canonical fixture:
    https://github.com/pret/pokeemerald/blob/master/data/layouts/layouts.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final

from porymap_mcp.errors import LayoutsJsonFormatError

_REQUIRED_KEYS: Final = (
    "id",
    "name",
    "width",
    "height",
    "primary_tileset",
    "secondary_tileset",
    "border_filepath",
    "blockdata_filepath",
)


@dataclass(frozen=True, slots=True)
class LayoutEntry:
    """One layout entry in ``layouts.json``.

    ``border_width`` / ``border_height`` are ``None`` for projects without
    custom border size (``use_custom_border_size=0``). They must be either
    both set or both ``None``; mixed presence is a format error.
    """

    id: str
    name: str
    width: int
    height: int
    primary_tileset: str
    secondary_tileset: str
    border_filepath: str
    blockdata_filepath: str
    border_width: int | None = None
    border_height: int | None = None

    def __post_init__(self) -> None:
        if (self.border_width is None) != (self.border_height is None):
            raise LayoutsJsonFormatError(
                f"layout {self.id!r}: border_width and border_height "
                "must both be present or both absent"
            )
        if self.width <= 0 or self.height <= 0:
            raise LayoutsJsonFormatError(
                f"layout {self.id!r}: width and height must be positive "
                f"(got {self.width}x{self.height})"
            )
        if self.border_width is not None and self.border_width <= 0:
            raise LayoutsJsonFormatError(
                f"layout {self.id!r}: border_width must be positive "
                f"(got {self.border_width})"
            )
        if self.border_height is not None and self.border_height <= 0:
            raise LayoutsJsonFormatError(
                f"layout {self.id!r}: border_height must be positive "
                f"(got {self.border_height})"
            )


@dataclass(frozen=True, slots=True)
class LayoutsJson:
    """The decoded ``data/layouts/layouts.json`` document."""

    layouts_table_label: str
    layouts: tuple[LayoutEntry, ...]


# --- read ------------------------------------------------------------------


def read(text: str) -> LayoutsJson:
    """Parse ``layouts.json`` text into a :class:`LayoutsJson`.

    Raises:
        LayoutsJsonFormatError: invalid JSON, wrong top-level shape, missing
            required keys, ``null`` layout entry, or a layout entry with
            mismatched ``border_*`` presence.
    """
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LayoutsJsonFormatError(f"invalid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise LayoutsJsonFormatError(
            f"top-level value must be an object, got {_typename(raw)}"
        )

    if "layouts_table_label" not in raw:
        raise LayoutsJsonFormatError("missing top-level key 'layouts_table_label'")
    if "layouts" not in raw:
        raise LayoutsJsonFormatError("missing top-level key 'layouts'")

    label = raw["layouts_table_label"]
    if not isinstance(label, str):
        raise LayoutsJsonFormatError(
            f"'layouts_table_label' must be a string, got {_typename(label)}"
        )

    raw_layouts = raw["layouts"]
    if not isinstance(raw_layouts, list):
        raise LayoutsJsonFormatError(
            f"'layouts' must be an array, got {_typename(raw_layouts)}"
        )

    layouts: list[LayoutEntry] = []
    for index, entry in enumerate(raw_layouts):
        layouts.append(_read_entry(entry, index))

    return LayoutsJson(layouts_table_label=label, layouts=tuple(layouts))


def _read_entry(entry: object, index: int) -> LayoutEntry:
    if entry is None:
        raise LayoutsJsonFormatError(
            f"layouts[{index}] is null (legacy placeholder); not supported"
        )
    if not isinstance(entry, dict):
        raise LayoutsJsonFormatError(
            f"layouts[{index}] must be an object, got {_typename(entry)}"
        )

    missing = [k for k in _REQUIRED_KEYS if k not in entry]
    if missing:
        raise LayoutsJsonFormatError(
            f"layouts[{index}] missing required keys: {', '.join(missing)}"
        )

    return LayoutEntry(
        id=_expect_str(entry["id"], index, "id"),
        name=_expect_str(entry["name"], index, "name"),
        width=_expect_int(entry["width"], index, "width"),
        height=_expect_int(entry["height"], index, "height"),
        primary_tileset=_expect_str(entry["primary_tileset"], index, "primary_tileset"),
        secondary_tileset=_expect_str(
            entry["secondary_tileset"], index, "secondary_tileset"
        ),
        border_filepath=_expect_str(entry["border_filepath"], index, "border_filepath"),
        blockdata_filepath=_expect_str(
            entry["blockdata_filepath"], index, "blockdata_filepath"
        ),
        border_width=_expect_optional_int(
            entry.get("border_width"), index, "border_width"
        ),
        border_height=_expect_optional_int(
            entry.get("border_height"), index, "border_height"
        ),
    )


def _expect_str(value: object, index: int, key: str) -> str:
    if not isinstance(value, str):
        raise LayoutsJsonFormatError(
            f"layouts[{index}].{key}: expected string, got {_typename(value)}"
        )
    return value


def _expect_int(value: object, index: int, key: str) -> int:
    # ``bool`` is a subclass of ``int`` in Python; reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, int):
        raise LayoutsJsonFormatError(
            f"layouts[{index}].{key}: expected integer, got {_typename(value)}"
        )
    return value


def _expect_optional_int(value: object, index: int, key: str) -> int | None:
    if value is None:
        return None
    return _expect_int(value, index, key)


def _typename(value: object) -> str:
    return type(value).__name__


# --- write -----------------------------------------------------------------


def write(doc: LayoutsJson) -> str:
    """Serialize a :class:`LayoutsJson` to canonical Porymap JSON text.

    Produces a 2-space-indented JSON document with a single trailing LF,
    matching what Porymap writes via ``OrderedJson``. Key order inside each
    layout object follows Porymap's canonical order; ``border_width`` and
    ``border_height`` are emitted only when both are set.
    """
    layouts_payload: list[dict[str, object]] = []
    for entry in doc.layouts:
        obj: dict[str, object] = {
            "id": entry.id,
            "name": entry.name,
            "width": entry.width,
            "height": entry.height,
        }
        if entry.border_width is not None and entry.border_height is not None:
            obj["border_width"] = entry.border_width
            obj["border_height"] = entry.border_height
        obj["primary_tileset"] = entry.primary_tileset
        obj["secondary_tileset"] = entry.secondary_tileset
        obj["border_filepath"] = entry.border_filepath
        obj["blockdata_filepath"] = entry.blockdata_filepath
        layouts_payload.append(obj)

    payload: dict[str, object] = {
        "layouts_table_label": doc.layouts_table_label,
        "layouts": layouts_payload,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
