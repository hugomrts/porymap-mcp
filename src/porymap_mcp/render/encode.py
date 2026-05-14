"""PNG encode + FastMCP ``ToolResult`` packaging for the L3 renderer.

Per ADR-0010 §"PNG encoding" + §"MCP return shape":

* **Palette mode** (``PIL`` mode ``"P"``) is the default when no overlay is
  present and the map area is ``<= 4096`` metatiles. Typically yields under
  60 KB for a 30x20 map, well below the 100 KB target. Lossless: built
  from numpy ``np.unique`` over the packed RGB values, so the indexed PNG
  decodes back to exactly the input pixels.
* **RGBA mode** (PIL mode ``"RGBA"``) is the fallback. Used when the area
  exceeds the threshold, when an overlay forces RGBA, or when the image
  has more than 256 distinct RGB values (or any non-opaque pixel) and
  palette mode would have to lossily quantize.
* ``optimize=True`` is only passed to Pillow when ``area_metatiles <= 4096``;
  above that the encode-time cost dominates and we drop it.

``package_render_result(png_bytes, summary=..., extra=...)`` wraps the
encoded bytes into the canonical ``ToolResult(content=[Image(...)],
structured_content={...})`` shape that ``tools/rendering.py`` will return.

References:
    - ADR-0010 §"PNG encoding".
    - ADR-0010 §"MCP return shape".
    - FastMCP image content: https://gofastmcp.com/servers/tools
"""

from __future__ import annotations

import io
from typing import Any, Final, Literal

import numpy as np
from PIL import Image as PILImage

from porymap_mcp.errors import PngEncodeError

#: Largest map area, in metatiles, that gets the palette-PNG encode path.
#: Above this, the savings from indexed mode no longer pay for the encode
#: time. See ADR-0010 §"PNG encoding".
PALETTE_MODE_MAX_METATILES: Final = 4096

#: Maximum distinct colours an indexed PNG palette can hold (PNG-8 / GBA-8).
_PALETTE_MAX_COLOURS: Final = 256

#: Encoding-name string returned alongside the PNG bytes — surfaced to the
#: agent through the structured content under the ``"encoding"`` key.
EncodingName = Literal["png-palette-8", "png-rgba-8"]


def encode_png(
    rgba: np.ndarray,
    *,
    area_metatiles: int,
    force_rgba: bool = False,
) -> tuple[bytes, EncodingName]:
    """Encode an RGBA image array to PNG bytes.

    Args:
        rgba: ``uint8`` array shape ``(H, W, 4)`` — typically the output of
            :func:`porymap_mcp.render.layout.assemble`.
        area_metatiles: Map area in *metatiles* (not pixels). Used to pick
            the palette-vs-RGBA path and the Pillow ``optimize`` flag per
            ADR-0010 §"PNG encoding".
        force_rgba: Caller forces RGBA mode — used by the overlay path
            (``collision``, ``elevation``, ``grid``, ``events``) since
            overlays require true alpha.

    Returns:
        ``(png_bytes, encoding_name)``. ``encoding_name`` is one of
        ``"png-palette-8"`` (indexed) or ``"png-rgba-8"`` (truecolour).

    Raises:
        PngEncodeError: ``rgba`` is not ``uint8 (H, W, 4)``, has a zero
            dimension, or ``area_metatiles`` is negative.
    """
    _validate_rgba(rgba)
    if area_metatiles < 0:
        raise PngEncodeError(f"area_metatiles must be >= 0, got {area_metatiles}")

    optimize = area_metatiles <= PALETTE_MODE_MAX_METATILES
    can_try_palette = (not force_rgba) and optimize

    if can_try_palette:
        palette_img = _to_indexed_palette(rgba)
        if palette_img is not None:
            buf = io.BytesIO()
            palette_img.save(buf, format="PNG", optimize=optimize)
            return buf.getvalue(), "png-palette-8"

    rgba_img = PILImage.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    rgba_img.save(buf, format="PNG", optimize=optimize)
    return buf.getvalue(), "png-rgba-8"


