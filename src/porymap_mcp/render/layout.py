"""Layout assembly for the L3 renderer.

Per ADR-0010 §"Layout assembly", an assembled layout image is a full RGBA
canvas where each ``WxH`` grid cell is pasted from the metatile bank::

    out[y*16:(y+1)*16, x*16:(x+1)*16] = metatile_bank[grid[y, x]]

This module ships the pure-numpy primitive that does that paste in a single
vectorized fancy-index + reshape + transpose, plus a region helper for
partial renders (``render_map_region``) and a small adapter that turns the
L1 :class:`~porymap_mcp.parsers.mapbin.MapBin` parser output into the
``uint16[H, W]`` metatile grid this module consumes.

The full assembly path is benched well under the 100 ms budget at 30x20 and
under 1 s at 60x120 because numpy's fancy index is a single C-level copy —
no Python-per-tile overhead.

References:
    - ADR-0010 §"Layout assembly" (the vectorized recipe).
    - ADR-0010 §"Performance" (per-render budgets).
    - :mod:`porymap_mcp.parsers.mapbin` (the raw ``map.bin`` /
      ``border.bin`` decoder this module adapts).
"""

from __future__ import annotations

from typing import Final

import numpy as np

from porymap_mcp.errors import LayoutAssemblyError
from porymap_mcp.parsers.mapbin import MapBin

#: Side length of one metatile in pixels (matches :mod:`compose`).
METATILE_SIZE: Final = 16


def assemble(metatile_bank: np.ndarray, metatile_grid: np.ndarray) -> np.ndarray:
    """Paste every cell of ``metatile_grid`` into a full RGBA image.

    The implementation is a single numpy fancy index followed by reshape +
    transpose: ``bank[grid.reshape(-1)]`` produces an ``(H*W, 16, 16, 4)``
    block, and the two-step ``transpose(0, 2, 1, 3, 4).reshape(H*16, W*16,
    4)`` interleaves the W and tile-pixel axes so adjacent metatiles end
    up adjacent in the output buffer.

    Args:
        metatile_bank: ``uint8[num_metatiles, 16, 16, 4]`` from
            :func:`porymap_mcp.render.compose.decode_metatile_bank`.
        metatile_grid: ``uint16[H, W]`` (or any integer dtype) of metatile
            IDs in row-major order, origin top-left. ``MapBin`` callers
            should pre-process with :func:`mapbin_to_metatile_grid`.

    Returns:
        A C-contiguous ``uint8[H*16, W*16, 4]`` RGBA image.

    Raises:
        LayoutAssemblyError: bank shape/dtype is wrong, grid is not 2D,
            grid is empty, grid dtype is non-integer, or grid contains an
            ID outside ``[0, num_metatiles)``.
    """
    _validate_bank(metatile_bank)
    _validate_grid(metatile_grid, num_metatiles=int(metatile_bank.shape[0]))

    height, width = metatile_grid.shape
    flat = metatile_bank[metatile_grid.reshape(-1)]
    out: np.ndarray = (
        flat.reshape(height, width, METATILE_SIZE, METATILE_SIZE, 4)
        .transpose(0, 2, 1, 3, 4)
        .reshape(height * METATILE_SIZE, width * METATILE_SIZE, 4)
        .copy()
    )
    return out


def assemble_region(
    metatile_bank: np.ndarray,
    metatile_grid: np.ndarray,
    *,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
) -> np.ndarray:
    """Assemble a half-open ``[x1, x2) x [y1, y2)`` slice of the grid.

    Coordinates are in metatile units, not pixels. The returned image is
    ``(y2 - y1) * 16`` rows by ``(x2 - x1) * 16`` cols. Strict: any region
    that escapes the grid raises — the tool layer pre-clips via
    :func:`clip_region` when the caller's intent is "render whatever fits".

    Raises:
        LayoutAssemblyError: region degenerate (``x1 >= x2`` or
            ``y1 >= y2``) or outside the grid bounds, plus the validation
            failures :func:`assemble` raises.
    """
    _validate_grid(metatile_grid, num_metatiles=-1)  # shape-only check
    height, width = metatile_grid.shape
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise LayoutAssemblyError(
            f"region (x1={x1}, y1={y1}, x2={x2}, y2={y2}) invalid for "
            f"{width}x{height} grid (expected 0 <= x1 < x2 <= width, "
            f"0 <= y1 < y2 <= height)"
        )
    return assemble(metatile_bank, metatile_grid[y1:y2, x1:x2])


