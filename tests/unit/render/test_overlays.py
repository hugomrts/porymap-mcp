"""Tests for ``porymap_mcp.render.overlays``.

Pure-numpy primitive — no on-disk fixtures. Each test builds a small
opaque-grey RGBA buffer (uniform background so blending arithmetic is
trivial to invert) and a synthetic :class:`MapBin` / :class:`MapJson`,
then verifies the overlay's pixel writes at known offsets.
"""

from __future__ import annotations

import numpy as np
import pytest

from porymap_mcp.errors import ProjectError
from porymap_mcp.parsers.mapbin import MapBin, Tile
from porymap_mcp.parsers.mapjson import MapJson
from porymap_mcp.render.overlays import (
    METATILE_SIZE,
    SUPPORTED_OVERLAYS,
    apply_collision_overlay,
    apply_elevation_overlay,
    apply_events_overlay,
    apply_grid_overlay,
    apply_overlays,
)

# --- Shared fixture helpers ----------------------------------------------


def _grey_buffer(width_mt: int, height_mt: int, grey: int = 128) -> np.ndarray:
    """An opaque uniform-grey RGBA canvas sized to ``width_mt x height_mt`` metatiles."""
    h = height_mt * METATILE_SIZE
    w = width_mt * METATILE_SIZE
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[:, :, :3] = grey
    out[:, :, 3] = 255
    return out


def _mapbin(rows: list[list[Tile]]) -> MapBin:
    height = len(rows)
    width = len(rows[0]) if rows else 0
    return MapBin(width=width, height=height, tiles=tuple(tuple(r) for r in rows))


def _blank_mapjson() -> MapJson:
    return MapJson(
        id="MAP_TEST",
        name="Test",
        layout="LAYOUT_TEST",
        music="MUS_NONE",
        region_map_section="MAPSEC_NONE",
        requires_flash=False,
        weather="WEATHER_NONE",
        map_type="MAP_TYPE_TOWN",
        show_map_name=True,
        battle_scene="MAP_BATTLE_SCENE_NORMAL",
        allow_cycling=True,
        allow_escaping=False,
        allow_running=True,
        floor_number=None,
        object_events=(),
        warp_events=(),
        coord_events=(),
        bg_events=(),
    )


# --- apply_collision_overlay ----------------------------------------------


class TestApplyCollisionOverlay:
    def test_passable_cells_untouched(self) -> None:
        buf = _grey_buffer(2, 2)
        # All cells collision=0 (passable) → no overlay anywhere.
        rows = [
            [Tile(0, 0, 0), Tile(0, 0, 0)],
            [Tile(0, 0, 0), Tile(0, 0, 0)],
        ]
        apply_collision_overlay(buf, _mapbin(rows))
        # Centre pixel of every cell must still be pure grey.
        for y in range(2):
            for x in range(2):
                px = buf[y * 16 + 8, x * 16 + 8]
                assert tuple(int(c) for c in px) == (128, 128, 128, 255)

    def test_collision_1_shifts_pixels_toward_red(self) -> None:
        buf = _grey_buffer(1, 1)
        rows = [[Tile(metatile_id=0, collision=1, elevation=0)]]
        apply_collision_overlay(buf, _mapbin(rows))
        # alpha=0.45 of (255,0,0) on (128,128,128):
        # R = 0.45*255 + 0.55*128 = 185.15 -> 185 (uint8 truncate)
        # G = 0.45*0   + 0.55*128 = 70.4   -> 70
        # B = same                          -> 70
        px = buf[8, 8]
        assert int(px[0]) == 185
        assert int(px[1]) == 70
        assert int(px[2]) == 70
        assert int(px[3]) == 255

    def test_frame_offset_shifts_overlay(self) -> None:
        # Map drawn into a buffer larger than the map, offset by (32, 16) px.
        buf = _grey_buffer(4, 4)
        rows = [[Tile(metatile_id=0, collision=1, elevation=0)]]
        apply_collision_overlay(buf, _mapbin(rows), frame_offset_px=(32, 16))
        # The single overlaid cell is at output pixels [32..48, 16..32].
        # Centre is at (40, 24) → inside the overlay.
        assert int(buf[40, 24, 0]) == 185  # red-shifted
        # Pixels at (0, 0) and (32+16+0, 16+16+0) = (48, 32) outside the
        # overlay must remain pure grey.
        assert tuple(int(c) for c in buf[0, 0]) == (128, 128, 128, 255)
        assert tuple(int(c) for c in buf[50, 40]) == (128, 128, 128, 255)


# --- apply_elevation_overlay ----------------------------------------------


