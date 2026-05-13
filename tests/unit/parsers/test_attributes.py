"""Tests for ``porymap_mcp.parsers.attributes``."""

from __future__ import annotations

import pytest

from porymap_mcp.errors import FormatError
from porymap_mcp.parsers import attributes

_RSE_MASKS = attributes.AttributeMasks(
    behavior=0x00FF,
    terrain_type=0x3E00,
    encounter_type=0xC000,
    layer_type=0x6000,
)


class TestShiftOf:
    def test_contiguous_low(self) -> None:
        assert attributes._shift_of(0x00FF) == 0

    def test_contiguous_mid(self) -> None:
        assert attributes._shift_of(0x3E00) == 9

    def test_contiguous_high(self) -> None:
        assert attributes._shift_of(0xC000) == 14

    def test_zero(self) -> None:
        assert attributes._shift_of(0) == 0


class TestDecode:
    def test_decodes_known_word(self) -> None:
        # behavior=0xAB, terrain_type=0b10110=0x16, encounter_type=0b10=2.
        # behavior fits 0x00FF, terrain into 0x3E00 (5 bits at shift 9):
        #   0x16 << 9 = 0x2C00
        # encounter_type into 0xC000 (2 bits at shift 14): 2 << 14 = 0x8000
        raw = 0xAB | 0x2C00 | 0x8000
        out = attributes.decode(raw, _RSE_MASKS)
        assert out.behavior == 0xAB
        assert out.terrain_type == 0x16
        assert out.encounter_type == 2
        assert out.raw == raw

    def test_zero_word(self) -> None:
        out = attributes.decode(0, _RSE_MASKS)
        assert out.behavior == 0
        assert out.terrain_type == 0
        assert out.encounter_type == 0
        assert out.layer_type == 0


class TestRead:
    def test_reads_multiple(self) -> None:
        data = (0xAA).to_bytes(2, "little") + (0xBB).to_bytes(2, "little")
        out = attributes.read(data, attribute_size=2, masks=_RSE_MASKS)
        assert len(out) == 2
        assert out[0].behavior == 0xAA
        assert out[1].behavior == 0xBB

    def test_size_mismatch_raises(self) -> None:
        with pytest.raises(FormatError, match="not a multiple"):
            attributes.read(b"\xab", attribute_size=2, masks=_RSE_MASKS)

    def test_unsupported_size(self) -> None:
        with pytest.raises(FormatError, match="unsupported"):
            attributes.read(b"\x00" * 6, attribute_size=3, masks=_RSE_MASKS)

    def test_expected_count_mismatch(self) -> None:
        with pytest.raises(FormatError, match="declares"):
            attributes.read(
                b"\x00\x00\x00\x00",
                attribute_size=2,
                masks=_RSE_MASKS,
                expected_count=5,
            )

    def test_4_byte_attribute(self) -> None:
        # Expansion-style: 4-byte attribute. Use the same masks (just for shape).
        masks4 = attributes.AttributeMasks(
            behavior=0x000001FF,
            terrain_type=0x00003E00,
            encounter_type=0x07000000,
            layer_type=0x60000000,
        )
        word = 0x01 | 0x2C00 | (0x05 << 24)
        data = word.to_bytes(4, "little")
        out = attributes.read(data, attribute_size=4, masks=masks4)
        assert out[0].behavior == 0x01
        assert out[0].encounter_type == 5