def clip_region(
    grid_shape: tuple[int, int],
    x1: int,
    y1: int,
    x2: int,
    y2: int,
) -> tuple[int, int, int, int]:
    """Clip a requested region to a grid's bounds.

    The caller asks for a half-open ``[x1, x2) x [y1, y2)`` rectangle in
    metatile units; this helper returns the largest sub-rectangle that
    fits inside ``[0, W) x [0, H)``. Raises if the clip collapses to
    empty (the caller is asking for a region entirely outside the grid,
    which is almost certainly a bug worth surfacing).

    Args:
        grid_shape: ``(height, width)`` of the grid being rendered.
        x1, y1, x2, y2: Requested half-open rectangle.

    Returns:
        ``(cx1, cy1, cx2, cy2)`` — the clipped half-open rectangle, safe
        to pass to :func:`assemble_region`.

    Raises:
        LayoutAssemblyError: post-clip region is empty.
    """
    height, width = grid_shape
    cx1 = max(0, min(x1, width))
    cy1 = max(0, min(y1, height))
    cx2 = max(0, min(x2, width))
    cy2 = max(0, min(y2, height))
    if cx1 >= cx2 or cy1 >= cy2:
        raise LayoutAssemblyError(
            f"region (x1={x1}, y1={y1}, x2={x2}, y2={y2}) clipped to empty "
            f"on a {width}x{height} grid"
        )
    return cx1, cy1, cx2, cy2


def tile_border_around(
    map_rgba: np.ndarray,
    border_rgba: np.ndarray,
    *,
    frame_width_metatiles: int,
    frame_height_metatiles: int,
) -> np.ndarray:
    """Wrap ``map_rgba`` in a frame of tiled ``border_rgba``.

    Replicates Porymap's "include border" export mode: the small border
    ``MapBin`` (typically 2x2 metatiles) is tiled across the frame
    surrounding the map. The frame is ``frame_width_metatiles`` thick on
    the left and right and ``frame_height_metatiles`` thick on the top
    and bottom (Porymap defaults to 7 per side, see
    ``BorderMetatilesData::DEFAULT_BORDER_SIZE`` in
    ``src/ui/maplayout.cpp``).

    The border tiles by its own pixel dimensions: pixel ``(x, y)`` in the
    output frame outside the map comes from
    ``border_rgba[y % bH, x % bW]``, where ``(bH, bW)`` are the border's
    height and width in pixels. The tiling phase is anchored at the
    top-left of the output buffer — same as Porymap.

    Args:
        map_rgba: ``uint8[H, W, 4]`` — the assembled map RGBA from
            :func:`assemble`. ``H`` and ``W`` must be positive multiples
            of :data:`METATILE_SIZE`.
        border_rgba: ``uint8[bH, bW, 4]`` — the assembled border RGBA
            (typically 32x32 for vanilla Gen-3). ``bH`` and ``bW`` must
            be positive multiples of :data:`METATILE_SIZE`.
        frame_width_metatiles: Frame thickness on the left and right
            sides, in metatile units. Must be non-negative.
        frame_height_metatiles: Frame thickness on the top and bottom
            sides, in metatile units. Must be non-negative.

    Returns:
        A C-contiguous ``uint8[H + 2*FH, W + 2*FW, 4]`` RGBA image,
        where ``FH = frame_height_metatiles * METATILE_SIZE`` and
        ``FW = frame_width_metatiles * METATILE_SIZE``.

    Raises:
        LayoutAssemblyError: shape/dtype violation on either input, or
            a negative frame dimension.
    """
    _validate_rgba(map_rgba, name="map_rgba")
    _validate_rgba(border_rgba, name="border_rgba")
    if frame_width_metatiles < 0 or frame_height_metatiles < 0:
        raise LayoutAssemblyError(
            f"frame dimensions must be non-negative metatile counts "
            f"(got width={frame_width_metatiles}, height={frame_height_metatiles})"
        )

    fh_px = frame_height_metatiles * METATILE_SIZE
    fw_px = frame_width_metatiles * METATILE_SIZE
    map_h, map_w = int(map_rgba.shape[0]), int(map_rgba.shape[1])
    total_h = map_h + 2 * fh_px
    total_w = map_w + 2 * fw_px

    # Fast path: zero frame — return the map as-is (with a copy so the
    # caller cannot mutate the input through the returned buffer).
    if fh_px == 0 and fw_px == 0:
        return map_rgba.copy()

    bh, bw = int(border_rgba.shape[0]), int(border_rgba.shape[1])
    # Tile the border across the entire output via modulo indexing — one
    # numpy fancy-index pass, no per-pixel Python loop.
    ys = np.arange(total_h) % bh
    xs = np.arange(total_w) % bw
    out: np.ndarray = border_rgba[ys[:, None], xs[None, :], :].copy()
    # Paste the map into the centre.
    out[fh_px : fh_px + map_h, fw_px : fw_px + map_w] = map_rgba
    return out


