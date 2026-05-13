# ADR-0008: Prefab library format and `paint_prefab` semantics

- **Status:** Accepted
- **Date:** 2026-05-13
- **Deciders:** project owner

---

## Context

Phase doc §3 froze two prefab-related tools:

- `list_prefabs(project_path)` — already ships (ADR-0005 §6); currently returns `[]`.
- `paint_prefab(project_path, map_name, prefab_name, x, y)` — stamps a named metatile pattern at `(x, y)`.

Phase doc §8 OQ1 (resolved here): "Should `paint_prefab` reject when the target tileset doesn't include the prefab's metatiles, or auto-import them? Default: reject."

This ADR specifies the prefab library format that ships with `porymap-mcp` and the semantics of `paint_prefab`. The library is intentionally minimal in v0.1.0 — three demonstration prefabs that prove the system works. The Phase-2 ROM-hack community will grow it.

---

## Decision

### Library format

Prefabs are **declared as Python `Prefab` dataclass instances** in `src/porymap_mcp/prefabs/library.py`. No JSON, no on-disk discovery — the library is a constant that ships with the package.

```python
@dataclass(frozen=True, slots=True)
class Prefab:
    name: str                     # e.g. "single_tree"
    width: int                    # tiles
    height: int                   # tiles
    description: str              # one-sentence prose
    primary_tileset: str | None   # required gTileset_* C label, or None = any
    secondary_tileset: str | None # required gTileset_* C label, or None = any
    tiles: tuple[tuple[PrefabTile, ...], ...]  # [y][x]

@dataclass(frozen=True, slots=True)
class PrefabTile:
    metatile_id: int
    collision: int = 0
    elevation: int = 0
```

`LIBRARY: dict[str, Prefab]` is the registry. `list_prefabs` reads from it; `paint_prefab` resolves `prefab_name` through it.

### v0.1.0 contents

Three demonstration prefabs, intentionally tileset-agnostic (both `primary_tileset` and `secondary_tileset` are `None`):

- `single_tree` (1×1) — a tall-tree stamp.
- `flower_patch` (2×2) — a 2×2 decorative patch.
- `house_small` (3×3) — a small house footprint.

The metatile ids in v0.1.0 are placeholders meaningful for vanilla pokeemerald's `gTileset_General` / `gTileset_LittlerootTown` pair (the most common tileset combo for towns). They are documented as **"may need retargeting for your tileset"**. The README explains how to register a custom prefab.

### `paint_prefab` semantics

```python
def paint_prefab(
    project_path: str,
    map_name: str,
    prefab_name: str,
    x: int,
    y: int,
) -> dict[str, Any]:
```

Behavior:

1. Resolve the prefab from `LIBRARY`. Unknown name → `ProjectError` listing the available prefab names.
2. Validate tileset compatibility:
   - If `prefab.primary_tileset` is set, the map's layout `primary_tileset` must equal it.
   - Same for `secondary_tileset`.
   - Mismatch → `ProjectError("paint_prefab: tileset mismatch — prefab 'X' requires primary gTileset_Y, map uses gTileset_Z. Pick a different prefab or change the map's tileset.")`. Auto-import is rejected per phase §8 OQ1.
3. Validate placement: `x + prefab.width <= map.width` and `y + prefab.height <= map.height`. Otherwise `CoordinatesOutOfBoundsError`.
4. Stamp the tiles onto a copy of the map's layout, computing `tiles_changed` like `paint_rectangle`.
5. Idempotence: if all stamped tiles already match → no-op (`files_modified: []`, `tiles_changed: 0`).
6. Write the new `map.bin`. Returns `{summary, project_path, map_name, prefab_name, anchor: {x, y}, dimensions: {width, height}, tiles_changed, files_modified}`.

### `list_prefabs` wiring

The existing `list_prefabs` tool (ADR-0005 §6, currently returns `[]`) is updated to read from `LIBRARY`. Return shape is unchanged: `{summary, project_path, prefabs: list[{name, width, height, tileset_requirements: {primary, secondary}, description}]}`.

---

## Alternatives considered

### Alternative 1 — JSON-based prefab library
- **Upside:** Users can add prefabs without recompiling the package.
- **Downside:** v0.1.0 ships with 3 stubs; on-disk discovery adds parser complexity for negligible day-one value.
- **Why not:** Defer to v0.2.0. The Python dataclass library is trivially extendable by forks (subclass + monkey-patch `LIBRARY`).

### Alternative 2 — Auto-import missing metatiles
- **Upside:** Prefab works on any map.
- **Downside:** Modifies the tileset, which is a destructive cross-cutting change far outside `paint_prefab`'s scope. Conflicts with the rh-hideout convention of tilesets as carefully-curated artist work.
- **Why not:** Rejected per phase §8 OQ1.

### Alternative 3 — Ship empty library, defer prefabs entirely to v0.2.0
- **Upside:** No "demonstration prefabs with placeholder IDs" awkwardness.
- **Downside:** `paint_prefab` already in the phase-doc tool list; if we ship it returning errors for every prefab name, the tool is dead-on-arrival. We may as well have three example prefabs proving the wiring works.
- **Why not:** Three small prefabs cost ~80 lines and prove the system.

---

## Consequences

- **Positive:**
  - `list_prefabs` becomes useful and `paint_prefab` ships in v0.1.0.
  - Library format is Python-dataclass-clean: trivially extendable by forks.
  - Tileset compatibility check protects users from invisible corruption (stamping a prefab into the wrong tileset would silently render wrong).

- **Negative:**
  - v0.1.0 prefab metatile IDs target vanilla pokeemerald conventions; forks must retarget. Documented in README.
  - No on-disk extensibility yet — users must contribute prefabs upstream or monkey-patch `LIBRARY`.

- **Neutral:**
  - One new package: `src/porymap_mcp/prefabs/` with `library.py`.
  - `tools/discovery.py`'s `list_prefabs` is updated; signature unchanged.
  - `tools/maps.py` gains `paint_prefab`.

---

## Open questions (deferred)

- **OQ-A — On-disk JSON prefab library.** v0.2.0. Format: `data/prefabs/<name>.json` either bundled in the project or discovered globally.
- **OQ-B — Tileset retargeting helper.** A tool that auto-maps prefab metatile IDs from a source tileset to a target tileset using visual similarity. Future work, possibly v1.0+.
- **OQ-C — Anchor variants.** Currently `(x, y)` is the top-left corner. Other anchors (center, bottom-left) are deferred; trivial to add as a kwarg.

---

## References

- ADR-0005 §6 (`list_prefabs` empty-shipping rationale, now superseded for behavior but the return shape is unchanged).
- ADR-0006 (mutation-tool conventions: `files_modified`, idempotence, bounds errors).
- Phase doc: `docs/phases/phase-2-l1-filesystem.md` §3, §8 OQ1 (resolved here).
