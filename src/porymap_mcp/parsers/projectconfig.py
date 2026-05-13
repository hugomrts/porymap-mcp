"""Parser/serializer for ``porymap.project.cfg``.

This is Porymap's per-project configuration file. It is a flat ``key = value``
text file (no INI sections), UTF-8, LF line endings, with ``#`` comments. See
Porymap source ``src/config.cpp`` (``KeyValueConfigBase::reader`` ~L379 and
``ProjectConfig::getKeyValueMap`` ~L1238) for the canonical format.

The file carries the *format parameters* every other parser depends on
(metatile-id mask, collision/elevation masks, attribute-size, etc.). Per
ADR-0003 these are explicit fields here, not derived from ``base_game_version``
alone — that lets pokeemerald-expansion (which declares ``pokeemerald`` but
overrides the masks) flow through with no special-casing.

Public API:

* :class:`BaseGameVersion`  — the three values Porymap accepts.
* :class:`ProjectConfig`    — frozen, fully-populated config.
* :func:`parse(text)`       — pure parser; for tests and in-memory use.
* :func:`read(path)`        — disk read; raises :class:`ProjectError`.
* :func:`serialize(config)` — pure serializer.
* :func:`write(config, path)` — atomic disk write.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Final

from porymap_mcp._atomic import write_atomic
from porymap_mcp.errors import FormatError, ProjectError, UnsupportedBaseGameError


class BaseGameVersion(enum.Enum):
    """The ``base_game_version`` values Porymap writes.

    Values match Porymap's strings exactly (case-sensitive). pokeemerald-expansion
    declares ``POKEEMERALD`` and distinguishes itself via the mask/path overrides
    elsewhere in the config.
    """

    POKERUBY = "pokeruby"
    POKEFIRERED = "pokefirered"
    POKEEMERALD = "pokeemerald"


# Defaults for each base game, applied for any key omitted from the cfg.
# Source: Porymap ``ProjectConfig::reset`` and the per-version
# ``setDefaultMetatile*`` calls in ``src/config.cpp``.
#
# We currently populate the pokeemerald row only (the v0.1.0 supported target);
# pokeruby/pokefirered defaults are filled in when those versions are accepted
# in a future release (see ADR-0002 + ADR-0003 §5).


@dataclass(frozen=True, slots=True)
class _VersionDefaults:
    metatile_id_mask: int
    collision_mask: int
    elevation_mask: int
    metatile_attributes_size: int
    behavior_mask: int
    terrain_type_mask: int
    encounter_type_mask: int
    layer_type_mask: int
    default_primary_tileset: str
    default_secondary_tileset: str


_DEFAULTS_BY_VERSION: Final[Mapping[BaseGameVersion, _VersionDefaults]] = MappingProxyType(
    {
        BaseGameVersion.POKEEMERALD: _VersionDefaults(
            metatile_id_mask=0x03FF,
            collision_mask=0x0C00,
            elevation_mask=0xF000,
            metatile_attributes_size=2,
            behavior_mask=0x00FF,
            terrain_type_mask=0x3E00,
            encounter_type_mask=0xC000,
            layer_type_mask=0x6000,
            default_primary_tileset="gTileset_General",
            default_secondary_tileset="gTileset_PalletTown",
        ),
    }
)

# Keys we know about and consume. Anything else read from disk is preserved in
# ``ProjectConfig.unknown_keys`` and re-emitted on ``serialize``.
_KNOWN_SCALAR_KEYS: Final = frozenset(
    {
        "base_game_version",
        "use_poryscript",
        "use_custom_border_size",
        "default_map_width",
        "default_map_height",
        "default_primary_tileset",
        "default_secondary_tileset",
        "prefabs_filepath",
        "enable_triple_layer_metatiles",
        "block_metatile_id_mask",
        "block_collision_mask",
        "block_elevation_mask",
        "metatile_attributes_size",
        "metatile_behavior_mask",
        "metatile_terrain_type_mask",
        "metatile_encounter_type_mask",
        "metatile_layer_type_mask",
    }
)


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    """Resolved per-project configuration.

    All format-relevant fields are populated: explicit cfg values override
    per-version defaults at parse time, so downstream parsers can rely on every
    field being meaningful without inspecting ``base_game_version`` themselves.
    """

    base_game_version: BaseGameVersion
    metatile_id_mask: int
    collision_mask: int
    elevation_mask: int
    metatile_attributes_size: int
    behavior_mask: int
    terrain_type_mask: int
    encounter_type_mask: int
    layer_type_mask: int
    triple_layer_metatiles: bool
    use_poryscript: bool
    use_custom_border_size: bool
    default_map_width: int
    default_map_height: int
    default_primary_tileset: str
    default_secondary_tileset: str
    prefabs_filepath: str | None
    # Hierarchical-looking keys, preserved as-is for round-trip.
    paths: Mapping[str, str] = field(default_factory=dict)  # ``path/*``
    idents: Mapping[str, str] = field(default_factory=dict)  # ``ident/*``
    # Anything else encountered on disk (forward-compat, lossless round-trip).
    unknown_keys: Mapping[str, str] = field(default_factory=dict)


# ----------------------------- text parsing -----------------------------


def _parse_kv_lines(text: str) -> dict[str, str]:
    """Return an ordered mapping of cfg keys to raw string values.

    Strips ``#`` comments and surrounding whitespace. Duplicate keys: last one
    wins (matches Porymap's ``QMap`` write-order semantics; the file is read
    line by line and later assignments overwrite earlier ones).
    """
    out: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        # Strip comment (Porymap's reader splits on the first '#').
        hash_pos = raw.find("#")
        line = raw if hash_pos == -1 else raw[:hash_pos]
        line = line.strip()
        if not line:
            continue
        if "=" not in line:
            raise FormatError(
                f"porymap.project.cfg line {lineno}: expected 'key = value', got {raw!r}"
            )
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def _as_bool(s: str, *, key: str) -> bool:
    if s == "0":
        return False
    if s == "1":
        return True
    raise FormatError(f"porymap.project.cfg: {key}={s!r} is not a boolean (expected 0 or 1)")


def _as_int(s: str, *, key: str) -> int:
    try:
        # ``int(s, 0)`` accepts decimal *and* ``0x..`` hex, matching Porymap.
        return int(s, 0)
    except ValueError as exc:
        raise FormatError(
            f"porymap.project.cfg: {key}={s!r} is not a valid integer (decimal or 0x-hex)"
        ) from exc


def _coerce_base_game_version(raw: str) -> BaseGameVersion:
    try:
        return BaseGameVersion(raw)
    except ValueError:
        raise UnsupportedBaseGameError(
            declared=raw,
            supported=tuple(v.value for v in BaseGameVersion),
        ) from None


def parse(text: str) -> ProjectConfig:
    """Parse the textual contents of a ``porymap.project.cfg`` file.

    Raises:
        FormatError: malformed line, malformed integer, malformed boolean.
        UnsupportedBaseGameError: missing or unknown ``base_game_version``.
    """
    raw = _parse_kv_lines(text)

    bgv_raw = raw.get("base_game_version")
    if bgv_raw is None:
        raise UnsupportedBaseGameError(
            declared="<missing>",
            supported=tuple(v.value for v in BaseGameVersion),
        )
    bgv = _coerce_base_game_version(bgv_raw)

    defaults = _DEFAULTS_BY_VERSION.get(bgv)
    if defaults is None:
        # The version is valid for Porymap but we haven't filled in its defaults
        # table yet. Per ADR-0003 §5, the v0.1.0 supported-version gate lives in
        # ``Project.load()`` — but we still cannot safely return a config with
        # made-up masks. Fail clearly.
        raise UnsupportedBaseGameError(
            declared=bgv.value,
            supported=tuple(v.value for v in _DEFAULTS_BY_VERSION),
        )

    paths: dict[str, str] = {}
    idents: dict[str, str] = {}
    unknown: dict[str, str] = {}
    for key, value in raw.items():
        if key in _KNOWN_SCALAR_KEYS:
            continue
        if key.startswith("path/"):
            paths[key] = value
        elif key.startswith("ident/"):
            idents[key] = value
        else:
            unknown[key] = value

    return ProjectConfig(
        base_game_version=bgv,
        metatile_id_mask=(
            _as_int(raw["block_metatile_id_mask"], key="block_metatile_id_mask")
            if "block_metatile_id_mask" in raw
            else defaults.metatile_id_mask
        ),
        collision_mask=(
            _as_int(raw["block_collision_mask"], key="block_collision_mask")
            if "block_collision_mask" in raw
            else defaults.collision_mask
        ),
        elevation_mask=(
            _as_int(raw["block_elevation_mask"], key="block_elevation_mask")
            if "block_elevation_mask" in raw
            else defaults.elevation_mask
        ),
        metatile_attributes_size=(
            _as_int(raw["metatile_attributes_size"], key="metatile_attributes_size")
            if "metatile_attributes_size" in raw
            else defaults.metatile_attributes_size
        ),
        behavior_mask=(
            _as_int(raw["metatile_behavior_mask"], key="metatile_behavior_mask")
            if "metatile_behavior_mask" in raw
            else defaults.behavior_mask
        ),
        terrain_type_mask=(
            _as_int(raw["metatile_terrain_type_mask"], key="metatile_terrain_type_mask")
            if "metatile_terrain_type_mask" in raw
            else defaults.terrain_type_mask
        ),
        encounter_type_mask=(
            _as_int(raw["metatile_encounter_type_mask"], key="metatile_encounter_type_mask")
            if "metatile_encounter_type_mask" in raw
            else defaults.encounter_type_mask
        ),
        layer_type_mask=(
            _as_int(raw["metatile_layer_type_mask"], key="metatile_layer_type_mask")
            if "metatile_layer_type_mask" in raw
            else defaults.layer_type_mask
        ),
        triple_layer_metatiles=(
            _as_bool(raw["enable_triple_layer_metatiles"], key="enable_triple_layer_metatiles")
            if "enable_triple_layer_metatiles" in raw
            else False
        ),
        use_poryscript=(
            _as_bool(raw["use_poryscript"], key="use_poryscript")
            if "use_poryscript" in raw
            else False
        ),
        use_custom_border_size=(
            _as_bool(raw["use_custom_border_size"], key="use_custom_border_size")
            if "use_custom_border_size" in raw
            else False
        ),
        default_map_width=(
            _as_int(raw["default_map_width"], key="default_map_width")
            if "default_map_width" in raw
            else 20
        ),
        default_map_height=(
            _as_int(raw["default_map_height"], key="default_map_height")
            if "default_map_height" in raw
            else 20
        ),
        default_primary_tileset=raw.get(
            "default_primary_tileset", defaults.default_primary_tileset
        ),
        default_secondary_tileset=raw.get(
            "default_secondary_tileset", defaults.default_secondary_tileset
        ),
        prefabs_filepath=raw.get("prefabs_filepath") or None,
        paths=MappingProxyType(paths),
        idents=MappingProxyType(idents),
        unknown_keys=MappingProxyType(unknown),
    )


# ----------------------------- disk I/O -----------------------------


def read(path: Path) -> ProjectConfig:
    """Read and parse a ``porymap.project.cfg`` file from disk.

    Raises:
        ProjectError: file is missing or unreadable.
        FormatError, UnsupportedBaseGameError: see :func:`parse`.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ProjectError(
            f"porymap.project.cfg not found at {path}. Is this a Porymap project?"
        ) from exc
    except OSError as exc:
        raise ProjectError(f"failed to read {path}: {exc}") from exc
    return parse(text)