def mapbin_to_metatile_grid(map_bin: MapBin) -> np.ndarray:
    """Adapt an L1 :class:`MapBin` into the ``uint16[H, W]`` grid this
    module consumes.

    Drops the per-tile ``collision`` and ``elevation`` fields — those are
    overlay concerns, not base-layer geometry. The full :class:`MapBin`
    stays available to overlay renderers.
    """
    grid = np.empty((map_bin.height, map_bin.width), dtype=np.uint16)
    for y, row in enumerate(map_bin.tiles):
        for x, tile in enumerate(row):
            grid[y, x] = tile.metatile_id
    return grid


# --- Validation helpers ----------------------------------------------------


def _validate_rgba(rgba: np.ndarray, *, name: str) -> None:
    """Shared shape/dtype check for RGBA pixel buffers."""
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise LayoutAssemblyError(f"{name} shape {rgba.shape} is not (H, W, 4)")
    if rgba.dtype != np.uint8:
        raise LayoutAssemblyError(f"{name} dtype must be uint8, got {rgba.dtype}")
    if rgba.shape[0] == 0 or rgba.shape[1] == 0:
        raise LayoutAssemblyError(f"{name} has a zero pixel dimension: {rgba.shape}")
    if rgba.shape[0] % METATILE_SIZE != 0 or rgba.shape[1] % METATILE_SIZE != 0:
        raise LayoutAssemblyError(
            f"{name} dimensions {rgba.shape[0]}x{rgba.shape[1]} are not a "
            f"multiple of {METATILE_SIZE} pixels"
        )


def _validate_bank(bank: np.ndarray) -> None:
    if bank.ndim != 4 or bank.shape[1:] != (METATILE_SIZE, METATILE_SIZE, 4):
        raise LayoutAssemblyError(
            f"metatile_bank shape {bank.shape} is not (N, {METATILE_SIZE}, {METATILE_SIZE}, 4)"
        )
    if bank.dtype != np.uint8:
        raise LayoutAssemblyError(f"metatile_bank dtype must be uint8, got {bank.dtype}")
    if int(bank.shape[0]) == 0:
        raise LayoutAssemblyError("metatile_bank is empty (no metatiles)")


def _validate_grid(grid: np.ndarray, *, num_metatiles: int) -> None:
    """Validate a 2D integer grid.

    Pass ``num_metatiles=-1`` to skip the upper-bound ID check (used by
    :func:`assemble_region` which delegates to :func:`assemble` after
    slicing and re-validates there).
    """
    if grid.ndim != 2:
        raise LayoutAssemblyError(f"metatile_grid must be 2D, got shape {grid.shape}")
    height, width = grid.shape
    if height == 0 or width == 0:
        raise LayoutAssemblyError(f"metatile_grid has a zero dimension: {height}x{width}")
    if not np.issubdtype(grid.dtype, np.integer):
        raise LayoutAssemblyError(f"metatile_grid dtype must be integer, got {grid.dtype}")
    if num_metatiles < 0:
        return
    grid_min = int(grid.min())
    grid_max = int(grid.max())
    if grid_min < 0 or grid_max >= num_metatiles:
        raise LayoutAssemblyError(
            f"metatile_grid contains IDs outside [0, {num_metatiles}); "
            f"min={grid_min}, max={grid_max}"
        )
