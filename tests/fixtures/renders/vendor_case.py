"""Copy a minimum project slice for one map from a pokeemerald checkout.

Usage:

    python tests/fixtures/renders/vendor_case.py \\
        --case case_01_littleroot_town \\
        --pokeemerald /path/to/your/pokeemerald \\
        --map LittlerootTown

The script:

1. Loads the source pokeemerald project to resolve the map's layout and the
   two referenced tileset directories.
2. Creates ``tests/fixtures/renders/<case>/project/`` with the *minimum*
   subset of files needed to render that one map: ``porymap.project.cfg``,
   the relevant ``data/maps/<MapName>/``, the relevant
   ``data/layouts/<MapName>/``, the two tileset directories, and stripped-
   down versions of ``data/layouts/layouts.json`` (containing only that
   one layout entry) and ``data/maps/map_groups.json`` (containing only
   that one map).
3. Does NOT vendor anything else from the source checkout — not the C
   sources, not the other maps, not the scripts. The fidelity test only
   needs the data files that ``Project`` actually reads.

Idempotent: rerun to refresh the slice after the source checkout moves.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

# Importing porymap_mcp lets us reuse the parsers + Project class to avoid
# reimplementing the layout/tileset resolution logic.
from porymap_mcp.parsers.layoutsjson import LayoutEntry
from porymap_mcp.project import Project

CORPUS_ROOT = Path(__file__).resolve().parent


def _resolve_layout(project: Project, map_bare_name: str) -> tuple[str, LayoutEntry]:
    """Find the layout entry referenced by ``data/maps/<map_bare_name>/map.json``."""
    map_json_path = project.maps_dir / map_bare_name / "map.json"
    if not map_json_path.is_file():
        raise SystemExit(
            f"map.json not found at {map_json_path} — is --map correct? "
            "Pass the bare map directory name (e.g. 'LittlerootTown', not 'MAP_LITTLEROOT_TOWN')."
        )
    text = map_json_path.read_text(encoding="utf-8")
    data = json.loads(text)
    layout_id = data.get("layout")
    if not isinstance(layout_id, str):
        raise SystemExit(f"{map_json_path} has no string 'layout' field")
    for entry in project.layouts.layouts:
        if entry.id == layout_id:
            return layout_id, entry
    raise SystemExit(f"layout {layout_id!r} (from {map_json_path}) not in layouts.json")


def _copy_tree(src: Path, dst: Path) -> None:
    """Recursive copy. Mirrors ``shutil.copytree`` but tolerates an existing dst."""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _write_minimal_layouts_json(out_path: Path, entry: LayoutEntry) -> None:
    """Write a ``layouts.json`` containing only the one layout entry the test uses."""
    obj = {
        "layouts_table_label": "gMapLayouts",
        "layouts": [
            {
                "id": entry.id,
                "name": entry.name,
                "width": entry.width,
                "height": entry.height,
                "primary_tileset": entry.primary_tileset,
                "secondary_tileset": entry.secondary_tileset,
                "border_filepath": entry.border_filepath,
                "blockdata_filepath": entry.blockdata_filepath,
            }
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _write_minimal_map_groups_json(out_path: Path, map_bare_name: str) -> None:
    """Write a ``map_groups.json`` containing only the one map under a single group."""
    obj: dict[str, Any] = {
        "group_order": ["gMapGroup_Vendored"],
        "gMapGroup_Vendored": [map_bare_name],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--case",
        required=True,
        help="Fixture directory name under tests/fixtures/renders/",
    )
    ap.add_argument(
        "--pokeemerald",
        required=True,
        type=Path,
        help="Path to source pokeemerald checkout",
    )
    ap.add_argument(
        "--map",
        required=True,
        help="Bare map directory name (e.g. LittlerootTown)",
    )
    args = ap.parse_args()

    case_dir = CORPUS_ROOT / args.case
    if not case_dir.is_dir():
        raise SystemExit(f"case directory does not exist: {case_dir}")

    src_root: Path = args.pokeemerald.resolve()
    if not src_root.is_dir():
        raise SystemExit(f"--pokeemerald is not a directory: {src_root}")

    project = Project(src_root)
    layout_id, layout_entry = _resolve_layout(project, args.map)
    primary_entry = project.get_tileset_by_label(layout_entry.primary_tileset)
    secondary_entry = project.get_tileset_by_label(layout_entry.secondary_tileset)

    dst_root = case_dir / "project"
    if dst_root.exists():
        shutil.rmtree(dst_root)
    dst_root.mkdir(parents=True)

    # 1. porymap.project.cfg
    shutil.copy2(project.config_path, dst_root / "porymap.project.cfg")

    # 2. data/maps/<MapBareName>/
    src_map_dir = project.maps_dir / args.map
    _copy_tree(src_map_dir, dst_root / "data" / "maps" / args.map)

    # 3. data/layouts/<MapBareName>/ (map.bin, border.bin, …)
    #    The layout's blockdata/border paths are project-relative POSIX paths;
    #    walk one directory up from the .bin to find the layout dir.
    blockdata = project.resolve_path(layout_entry.blockdata_filepath)
    src_layout_dir = blockdata.parent
    _copy_tree(src_layout_dir, dst_root / "data" / "layouts" / src_layout_dir.name)

    # 4. Stripped layouts.json + map_groups.json
    _write_minimal_layouts_json(dst_root / "data" / "layouts" / "layouts.json", layout_entry)
    _write_minimal_map_groups_json(dst_root / "data" / "maps" / "map_groups.json", args.map)

    # 5. Both tileset directories
    for entry in (primary_entry, secondary_entry):
        src_tileset_dir = project.resolve_path(entry.tiles_path).parent
        rel = src_tileset_dir.relative_to(src_root)
        _copy_tree(src_tileset_dir, dst_root / rel)

    # 6. Write a small VENDOR.md alongside the slice so a reviewer can verify
    #    the provenance of the bytes.
    (case_dir / "VENDOR.md").write_text(
        "# Vendored slice — auto-generated by `vendor_case.py`\n\n"
        f"- **Source repo:** {src_root}\n"
        f"- **Source map:** `{args.map}` (`{layout_id}`)\n"
        f"- **Primary tileset:** `{layout_entry.primary_tileset}`\n"
        f"- **Secondary tileset:** `{layout_entry.secondary_tileset}`\n"
        f"- **Layout size:** {layout_entry.width}x{layout_entry.height}\n\n"
        "Regenerate with:\n\n"
        "```bash\n"
        f"python tests/fixtures/renders/vendor_case.py \\\n"
        f"    --case {args.case} \\\n"
        f"    --pokeemerald {src_root} \\\n"
        f"    --map {args.map}\n"
        "```\n",
        encoding="utf-8",
    )

    print(f"Vendored {args.map} from {src_root} into {dst_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