# ----------------------------- serialization -----------------------------


def _format_value(key: str, value: object) -> str:
    """Render a single value back to the cfg string form Porymap uses."""
    if isinstance(value, bool):  # must precede int — bool is an int
        return "1" if value else "0"
    if isinstance(value, int):
        # Mask-like keys → hex with at least 4 digits (matches Porymap's style).
        if "mask" in key:
            return f"0x{value:X}"
        return str(value)
    if value is None:
        return ""
    return str(value)


def serialize(config: ProjectConfig) -> str:
    """Serialize a :class:`ProjectConfig` back to cfg text.

    Output is alphabetically ordered (matches Porymap's ``QMap`` write order)
    with a trailing newline, so diffs against Porymap-written files stay clean.
    Unknown keys are preserved verbatim.
    """
    pairs: dict[str, str] = {
        "base_game_version": config.base_game_version.value,
        "block_collision_mask": _format_value("block_collision_mask", config.collision_mask),
        "block_elevation_mask": _format_value("block_elevation_mask", config.elevation_mask),
        "block_metatile_id_mask": _format_value("block_metatile_id_mask", config.metatile_id_mask),
        "default_map_height": _format_value("default_map_height", config.default_map_height),
        "default_map_width": _format_value("default_map_width", config.default_map_width),
        "default_primary_tileset": config.default_primary_tileset,
        "default_secondary_tileset": config.default_secondary_tileset,
        "enable_triple_layer_metatiles": _format_value(
            "enable_triple_layer_metatiles", config.triple_layer_metatiles
        ),
        "metatile_attributes_size": _format_value(
            "metatile_attributes_size", config.metatile_attributes_size
        ),
        "metatile_behavior_mask": _format_value("metatile_behavior_mask", config.behavior_mask),
        "metatile_encounter_type_mask": _format_value(
            "metatile_encounter_type_mask", config.encounter_type_mask
        ),
        "metatile_layer_type_mask": _format_value(
            "metatile_layer_type_mask", config.layer_type_mask
        ),
        "metatile_terrain_type_mask": _format_value(
            "metatile_terrain_type_mask", config.terrain_type_mask
        ),
        "use_custom_border_size": _format_value(
            "use_custom_border_size", config.use_custom_border_size
        ),
        "use_poryscript": _format_value("use_poryscript", config.use_poryscript),
    }
    if config.prefabs_filepath is not None:
        pairs["prefabs_filepath"] = config.prefabs_filepath
    pairs.update(config.paths)
    pairs.update(config.idents)
    pairs.update(config.unknown_keys)

    lines = [f"{k} = {pairs[k]}" for k in sorted(pairs)]
    return "\n".join(lines) + "\n"


def write(config: ProjectConfig, path: Path) -> None:
    """Atomically write ``config`` to ``path`` (UTF-8, LF, trailing newline)."""
    write_atomic(path, serialize(config).encode("utf-8"))