class TestApplyElevationOverlay:
    def test_different_elevations_produce_different_centres(self) -> None:
        # Three cells with elevations 0, 1, 2 — the centre-pixel R values
        # must all differ (each elevation uses a distinct colour).
        buf = _grey_buffer(3, 1)
        rows = [
            [
                Tile(metatile_id=0, collision=0, elevation=0),
                Tile(metatile_id=0, collision=0, elevation=1),
                Tile(metatile_id=0, collision=0, elevation=2),
            ]
        ]
        apply_elevation_overlay(buf, _mapbin(rows))
        centres = [tuple(int(c) for c in buf[8, x * 16 + 8]) for x in range(3)]
        # Each elevation maps to a different colour. (Elevation 0 happens
        # to render as the same grey as the background; we only assert
        # uniqueness across the three values.)
        assert centres[1] != (128, 128, 128, 255)
        assert centres[2] != (128, 128, 128, 255)
        assert len({centres[0], centres[1], centres[2]}) == 3


# --- apply_grid_overlay ---------------------------------------------------


class TestApplyGridOverlay:
    def test_grid_lines_at_metatile_boundaries(self) -> None:
        buf = _grey_buffer(3, 2)  # 48x32 px
        # 3x2 of any tile; grid only cares about dimensions.
        rows = [
            [Tile(0, 0, 0) for _ in range(3)],
            [Tile(0, 0, 0) for _ in range(3)],
        ]
        apply_grid_overlay(buf, _mapbin(rows))
        # Grid is drawn at x = 0, 16, 32, 48 and y = 0, 16, 32.
        # Off-boundary pixel — e.g. inside the middle cell at (8, 8) —
        # is untouched grey.
        assert tuple(int(c) for c in buf[8, 8]) == (128, 128, 128, 255)
        # On-boundary horizontal-line pixel (x in middle, y == 16).
        # alpha=0.4 of (0,0,0) on (128,128,128): each channel = 0.6*128 = 76.8 → 76.
        line_px = buf[16, 24]
        assert int(line_px[0]) == 76
        assert int(line_px[1]) == 76
        assert int(line_px[2]) == 76
        # On-boundary vertical line.
        vline_px = buf[8, 16]
        assert int(vline_px[0]) == 76

    def test_grid_with_frame_offset(self) -> None:
        # Buffer 4x4 with map placed at offset (32, 32) (frame=2 mt).
        buf = _grey_buffer(4, 4)
        rows = [[Tile(0, 0, 0), Tile(0, 0, 0)]]  # 2x1 map
        apply_grid_overlay(buf, _mapbin(rows), frame_offset_px=(32, 32))
        # Map area: x in [32, 64), y in [32, 48). Grid lines at
        # x=32, 48, 64 and y=32, 48.
        # On-boundary line:
        on = buf[32, 40]  # y=32 is a horizontal grid line.
        assert int(on[0]) == 76
        # Far outside the map (top-left corner of buffer): still grey.
        outside = buf[0, 0]
        assert tuple(int(c) for c in outside) == (128, 128, 128, 255)


# --- apply_events_overlay -------------------------------------------------


