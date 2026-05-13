"""Tests for ``porymap_mcp.parsers.metatiles``."""

from __future__ import annotations

import pytest

from porymap_mcp.errors import FormatError
from porymap_mcp.parsers import metatiles


class TestBytesPerMetatile:
    def test_two_layer(self) -> None:
        assert metatiles.bytes_per_metatile(triple_layer=False) == 16

    def test_triple_layer(self) -> None:
        assert metatiles.bytes_per_metatile(triple_layer=True) == 24


class TestCountMetatiles:
    def test_two_layer_count(self) -> None:
        assert metatiles.count_metatiles(b"\x00" * 64, triple_layer=False) == 4

    def test_triple_layer_count(self) -> None:
        assert metatiles.count_metatiles(b"\x00" * 72, triple_layer=True) == 3

    def test_empty(self) -> None:
        assert metatiles.count_metatiles(b"", triple_layer=False) == 0

    def test_size_mismatch_raises(self) -> None:
        with pytest.raises(FormatError, match="not a multiple"):
            metatiles.count_metatiles(b"\x00" * 17, triple_layer=False)

    def test_triple_layer_mismatch_raises(self) -> None:
        with pytest.raises(FormatError, match="triple-layer"):
            metatiles.count_metatiles(b"\x00" * 16, triple_layer=True)