def package_render_result(
    png_bytes: bytes,
    *,
    summary: str,
    extra: dict[str, Any] | None = None,
) -> Any:
    """Wrap encoded PNG bytes into a FastMCP ``ToolResult``.

    Late-imported from :mod:`fastmcp` so importing :mod:`porymap_mcp.render`
    does not pull FastMCP into the L1 import graph. The return type is
    annotated ``Any`` for the same reason; callers in ``tools/rendering.py``
    that already import FastMCP can re-annotate when they bind it to a
    decorator.

    Args:
        png_bytes: PNG container bytes (from :func:`encode_png`).
        summary: Short human-readable line for the structured ``summary``
            field — ADR-0006's convention.
        extra: Additional structured-content keys to merge alongside
            ``summary`` (e.g. ``encoding``, ``width_px``, ``render_ms``).
            ``summary`` always wins on collision.

    Returns:
        A ``fastmcp.tools.base.ToolResult`` with the rendered PNG as an
        :class:`fastmcp.utilities.types.Image` content block plus a
        ``structured_content`` dict.
    """
    from fastmcp.tools.base import ToolResult
    from fastmcp.utilities.types import Image as FastMCPImage

    structured: dict[str, Any] = dict(extra or {})
    structured["summary"] = summary
    image = FastMCPImage(data=png_bytes, format="png")
    return ToolResult(
        content=[image.to_image_content()],
        structured_content=structured,
    )


# --- Internal helpers ------------------------------------------------------


def _to_indexed_palette(rgba: np.ndarray) -> PILImage.Image | None:
    """Convert an RGBA array to a PIL ``"P"``-mode image *without* lossy
    quantization. Returns ``None`` when palette encoding would have to lose
    information — callers fall back to RGBA.

    Two reasons palette encoding bails:
        1. Any pixel has ``alpha != 255``. Indexed PNGs can express
           transparency only via the ``tRNS`` chunk, which is per-palette-
           index — not per-pixel. Our renderer's compose output is opaque
           (the canvas is pre-filled), so this only triggers when an
           overlay slipped through without setting ``force_rgba``.
        2. The image has more than 256 distinct RGB values. GBA hardware
           palette + ``& 0xF8`` quantization keeps real maps well under
           that, but expansion maps with rich custom palettes can exceed
           it. The threshold is the PNG-8 palette ceiling, not a heuristic.
    """
    if not np.all(rgba[..., 3] == 255):
        return None

    rgb = rgba[..., :3]
    flat = rgb.reshape(-1, 3)
    packed = (
        (flat[:, 0].astype(np.uint32) << 16)
        | (flat[:, 1].astype(np.uint32) << 8)
        | flat[:, 2].astype(np.uint32)
    )
    uniques, inverse = np.unique(packed, return_inverse=True)
    if uniques.shape[0] > _PALETTE_MAX_COLOURS:
        return None

    indices = inverse.reshape(rgb.shape[:2]).astype(np.uint8)
    img = PILImage.fromarray(indices, mode="P")

    n = uniques.shape[0]
    palette = np.zeros(_PALETTE_MAX_COLOURS * 3, dtype=np.uint8)
    palette[0 : n * 3 : 3] = ((uniques >> 16) & 0xFF).astype(np.uint8)
    palette[1 : n * 3 : 3] = ((uniques >> 8) & 0xFF).astype(np.uint8)
    palette[2 : n * 3 : 3] = (uniques & 0xFF).astype(np.uint8)
    img.putpalette(palette.tobytes())
    return img


def _validate_rgba(rgba: np.ndarray) -> None:
    if rgba.ndim != 3 or rgba.shape[2] != 4 or rgba.dtype != np.uint8:
        raise PngEncodeError(
            f"rgba must be uint8 shape (H, W, 4); got dtype={rgba.dtype}, shape={rgba.shape}"
        )
    if rgba.shape[0] == 0 or rgba.shape[1] == 0:
        raise PngEncodeError(f"rgba has a zero dimension: shape={rgba.shape}")
