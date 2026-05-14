"""L3 overlay renderers — collision, elevation, grid, events.

Each function alpha-blends a translucent visualization on top of an
already-assembled RGBA image, mutating it in place. The caller (typically
``tools/rendering.py``) chains them in sequence between the bare map
assembly and the final PNG encode, and passes ``force_rgba=True`` to
:func:`porymap_mcp.render.encode.encode_png` whenever any overlay is
applied — overlays generate many intermediate RGB triples, so palette
mode would lose to the > 256 colour limit.

Coordinate convention:

  - All overlays accept a ``frame_offset_px = (offset_y, offset_x)`` so
    they place themselves correctly when ``include_border=True`` has
    wrapped the map in a border frame. Without a frame, the offset is
    ``(0, 0)`` and the overlay aligns with the buffer's top-left.
  - Inside this module, pixel coordinates are ``(x, y)`` matching the
    rest of the project (Porymap convention).

References:
    - ADR-0010 §"PNG encoding" — overlays force RGBA.
    - Phase-4 doc §3 — overlay menu + bundled icons (icons are a future
      enhancement; v1 uses geometric markers, no committed assets).
"""

from __future__ import annotations

from typing import Final

import numpy as np

from porymap_mcp.errors import ProjectError
from porymap_mcp.parsers.mapbin import MapBin
from porymap_mcp.parsers.mapjson import MapJson

#: Side length of one metatile in pixels (mirrors :mod:`compose`).
METATILE_SIZE: Final = 16

#: Overlay names accepted by :func:`apply_overlays`. ``tools/rendering.py``
#: exposes the same tuple to the agent through tool descriptions.
SUPPORTED_OVERLAYS: Final = ("collision", "elevation", "grid", "events")


# --- Colour tables --------------------------------------------------------

# Collision is a 2-bit field (0..3). 0 = passable (no overlay drawn).
# Porymap renders impassable tiles with translucent red boxes; we follow
# the same convention.
_COLLISION_COLOURS: Final = {
    1: (255, 0, 0),  # solid wall
    2: (200, 0, 100),  # rarely seen — paint with a distinct hue
    3: (100, 0, 200),
}
_COLLISION_ALPHA: Final = 0.45

# Elevation is a 4-bit field (0..15). v1 uses a distinct hue per level —
# no text labels (would need a bundled font). The colours are chosen for
# high visual contrast so a glance reveals layer transitions.
_ELEVATION_COLOURS: Final = (
    (128, 128, 128),  # 0 — transition layer
    (255, 200, 0),  # 1
    (255, 100, 0),  # 2
    (0, 200, 255),  # 3
    (0, 100, 255),  # 4
    (0, 200, 50),  # 5
    (200, 0, 200),  # 6
    (200, 200, 0),  # 7
    (255, 50, 100),  # 8
    (50, 100, 255),  # 9
    (220, 220, 220),  # 10
    (100, 200, 100),  # 11
    (200, 100, 50),  # 12
    (50, 50, 50),  # 13
    (255, 255, 255),  # 14
    (0, 0, 0),  # 15
)
_ELEVATION_ALPHA: Final = 0.35

# Grid lines: thin black overlay at every metatile boundary inside the map.
_GRID_COLOUR: Final = (0, 0, 0)
_GRID_ALPHA: Final = 0.4

# Event markers — one colour per event class. v1 draws a 12x12 filled
# square with a 1-px black outline; a future slice can replace the
# square with proper 12x12 PNG icons (warp / object / sign / trigger).
_EVENT_COLOURS: Final = {
    "object_events": (255, 200, 0),  # yellow
    "warp_events": (255, 0, 0),  # red
    "coord_events": (0, 200, 255),  # cyan
    "bg_events": (0, 255, 100),  # green
}
_EVENT_ICON_SIZE_PX: Final = 12
_EVENT_OUTLINE_COLOUR: Final = (0, 0, 0)
_EVENT_ALPHA: Final = 0.85


# --- Public overlay functions ---------------------------------------------


