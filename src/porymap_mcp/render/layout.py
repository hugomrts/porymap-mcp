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
