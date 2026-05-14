"""Typed exception hierarchy for porymap-mcp.

Every error the package raises across the MCP boundary is a subclass of
:class:`PorymapMCPError`. Callers (typically the MCP tool layer) translate
these into structured error responses; raw ``Exception`` must not leak.
"""

from __future__ import annotations


class PorymapMCPError(Exception):
    """Base class for every porymap-mcp error raised across the public API."""


class ProjectError(PorymapMCPError):
    """Project-level error: missing config, unreadable structure, etc."""


class UnsupportedBaseGameError(ProjectError):
    """The project declares a ``base_game_version`` we do not yet support.

    Carries the offending value and the list of currently supported ones so
    the agent can surface a useful message to the user.
    """

    def __init__(self, declared: str, supported: tuple[str, ...]) -> None:
        self.declared = declared
        self.supported = supported
        super().__init__(
            f"Unsupported base_game_version: {declared!r}. Supported: {', '.join(supported)}."
        )


class FormatError(PorymapMCPError):
    """A file on disk did not match the format we expect."""


class MapBinFormatError(FormatError):
    """``map.bin`` (or ``border.bin``) had an unexpected size or content."""


class ProjectConfigFormatError(FormatError):
    """``porymap.project.cfg`` had malformed content."""


class LayoutsJsonFormatError(FormatError):
    """``data/layouts/layouts.json`` had malformed content."""


class MapGroupsFormatError(FormatError):
    """``data/maps/map_groups.json`` had malformed content."""


class MapJsonFormatError(FormatError):
    """``data/maps/<MAP>/map.json`` had malformed content."""


class TilesPngFormatError(FormatError):
    """A tileset's ``tiles.png`` did not match the 4-bpp / 8x8-tiled layout
    Porymap expects (e.g. width/height not a multiple of 8, not indexed)."""


class PaletteFormatError(FormatError):
    """A tileset ``.pal`` file was not valid JASC-PAL (wrong header, wrong
    declared colour count, or malformed RGB triple)."""


class MetatilesBinFormatError(FormatError):
    """A tileset's ``metatiles.bin`` did not match the expected layout
    (size not a multiple of 16/24, or attribute count mismatch)."""


class LayoutAssemblyError(PorymapMCPError):
    """L3 layout-assembly precondition failed: shape mismatch between the
    metatile bank and the metatile grid, grid contains an out-of-range
    metatile ID, or a requested region is invalid for the grid."""


class MapNotFoundError(ProjectError):
    """Referenced map name does not exist in the project."""

    def __init__(self, map_name: str) -> None:
        self.map_name = map_name
        super().__init__(f"Map not found: {map_name!r}.")


class CoordinatesOutOfBoundsError(PorymapMCPError):
    """A tool was called with (x, y) outside the map's dimensions."""

    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        super().__init__(
            f"Coordinates ({x}, {y}) are out of bounds. "
            f"Map is {width}x{height} (valid x: 0..{width - 1}, y: 0..{height - 1})."
        )