def apply_overlays(
    rgba: np.ndarray,
    overlays: tuple[str, ...],
    *,
    map_bin: MapBin,
    map_json: MapJson,
    frame_offset_px: tuple[int, int] = (0, 0),
) -> None:
    """Dispatch to each named overlay, in argument order.

    Args:
        rgba: ``uint8[H, W, 4]`` — the buffer to draw on (mutated in place).
        overlays: ordered sequence of overlay names from
            :data:`SUPPORTED_OVERLAYS`. Duplicates are allowed (later
            layers paint over earlier ones).
        map_bin: the layout the buffer represents; carries per-tile
            ``collision`` and ``elevation`` for those overlays.
        map_json: the same map's events for the ``"events"`` overlay.
        frame_offset_px: ``(y, x)`` pixel offset of the map's top-left
            corner inside the buffer. Non-zero when ``include_border=True``
            has wrapped the map in a tiled border frame.

    Raises:
        ProjectError: an overlay name is not in :data:`SUPPORTED_OVERLAYS`.
    """
    for name in overlays:
        if name == "collision":
            apply_collision_overlay(rgba, map_bin, frame_offset_px=frame_offset_px)
        elif name == "elevation":
            apply_elevation_overlay(rgba, map_bin, frame_offset_px=frame_offset_px)
        elif name == "grid":
            apply_grid_overlay(rgba, map_bin, frame_offset_px=frame_offset_px)
        elif name == "events":
            apply_events_overlay(rgba, map_json, frame_offset_px=frame_offset_px)
        else:
            raise ProjectError(f"unknown overlay name: {name!r}. Supported: {SUPPORTED_OVERLAYS}.")


def apply_collision_overlay(
    rgba: np.ndarray,
    map_bin: MapBin,
    *,
    frame_offset_px: tuple[int, int] = (0, 0),
) -> None:
    """Paint a translucent red square in every cell where ``collision > 0``.

    Collision 0 (passable) is untouched. Values 2 and 3 — rare but
    semantically meaningful — get their own distinct hues so the agent
    can read them apart from the standard "1 = solid wall" case.
    """
    fy, fx = frame_offset_px
    for y, row in enumerate(map_bin.tiles):
        for x, tile in enumerate(row):
            if tile.collision == 0:
                continue
            colour = _COLLISION_COLOURS.get(tile.collision)
            if colour is None:
                continue
            _blend_rectangle(
                rgba,
                x=fx + x * METATILE_SIZE,
                y=fy + y * METATILE_SIZE,
                w=METATILE_SIZE,
                h=METATILE_SIZE,
                colour=colour,
                alpha=_COLLISION_ALPHA,
            )


def apply_elevation_overlay(
    rgba: np.ndarray,
    map_bin: MapBin,
    *,
    frame_offset_px: tuple[int, int] = (0, 0),
) -> None:
    """Paint a translucent colour-per-elevation block on every cell.

    A heat-map of the 4-bit elevation field. v1 ships hues only — adding
    numeric labels would require a bundled font and is deferred.
    """
    fy, fx = frame_offset_px
    for y, row in enumerate(map_bin.tiles):
        for x, tile in enumerate(row):
            colour = _ELEVATION_COLOURS[tile.elevation]
            _blend_rectangle(
                rgba,
                x=fx + x * METATILE_SIZE,
                y=fy + y * METATILE_SIZE,
                w=METATILE_SIZE,
                h=METATILE_SIZE,
                colour=colour,
                alpha=_ELEVATION_ALPHA,
            )


