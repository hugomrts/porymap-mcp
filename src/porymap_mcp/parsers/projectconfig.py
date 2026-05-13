"""Parser/serializer for ``porymap.project.cfg``.

Format (per Porymap source: ``src/config.cpp``, classes ``ProjectConfig`` and
``KeyValueConfigBase``):

The file is an INI-lite key/value store with **no section headers**.

  - Encoding: UTF-8, LF line endings.
  - One ``key=value`` per line. Whitespace around key and value is trimmed.
  - Lines beginning with ``#`` and blank lines are comments and dropped.
  - Slashes in keys (e.g. ``path/data_map_folders``) are *namespace* indicators,
    not sections.
  - Duplicate keys: last wins (Porymap uses ``QHash``-like semantics).
  - Booleans serialize as ``0`` / ``1``. Hex values are written as ``0x...``.

The companion file ``porymap.user.cfg`` (recent maps, scroll state) is **not**
in scope here — this module only handles ``porymap.project.cfg``.

References:
  - Porymap parser: ``KeyValueConfigBase::load`` and
    ``ProjectConfig::parseConfigKeyValue`` in ``porymap/src/config.cpp``.
  - Porymap settings manual: https://huderlem.github.io/porymap/manual/settings-and-options.html
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from porymap_mcp.errors import ProjectConfigFormatError

# Currently recognized values for ``base_game_version``. pokeemerald-expansion
# projects also declare themselves as ``pokeemerald`` here — there is no
# dedicated key for the expansion (ADR-0002).
SUPPORTED_BASE_GAME_VERSIONS: Final = ("pokeruby", "pokefirered", "pokeemerald")

# Canonical defaults from Porymap when a key is absent. These mirror the
# pokeemerald (RSE) defaults; FRLG and Ruby differ on some keys but always
# write the value explicitly when they differ, so absence == RSE default.
_DEFAULT_BLOCK_METATILE_ID_MASK: Final = 0x03FF
_DEFAULT_BLOCK_COLLISION_MASK: Final = 0x0C00
_DEFAULT_BLOCK_ELEVATION_MASK: Final = 0xF000
_DEFAULT_METATILE_ATTRIBUTES_SIZE: Final = 2
_DEFAULT_METATILE_BEHAVIOR_MASK: Final = 0x00FF
_DEFAULT_METATILE_TERRAIN_TYPE_MASK: Final = 0x3E00
_DEFAULT_METATILE_ENCOUNTER_TYPE_MASK: Final = 0xC000
_DEFAULT_METATILE_LAYER_TYPE_MASK: Final = 0x6000

# Renderer-relevant defaults (see ADR-0010).
#
# Porymap's ``unusedTileNormal/Covered/Split`` default to 0 in
# ``Tileset::loadProject`` when the key is absent (``src/config.cpp:1375-1377``,
# ``Util::toHexString`` writer + ``getConfigUint32(key, value, 0, ...)`` reader).
# These are tile IDs (uint16, 10 bits used) — the renderer fills the "missing"
# layer of a dual-layer metatile with this tile per ADR-0010's composition table.
_DEFAULT_UNUSED_TILE_ID: Final = 0


@dataclass(slots=True)
class ProjectConfig:
    """In-memory representation of ``porymap.project.cfg``.

    Stored as an ordered ``dict[str, str]`` (insertion order preserved) so a
    read + write cycle preserves both the set of keys and their order. Typed
    accessors are provided as properties for the keys L1 needs to make
    decisions about parsing other files (notably the metatile/block masks and
    the base game version).

    Unknown keys are preserved in :attr:`entries` and round-trip cleanly.
    """

    entries: dict[str, str] = field(default_factory=dict)

    # --- Required-on-access typed accessors ------------------------------

    @property
    def base_game_version(self) -> str:
        """The ``base_game_version`` key. Raises if missing — this is the one
        key without a safe default."""
        try:
            return self.entries["base_game_version"]
        except KeyError as exc:
            raise ProjectConfigFormatError("missing required key 'base_game_version'") from exc

    # --- Optional typed accessors (with documented defaults) -------------

    @property
    def use_poryscript(self) -> bool:
        return _parse_bool(self.entries.get("use_poryscript", "0"), "use_poryscript")

    @property
    def use_custom_border_size(self) -> bool:
        return _parse_bool(
            self.entries.get("use_custom_border_size", "0"), "use_custom_border_size"
        )

    @property
    def enable_triple_layer_metatiles(self) -> bool:
        return _parse_bool(
            self.entries.get("enable_triple_layer_metatiles", "0"),
            "enable_triple_layer_metatiles",
        )

    @property
    def metatile_attributes_size(self) -> int:
        return _parse_int(
            self.entries.get("metatile_attributes_size", str(_DEFAULT_METATILE_ATTRIBUTES_SIZE)),
            "metatile_attributes_size",
        )

    @property
    def block_metatile_id_mask(self) -> int:
        return self._hex_or_default("block_metatile_id_mask", _DEFAULT_BLOCK_METATILE_ID_MASK)

    @property
    def block_collision_mask(self) -> int:
        return self._hex_or_default("block_collision_mask", _DEFAULT_BLOCK_COLLISION_MASK)

    @property
    def block_elevation_mask(self) -> int:
        return self._hex_or_default("block_elevation_mask", _DEFAULT_BLOCK_ELEVATION_MASK)

    @property
    def metatile_behavior_mask(self) -> int:
        return self._hex_or_default("metatile_behavior_mask", _DEFAULT_METATILE_BEHAVIOR_MASK)

    @property
    def metatile_terrain_type_mask(self) -> int:
        return self._hex_or_default(
            "metatile_terrain_type_mask", _DEFAULT_METATILE_TERRAIN_TYPE_MASK
        )

    @property
    def metatile_encounter_type_mask(self) -> int:
        return self._hex_or_default(
            "metatile_encounter_type_mask", _DEFAULT_METATILE_ENCOUNTER_TYPE_MASK
        )

    @property
    def metatile_layer_type_mask(self) -> int:
        return self._hex_or_default("metatile_layer_type_mask", _DEFAULT_METATILE_LAYER_TYPE_MASK)

    # --- Renderer-relevant accessors (ADR-0010) --------------------------

    @property
    def transparency_color(self) -> int | None:
        """RGB color used as the transparency fill for the metatile renderer.

        Porymap serializes this as a 6-digit ``RRGGBB`` hex string with **no**
        ``#`` prefix (``#`` is the project.cfg comment marker; see
        ``KeyValueConfigBase::toConfigColor`` in ``porymap/src/config.cpp``).

        Returns the 24-bit RGB value packed into an ``int`` (``0x00RRGGBB``)
        when set, or ``None`` when the key is absent or its value is the empty
        string. Porymap maps the empty case to ``QColor()`` (invalid) and the
        renderer treats that as "use palette 0 colour 0".
        """
        raw = self.entries.get("transparency_color")
        if raw is None:
            return None
        s = raw.strip()
        if not s:
            return None
        return _parse_rgb(s, "transparency_color")

    @property
    def unused_tile_normal(self) -> int:
        """Tile ID used to fill the missing bottom layer when ``LayerType``
        is ``Normal`` (dual-layer metatiles only). See ADR-0010."""
        return self._hex_or_default("unused_tile_normal", _DEFAULT_UNUSED_TILE_ID)

    @property
    def unused_tile_covered(self) -> int:
        """Tile ID used to fill the missing top layer when ``LayerType`` is
        ``Covered`` (dual-layer metatiles only). See ADR-0010."""
        return self._hex_or_default("unused_tile_covered", _DEFAULT_UNUSED_TILE_ID)

    @property
    def unused_tile_split(self) -> int:
        """Tile ID used to fill the missing middle layer when ``LayerType``
        is ``Split`` (dual-layer metatiles only). See ADR-0010."""
        return self._hex_or_default("unused_tile_split", _DEFAULT_UNUSED_TILE_ID)

    def _hex_or_default(self, key: str, default: int) -> int:
        value = self.entries.get(key)
        if value is None:
            return default
        return _parse_hex(value, key)


# --- Helpers ---------------------------------------------------------------


def _parse_bool(value: str, key: str) -> bool:
    stripped = value.strip()
    if stripped == "0":
        return False
    if stripped == "1":
        return True
    raise ProjectConfigFormatError(f"key {key!r}: expected boolean '0' or '1', got {value!r}")


def _parse_int(value: str, key: str) -> int:
    try:
        return int(value.strip(), 10)
    except ValueError as exc:
        raise ProjectConfigFormatError(
            f"key {key!r}: expected decimal integer, got {value!r}"
        ) from exc


def _parse_hex(value: str, key: str) -> int:
    s = value.strip()
    if not s:
        raise ProjectConfigFormatError(f"key {key!r}: empty hex value")
    try:
        return int(s, 16)
    except ValueError as exc:
        raise ProjectConfigFormatError(f"key {key!r}: invalid hex value {value!r}") from exc


def _parse_rgb(value: str, key: str) -> int:
    """Parse a 6-digit ``RRGGBB`` hex colour (no ``#`` prefix) into a 24-bit int.

    Empty input is handled by the caller (Porymap maps empty → invalid QColor).
    Anything other than exactly 6 hex digits raises — this matches CLAUDE.md's
    "fail fast on malformed project files" rule.
    """
    s = value.strip()
    if len(s) != 6 or not all(c in "0123456789abcdefABCDEF" for c in s):
        raise ProjectConfigFormatError(
            f"key {key!r}: expected 6-digit RGB hex 'RRGGBB' (no '#'), got {value!r}"
        )
    return int(s, 16)


# --- Top-level read / write ------------------------------------------------


def read(text: str) -> ProjectConfig:
    """Parse ``porymap.project.cfg`` text into a :class:`ProjectConfig`.

    Comments and blank lines are dropped (Porymap drops them on save too).
    Duplicate keys: the last occurrence wins.

    Raises:
        ProjectConfigFormatError: a non-empty, non-comment line did not match
            the ``key=value`` shape.
    """
    entries: dict[str, str] = {}
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ProjectConfigFormatError(f"line {lineno}: expected 'key=value', got {raw_line!r}")
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            raise ProjectConfigFormatError(f"line {lineno}: empty key in {raw_line!r}")
        entries[key] = value.strip()
    return ProjectConfig(entries=entries)


def write(config: ProjectConfig) -> str:
    """Serialize a :class:`ProjectConfig` back to text.

    Output: ``key=value\\n`` for each entry in insertion order. A single
    trailing newline is included so the file is POSIX-clean. Comments and
    blank lines from the original source are not preserved — Porymap does not
    preserve them either, so this matches upstream behavior.
    """
    return "".join(f"{key}={value}\n" for key, value in config.entries.items())
