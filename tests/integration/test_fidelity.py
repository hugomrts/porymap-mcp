"""Fidelity corpus — the L3 v1.0.0 acceptance gate.

Each case under ``tests/fixtures/renders/case_*/`` ships:

- ``project/`` — a vendored slice of a pokeemerald(-expansion) project
  pinned to one map (see ``tests/fixtures/renders/vendor_case.py`` for
  how the slices are produced).
- ``reference.png`` — Porymap's own export of that one map, with the
  flags documented in ``tests/fixtures/renders/HOW_TO_EXPORT.md``.
- ``description.md`` — human-readable description of the case.

This test renders the project with ``render_map`` and asserts that the
decoded RGBA arrays are byte-for-byte equal between our output and the
Porymap reference. PNG containers (Pillow vs Qt's libpng) differ in
permitted bytes; pixel content does not.

Each case has a ``kind`` of either ``"fidelity"`` (vs Porymap export)
or ``"regression"`` (vs a previous render of our own — only case 5).
The two kinds use the same comparison; the labelling is for the human
reading test failures.

Cases without a ``reference.png`` and / or a ``project/`` directory
are auto-skipped with a clear message — useful for incremental corpus
build-out (a maintainer can land cases one at a time).

The ``--update-golden`` pytest flag, when set, overwrites
``reference.png`` with our render instead of comparing. Maintainer-only;
CI must NOT pass this flag.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from porymap_mcp.tools import rendering as render_tools

CORPUS_ROOT = Path(__file__).parent.parent / "fixtures" / "renders"


@dataclass(frozen=True)
class Case:
    """A single fidelity-corpus case."""

    case_id: str
    map_id: str
    include_border: bool
    kind: str  # "fidelity" | "regression"


CASES: tuple[Case, ...] = (
    Case("case_01_littleroot_town", "MAP_LITTLEROOT_TOWN", include_border=True, kind="fidelity"),
    Case("case_02_route_101", "MAP_ROUTE101", include_border=True, kind="fidelity"),
    Case("case_03_granite_cave_1f", "MAP_GRANITE_CAVE_1F", include_border=False, kind="fidelity"),
    Case("case_04_expansion_layered", "", include_border=True, kind="fidelity"),
    Case("case_05_synthetic_edge", "MAP_EDGECASETOWN", include_border=True, kind="regression"),
)


def _decode_png(png_bytes: bytes) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(png_bytes)).convert("RGBA"))


def _resolve_map_id(case: Case) -> str:
    """Case 04's map id is filled in by the human at vendor time.

    The human commits ``project/data/maps/<MapBareName>/map.json`` and
    we read its ``id`` field rather than hard-coding the choice in
    this file. Other cases hard-code the map id and short-circuit.
    """
    if case.map_id:
        return case.map_id
    project = CORPUS_ROOT / case.case_id / "project"
    maps_dir = project / "data" / "maps"
    if not maps_dir.is_dir():
        pytest.skip(f"{case.case_id}: project/data/maps/ missing — vendor not run")
    map_dirs = [d for d in maps_dir.iterdir() if d.is_dir() and (d / "map.json").is_file()]
    if not map_dirs:
        pytest.skip(f"{case.case_id}: no map.json under project/data/maps/")
    if len(map_dirs) > 1:
        pytest.skip(
            f"{case.case_id}: multiple maps in project/data/maps/ — "
            "vendor_case.py should produce exactly one"
        )
    import json

    data = json.loads((map_dirs[0] / "map.json").read_text(encoding="utf-8"))
    map_id = data.get("id")
    if not isinstance(map_id, str):
        pytest.skip(f"{case.case_id}: map.json missing 'id' field")
    return map_id


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.case_id)
def test_render_matches_reference(case: Case, update_golden: bool) -> None:
    case_dir = CORPUS_ROOT / case.case_id
    project_dir = case_dir / "project"
    reference_png_path = case_dir / "reference.png"

    if not project_dir.is_dir():
        pytest.skip(f"{case.case_id}: project/ missing — vendor_case.py not run yet")

    map_id = _resolve_map_id(case)

    result = render_tools.render_map(
        str(project_dir),
        map_id,
        include_border=case.include_border,
    )
    block = result.content[0]
    assert block.type == "image"
    assert block.mimeType == "image/png"
    ours_png = base64.b64decode(block.data)

    if update_golden:
        reference_png_path.write_bytes(ours_png)
        return

    if not reference_png_path.is_file():
        pytest.skip(
            f"{case.case_id}: reference.png missing — Porymap export not committed yet "
            "(see tests/fixtures/renders/HOW_TO_EXPORT.md)"
        )

    ours = _decode_png(ours_png)
    ref = _decode_png(reference_png_path.read_bytes())

    if ours.shape != ref.shape:
        pytest.fail(
            f"{case.case_id} ({case.kind}): shape mismatch — "
            f"ours={ours.shape} ref={ref.shape}. "
            f"Suggests a wrong border size or the wrong include_border flag at export time."
        )

    diff = (ours != ref).any(axis=-1)
    n_diff = int(diff.sum())
    if n_diff == 0:
        return

    ys, xs = np.where(diff)
    y, x = int(ys[0]), int(xs[0])
    total = int(ours.shape[0] * ours.shape[1])
    pct = 100.0 * n_diff / total
    pytest.fail(
        f"{case.case_id} ({case.kind}): {n_diff}/{total} pixels differ ({pct:.2f}%). "
        f"First mismatch at ({x},{y}): ours={tuple(int(c) for c in ours[y, x])}, "
        f"ref={tuple(int(c) for c in ref[y, x])}."
    )