def apply_grid_overlay(
    rgba: np.ndarray,
    map_bin: MapBin,
    *,
    frame_offset_px: tuple[int, int] = (0, 0),
) -> None:
    """Draw 1-px grid lines at every metatile boundary of the map region.

    Lines are drawn at ``x = 0, 16, 32, ..., map_w_px`` and similarly for
    ``y``. The border frame (when present) is left alone — the agent
    typically only cares about grid coordinates inside the map itself.
    """
    fy, fx = frame_offset_px
    map_h_px = map_bin.height * METATILE_SIZE
    map_w_px = map_bin.width * METATILE_SIZE
    for y in range(0, map_h_px + 1, METATILE_SIZE):
        _blend_rectangle(
            rgba,
            x=fx,
            y=fy + y,
            w=map_w_px,
            h=1,
            colour=_GRID_COLOUR,
            alpha=_GRID_ALPHA,
        )
    for x in range(0, map_w_px + 1, METATILE_SIZE):
        _blend_rectangle(
            rgba,
            x=fx + x,
            y=fy,
            w=1,
            h=map_h_px,
            colour=_GRID_COLOUR,
            alpha=_GRID_ALPHA,
        )


def apply_events_overlay(
    rgba: np.ndarray,
    map_json: MapJson,
    *,
    frame_offset_px: tuple[int, int] = (0, 0),
) -> None:
    """Draw a 12x12 coloured square (with a 1-px black outline) on every
    event's metatile.

    Class-to-colour mapping:

      ============== ===========
      Event class    Colour
      ============== ===========
      object_events  yellow
      warp_events    red
      coord_events   cyan
      bg_events      green
      ============== ===========

    Events whose ``x``/``y`` keys are missing or non-integer are silently
    skipped — that's a malformed event the L1 layer would already have
    surfaced via ``list_events``; the renderer doesn't double-fail on it.
    """
    fy, fx = frame_offset_px
    icon = _EVENT_ICON_SIZE_PX
    inset = (METATILE_SIZE - icon) // 2  # centre the icon in the cell

    classes: tuple[tuple[str, tuple[dict[str, object], ...] | None], ...] = (
        ("object_events", map_json.object_events),
        ("warp_events", map_json.warp_events),
        ("coord_events", map_json.coord_events),
        ("bg_events", map_json.bg_events),
    )
    for cls, events in classes:
        if not events:
            continue
        colour = _EVENT_COLOURS[cls]
        for event in events:
            ex = event.get("x")
            ey = event.get("y")
            if not isinstance(ex, int) or not isinstance(ey, int):
                continue
            if isinstance(ex, bool) or isinstance(ey, bool):
                # bool is an int subclass; skip the rare-but-possible case.
                continue
            cell_x = fx + ex * METATILE_SIZE + inset
            cell_y = fy + ey * METATILE_SIZE + inset
            # 1-px black outline.
            _blend_rectangle(
                rgba,
                x=cell_x - 1,
                y=cell_y - 1,
                w=icon + 2,
                h=icon + 2,
                colour=_EVENT_OUTLINE_COLOUR,
                alpha=_EVENT_ALPHA,
            )
            # Class-coloured fill on top.
            _blend_rectangle(
                rgba,
                x=cell_x,
                y=cell_y,
                w=icon,
                h=icon,
                colour=colour,
                alpha=_EVENT_ALPHA,
            )


# --- Internals ------------------------------------------------------------


def _blend_rectangle(
    rgba: np.ndarray,
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    colour: tuple[int, int, int],
    alpha: float,
) -> None:
    """Alpha-blend a solid-colour rectangle into ``rgba`` in place.

    Clips silently to the buffer's bounds — the overlay primitive is
    forgiving on off-the-edge writes so callers don't have to.
    Per-pixel maths: ``out = alpha * colour + (1 - alpha) * existing``.
    The alpha channel is restored to 255 after the blend; the underlying
    map is opaque and overlays should not introduce transparency in the
    final encode.
    """
    buf_h, buf_w = rgba.shape[:2]
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(buf_w, x + w)
    y2 = min(buf_h, y + h)
    if x1 >= x2 or y1 >= y2:
        return
    overlay_rgb = np.array(colour, dtype=np.float32)
    region = rgba[y1:y2, x1:x2, :3].astype(np.float32)
    blended = (alpha * overlay_rgb + (1.0 - alpha) * region).astype(np.uint8)
    rgba[y1:y2, x1:x2, :3] = blended
    rgba[y1:y2, x1:x2, 3] = 255