class TestApplyEventsOverlay:
    def test_warp_event_paints_red_at_cell(self) -> None:
        buf = _grey_buffer(3, 3)
        mj = MapJson(
            id="MAP_TEST",
            name="Test",
            layout="LAYOUT_TEST",
            music="MUS_NONE",
            region_map_section="MAPSEC_NONE",
            requires_flash=False,
            weather="WEATHER_NONE",
            map_type="MAP_TYPE_TOWN",
            show_map_name=True,
            battle_scene="MAP_BATTLE_SCENE_NORMAL",
            allow_cycling=True,
            allow_escaping=False,
            allow_running=True,
            floor_number=None,
            object_events=(),
            warp_events=({"x": 1, "y": 1, "elevation": 0, "dest_map": "M", "dest_warp_id": "0"},),
            coord_events=(),
            bg_events=(),
        )
        apply_events_overlay(buf, mj)
        # Cell (1, 1) → pixel range [16, 32) x [16, 32).
        # Icon is 12x12 centred → inset=2 → icon at [18, 30) x [18, 30).
        # The centre pixel (24, 24) sits inside *both* the black outline
        # and the red fill (fill is drawn ON TOP of outline). Sequence:
        #   1. Outline (black, alpha 0.85) over grey 128:
        #      each channel = 0.85*0 + 0.15*128 = 19.2 → 19
        #   2. Fill (red 255,0,0, alpha 0.85) over (19, 19, 19):
        #      R = 0.85*255 + 0.15*19 = 219.6 → 219
        #      G = 0.85*0   + 0.15*19 = 2.85  → 2
        #      B = same                       → 2
        centre = buf[24, 24]
        assert int(centre[0]) == 219
        assert int(centre[1]) == 2
        assert int(centre[2]) == 2
        # A pixel inside a different cell (0, 0) is still pure grey.
        assert tuple(int(c) for c in buf[8, 8]) == (128, 128, 128, 255)

    def test_event_classes_use_distinct_colours(self) -> None:
        buf = _grey_buffer(4, 1)
        # One event per class, at x = 0..3.
        mj = MapJson(
            id="MAP_TEST",
            name="Test",
            layout="LAYOUT_TEST",
            music="MUS_NONE",
            region_map_section="MAPSEC_NONE",
            requires_flash=False,
            weather="WEATHER_NONE",
            map_type="MAP_TYPE_TOWN",
            show_map_name=True,
            battle_scene="MAP_BATTLE_SCENE_NORMAL",
            allow_cycling=True,
            allow_escaping=False,
            allow_running=True,
            floor_number=None,
            object_events=({"x": 0, "y": 0},),
            warp_events=({"x": 1, "y": 0},),
            coord_events=({"x": 2, "y": 0},),
            bg_events=({"x": 3, "y": 0},),
        )
        apply_events_overlay(buf, mj)
        centres = [tuple(int(c) for c in buf[8, x * 16 + 8]) for x in range(4)]
        # All distinct (one colour per class).
        assert len(set(centres)) == 4

    def test_event_without_x_or_y_is_skipped(self) -> None:
        # An event missing x/y must not crash the renderer.
        buf = _grey_buffer(2, 2)
        mj = _blank_mapjson()
        # Build a copy with one malformed warp.
        mj = MapJson(
            id=mj.id,
            name=mj.name,
            layout=mj.layout,
            music=mj.music,
            region_map_section=mj.region_map_section,
            requires_flash=mj.requires_flash,
            weather=mj.weather,
            map_type=mj.map_type,
            show_map_name=mj.show_map_name,
            battle_scene=mj.battle_scene,
            allow_cycling=mj.allow_cycling,
            allow_escaping=mj.allow_escaping,
            allow_running=mj.allow_running,
            floor_number=mj.floor_number,
            object_events=(),
            warp_events=({"y": 1, "dest_map": "M", "dest_warp_id": "0"},),  # no x
            coord_events=(),
            bg_events=(),
        )
        before = buf.copy()
        apply_events_overlay(buf, mj)
        # Nothing changed.
        assert np.array_equal(before, buf)

    def test_event_with_negative_frame_offset_clips(self) -> None:
        # When render_map_region passes a negative offset for events,
        # events outside the region simply land off-buffer and clip.
        buf = _grey_buffer(2, 2)
        before = buf.copy()
        mj = _blank_mapjson()
        mj = MapJson(
            **{
                **{f: getattr(mj, f) for f in mj.__slots__},
                # Event at source (0, 0); negative offset of one full
                # metatile on each axis pushes the icon off the buffer.
                "object_events": ({"x": 0, "y": 0},),
            }
        )
        apply_events_overlay(buf, mj, frame_offset_px=(-32, -32))
        assert np.array_equal(before, buf)


# --- apply_overlays dispatch ---------------------------------------------


class TestApplyOverlays:
    def test_unknown_name_raises_project_error(self) -> None:
        buf = _grey_buffer(1, 1)
        mb = _mapbin([[Tile(0, 0, 0)]])
        mj = _blank_mapjson()
        with pytest.raises(ProjectError, match="unknown overlay"):
            apply_overlays(buf, ("not-an-overlay",), map_bin=mb, map_json=mj)

    def test_empty_overlay_list_is_no_op(self) -> None:
        buf = _grey_buffer(2, 2)
        before = buf.copy()
        mb = _mapbin([[Tile(0, 0, 0) for _ in range(2)] for _ in range(2)])
        apply_overlays(buf, (), map_bin=mb, map_json=_blank_mapjson())
        assert np.array_equal(before, buf)

    def test_dispatch_each_supported_name(self) -> None:
        # Smoke test: every name in SUPPORTED_OVERLAYS is reachable through
        # apply_overlays without an exception.
        buf = _grey_buffer(2, 2)
        mb = _mapbin(
            [
                [
                    Tile(metatile_id=0, collision=1, elevation=2),
                    Tile(metatile_id=0, collision=0, elevation=3),
                ],
                [
                    Tile(metatile_id=0, collision=0, elevation=0),
                    Tile(metatile_id=0, collision=2, elevation=5),
                ],
            ]
        )
        mj = _blank_mapjson()
        mj = MapJson(
            **{
                **{f: getattr(mj, f) for f in mj.__slots__},
                "object_events": ({"x": 0, "y": 0},),
            }
        )
        apply_overlays(buf, SUPPORTED_OVERLAYS, map_bin=mb, map_json=mj)
        # Buffer must have changed somewhere — every overlay paints
        # something on this fixture.
        original = _grey_buffer(2, 2)
        assert not np.array_equal(buf, original)
