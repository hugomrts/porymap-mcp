"""Tests for ``porymap_mcp.render.encode``.

Every test builds a small RGBA numpy array, encodes it, and rounds-trips
the bytes back through Pillow to assert *pixel-identical* output. That is
the ADR-0010 §"Fidelity criterion" — palette mode must be lossless.
"""

from __future__ import annotations

import io
from typing import cast

import numpy as np
import pytest
from PIL import Image

from porymap_mcp.errors import PngEncodeError
from porymap_mcp.render.encode import (
    PALETTE_MODE_MAX_METATILES,
    encode_png,
    package_render_result,
)


def _opaque(rgb: tuple[int, int, int]) -> tuple[int, int, int, int]:
    return (rgb[0], rgb[1], rgb[2], 255)


def _decode(png_bytes: bytes) -> np.ndarray:
    """Decode PNG bytes back to a ``uint8 (H, W, 4)`` RGBA array via Pillow."""
    return np.array(Image.open(io.BytesIO(png_bytes)).convert("RGBA"))


# --- encode_png: encoding-mode selection ----------------------------------


class TestEncodePngModeSelection:
    def test_small_opaque_image_uses_palette_mode(self) -> None:
        rgba = np.zeros((16, 16, 4), dtype=np.uint8)
        rgba[..., 3] = 255
        rgba[0:8, :, 0] = 200
        rgba[8:16, :, 1] = 100
        _, enc = encode_png(rgba, area_metatiles=1)
        assert enc == "png-palette-8"

    def test_force_rgba_overrides_palette(self) -> None:
        rgba = np.zeros((16, 16, 4), dtype=np.uint8)
        rgba[..., 3] = 255
        _, enc = encode_png(rgba, area_metatiles=1, force_rgba=True)
        assert enc == "png-rgba-8"

    def test_area_above_threshold_forces_rgba(self) -> None:
        rgba = np.zeros((16, 16, 4), dtype=np.uint8)
        rgba[..., 3] = 255
        _, enc = encode_png(rgba, area_metatiles=PALETTE_MODE_MAX_METATILES + 1)
        assert enc == "png-rgba-8"

    def test_area_exactly_at_threshold_uses_palette(self) -> None:
        rgba = np.zeros((16, 16, 4), dtype=np.uint8)
        rgba[..., 3] = 255
        _, enc = encode_png(rgba, area_metatiles=PALETTE_MODE_MAX_METATILES)
        assert enc == "png-palette-8"

    def test_more_than_256_colours_falls_back_to_rgba(self) -> None:
        # 17x16 = 272 pixels, all distinct colours.
        rgba = np.zeros((16, 17, 4), dtype=np.uint8)
        rgba[..., 3] = 255
        flat = rgba.reshape(-1, 4)
        for i in range(flat.shape[0]):
            flat[i, 0] = i % 256
            flat[i, 1] = (i // 256) % 256
            flat[i, 2] = i & 0xFF
        # Inject more than 256 distinct values
        assert (
            np.unique(
                (rgba[..., 0].astype(np.uint32) << 16)
                | (rgba[..., 1].astype(np.uint32) << 8)
                | rgba[..., 2].astype(np.uint32)
            ).shape[0]
            > 256
        )
        _, enc = encode_png(rgba, area_metatiles=2)
        assert enc == "png-rgba-8"

    def test_any_non_opaque_pixel_falls_back_to_rgba(self) -> None:
        # Single semi-transparent pixel forces RGBA (overlay path).
        rgba = np.zeros((4, 4, 4), dtype=np.uint8)
        rgba[..., 3] = 255
        rgba[0, 0, 3] = 200  # one translucent pixel
        _, enc = encode_png(rgba, area_metatiles=1)
        assert enc == "png-rgba-8"


# --- encode_png: round-trip correctness -----------------------------------


class TestEncodePngRoundTrip:
    def test_palette_round_trip_is_lossless(self) -> None:
        # Build an image with three distinct RGB blocks; palette encode
        # must decode back byte-for-byte identical.
        rgba = np.zeros((16, 16, 4), dtype=np.uint8)
        rgba[..., 3] = 255
        rgba[0:5, :] = _opaque((10, 20, 30))
        rgba[5:11, :] = _opaque((100, 0, 0))
        rgba[11:16, :] = _opaque((0, 100, 0))
        png, enc = encode_png(rgba, area_metatiles=1)
        assert enc == "png-palette-8"
        assert np.array_equal(_decode(png), rgba)

    def test_rgba_round_trip_is_lossless(self) -> None:
        # Random-ish pattern with >256 unique colours; RGBA round-trip.
        rgba = np.zeros((16, 17, 4), dtype=np.uint8)
        rgba[..., 3] = 255
        flat = rgba.reshape(-1, 4)
        for i in range(flat.shape[0]):
            flat[i, 0] = i % 256
            flat[i, 1] = (i * 7) % 256
            flat[i, 2] = (i * 13) % 256
        png, _ = encode_png(rgba, area_metatiles=2)
        # Either palette mode (if <= 256 unique) or rgba — both must round-trip.
        assert np.array_equal(_decode(png), rgba)

    def test_palette_round_trip_for_solid_image(self) -> None:
        rgba = np.full((8, 8, 4), 255, dtype=np.uint8)
        rgba[..., 0] = 50
        rgba[..., 1] = 60
        rgba[..., 2] = 70
        png, enc = encode_png(rgba, area_metatiles=1)
        assert enc == "png-palette-8"
        assert np.array_equal(_decode(png), rgba)

    def test_force_rgba_round_trip(self) -> None:
        rgba = np.full((4, 4, 4), 255, dtype=np.uint8)
        rgba[..., 0] = 200
        png, _ = encode_png(rgba, area_metatiles=1, force_rgba=True)
        assert np.array_equal(_decode(png), rgba)


# --- encode_png: validation -----------------------------------------------


class TestEncodePngValidation:
    def test_rejects_wrong_shape(self) -> None:
        with pytest.raises(PngEncodeError, match="shape"):
            encode_png(np.zeros((16, 16, 3), dtype=np.uint8), area_metatiles=1)

    def test_rejects_2d_input(self) -> None:
        with pytest.raises(PngEncodeError, match="shape"):
            encode_png(np.zeros((16, 16), dtype=np.uint8), area_metatiles=1)

    def test_rejects_wrong_dtype(self) -> None:
        with pytest.raises(PngEncodeError, match="dtype"):
            encode_png(np.zeros((4, 4, 4), dtype=np.float32), area_metatiles=1)

    def test_rejects_zero_dim(self) -> None:
        with pytest.raises(PngEncodeError, match="zero dimension"):
            encode_png(np.zeros((0, 16, 4), dtype=np.uint8), area_metatiles=1)

    def test_rejects_negative_area(self) -> None:
        rgba = np.zeros((4, 4, 4), dtype=np.uint8)
        rgba[..., 3] = 255
        with pytest.raises(PngEncodeError, match="area_metatiles"):
            encode_png(rgba, area_metatiles=-1)


# --- package_render_result --------------------------------------------------


class TestPackageRenderResult:
    def test_returns_toolresult_with_image_and_structured_content(self) -> None:
        rgba = np.full((4, 4, 4), 255, dtype=np.uint8)
        png, enc = encode_png(rgba, area_metatiles=1)
        result = package_render_result(
            png, summary="rendered", extra={"encoding": enc, "width_px": 4}
        )

        # ToolResult always has at least one content block: the image.
        assert len(result.content) == 1
        block = result.content[0]
        assert block.type == "image"
        assert block.mimeType == "image/png"
        # data is base64; we don't assert exact contents (Pillow's encode
        # is deterministic but Pillow-version-dependent). Just confirm it
        # round-trips as a PNG.
        import base64

        decoded = base64.b64decode(block.data)
        re_png = Image.open(io.BytesIO(decoded))
        assert re_png.format == "PNG"

        # Structured content carries summary + extras.
        sc = cast(dict[str, object], result.structured_content)
        assert sc["summary"] == "rendered"
        assert sc["encoding"] == "png-palette-8"
        assert sc["width_px"] == 4

    def test_summary_overrides_collision_in_extra(self) -> None:
        # Caller's `extra={"summary": "bad"}` must lose to the explicit
        # `summary=` kwarg — the explicit field is the canonical channel.
        rgba = np.full((4, 4, 4), 255, dtype=np.uint8)
        png, _ = encode_png(rgba, area_metatiles=1)
        result = package_render_result(png, summary="good", extra={"summary": "bad", "other": 1})
        sc = cast(dict[str, object], result.structured_content)
        assert sc["summary"] == "good"
        assert sc["other"] == 1

    def test_extra_none_is_accepted(self) -> None:
        rgba = np.full((4, 4, 4), 255, dtype=np.uint8)
        png, _ = encode_png(rgba, area_metatiles=1)
        result = package_render_result(png, summary="ok")
        sc = cast(dict[str, object], result.structured_content)
        assert sc == {"summary": "ok"}
