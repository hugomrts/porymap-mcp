# ADR-0003: `Project` class as single entrypoint, config-driven format parameters

- **Status:** Accepted
- **Date:** 2026-05-13
- **Deciders:** Hugo Martins

---

## Context

Phase 2 implementation is about to leave the pure-parser stage. The next two files on the critical path are `parsers/projectconfig.py` and `project.py` — the latter is the object every L1 tool will receive (or construct from `project_path`). Two coupled design questions need an answer before we write either:

1. **How do tools access project state?** Each MCP tool already takes `project_path` as its first argument (per `CLAUDE.md` §5). But should the server keep a long-lived `Project` cached per path, or construct one per call?
2. **How do parsers know which format variant they're reading?** ADR-0002 commits us to pokeemerald-expansion first, with vanilla and FireRed branched later. The naive reading of that ADR is "branch the parsers on `base_game_version`". But Porymap's actual on-disk config is more granular than that: `porymap.project.cfg` carries **explicit fields** for the metatile-id mask, collision mask, elevation mask, attribute size, layer mask, etc. (verified against Porymap `src/config.cpp` lines 1238–1322). Expansion sets `base_game_version=pokeemerald` and overrides those masks. So branching solely on `base_game_version` would silently miss expansion's overrides.

The dispatch mechanism we pick here propagates into every parser signature and every tool. Changing it later is a wide refactor.

---

## Decision

### 1. `Project` is the single entrypoint for tools

Every MCP tool that touches a project takes `project_path: Path` as its first argument and constructs a `Project(project_path)` at the top of the function. The server holds **no persistent project state** between tool calls.

```python
@mcp.tool()
def get_map_info(project_path: Path, map_name: str) -> dict[str, Any]:
    project = Project.load(project_path)
    layout = project.layout(map_name)
    ...
```

`Project.load(path)` is the only constructor. It is the function that may raise `ProjectError`, `UnsupportedBaseGameError`, or `FormatError`. After `.load()` returns, the `Project` is a frozen, internally consistent view of the on-disk project at that instant.

### 2. Stateless tools, per-call load, file system is the source of truth

No caching across calls. Each tool call re-reads the relevant files. This is acceptable for L1 (no `render_map`, no large bitmaps; only JSON + small `.bin` files) and it gives us three invariants for free:

- **No stale state.** A user editing files in another window between tool calls will not surprise us.
- **No cache invalidation.** We do not implement, document, or test it.
- **Multi-project safe.** Two concurrent tool calls on different `project_path`s share nothing.

L2 (file watcher) and L3 (rendering) will revisit caching when they have a concrete need. We do **not** speculate now.

### 3. Format parameters flow through `Project.config`, parsers do not branch on `base_game_version`

`Project` exposes a `ProjectConfig` value object that carries the *resolved* format parameters:

```python
@dataclass(frozen=True, slots=True)
class ProjectConfig:
    base_game_version: BaseGameVersion          # enum: POKEEMERALD | POKERUBY | POKEFIRERED
    metatile_id_mask: int
    collision_mask: int
    elevation_mask: int
    metatile_attributes_size: int                # 2 or 4 bytes
    behavior_mask: int
    terrain_type_mask: int
    encounter_type_mask: int
    layer_type_mask: int
    triple_layer_metatiles: bool
    use_poryscript: bool
    use_custom_border_size: bool
    default_map_width: int
    default_map_height: int
    paths: Mapping[str, str]                     # path/* overrides, POSIX, relative to project root
    prefabs_filepath: str | None
    unknown_keys: Mapping[str, str]              # preserved for round-trip
```

Parsers that need any of these values take them as **explicit parameters**, never as a `base_game_version` enum:

```python
# YES — parser receives the parameters it needs
def decode_tile(word: int, *, id_mask: int, collision_mask: int, elevation_mask: int) -> Tile: ...

# NO — parser inspects a "version" enum and infers masks
def decode_tile(word: int, base_game: BaseGameVersion) -> Tile: ...
```

Rationale: this matches how Porymap *actually* stores the variation (explicit masks, not a version switch). Expansion's overrides flow through naturally with zero special-casing. Adding vanilla pokeemerald or FireRed in a later release is a matter of (a) adding their defaults to the `BaseGameVersion → defaults` table and (b) accepting that `base_game_version` value in `Project.load()` — no parser changes.

### 4. Defaults are resolved at `Project.load()` time, not inside parsers

`porymap.project.cfg` omits keys that take their default. The defaults *depend on* `base_game_version`. Resolution happens once, in one place — `projectconfig.read()` — so every downstream parser sees a fully-populated `ProjectConfig` and never needs to know what was implicit vs. explicit on disk.

Implementation sketch:

```python
def read(path: Path) -> ProjectConfig:
    raw = _read_kv_file(path)
    bgv = BaseGameVersion(raw["base_game_version"])  # required, raises if missing/unknown
    defaults = _DEFAULTS_BY_VERSION[bgv]
    return ProjectConfig(
        base_game_version=bgv,
        metatile_id_mask=_int(raw.get("block_metatile_id_mask"), defaults.metatile_id_mask),
        ...,
        unknown_keys={k: v for k, v in raw.items() if k not in _KNOWN_KEYS},
    )
```

### 5. `base_game_version` is a coarse compatibility gate, nothing else

The enum is used for exactly three things:

1. Selecting the defaults table when a field is missing from the cfg.
2. Gating `UnsupportedBaseGameError`: in v0.1.0 we accept `pokeemerald` only; the gate lives in `Project.load()`, not in parsers.
3. Cosmetic surfacing in `get_project_info` so the MCP client can show the user which decomp variant they're editing.

It is **never** a switch statement inside a parser.

---

## Alternatives considered

### Alternative 1 — Long-lived `Project` cached per path

Keep a `dict[Path, Project]` on the server; reuse across tool calls; invalidate on file mtime.

- **Upside:** zero re-read cost; potentially faster on chatty clients.
- **Downside:** cache invalidation logic, mtime races on networked filesystems, surprising "stale view" bugs when the user edits files in another tool, and an extra concurrency surface (the LLM is single-threaded but the server can still see overlapping awaits).
- **Why not:** L1 reads are cheap (`map.bin` is at most a few KB, JSON is small). The performance need is hypothetical; the bug surface is real. Caching can be added later behind the *same* `Project.load()` signature without breaking tools — no need to commit now.

### Alternative 2 — Branch parsers on `BaseGameVersion`

`decode_tile(word, base_game=BaseGameVersion.POKEEMERALD)` and let the parser pick masks from an internal table.

- **Upside:** fewer parser arguments; "the parser knows what game it is".
- **Downside:** silently wrong for pokeemerald-expansion, which uses `base_game_version=pokeemerald` but overrides the masks. We would have to introduce a synthetic `POKEEMERALD_EXPANSION` value that doesn't exist in any real `.cfg`, then map config → enum ourselves. That's a fiction layer between us and Porymap.
- **Why not:** misaligned with how Porymap stores the variation. The fiction would leak into every error message, every test fixture, every contributor's mental model.

### Alternative 3 — Strategy / subclass per base game (`EmeraldProject`, `FireRedProject`, ...)

Polymorphic dispatch via subclasses, each with its own parser bindings.

- **Upside:** Pythonic-feeling OO.
- **Downside:** the variation is *one dict of constants*, not behavior. Subclassing to dispatch on a constant is over-engineering; pokeemerald-expansion would still need a separate subclass that differs from `EmeraldProject` only by a few mask values; we'd argue forever about whether expansion inherits from emerald or is a sibling.
- **Why not:** the configuration-as-data model is simpler and matches Porymap exactly.

### Alternative 4 — Global server context with implicit "current project"

A `current_project` is set on the server; tools omit `project_path`.

- **Upside:** terser tool signatures.
- **Downside:** silently breaks multi-project workflows; agents would need a hidden `select_project` step; a wrong call could mutate the wrong project. Violates `CLAUDE.md` §5 ("Project path is always the first argument").
- **Why not:** non-starter; explicitly forbidden in the operating manual.

---

## Consequences

**Positive:**
- Tools are trivially testable — pass a `Path`, get a result. No fixture setup beyond the on-disk fixture project.
- Adding vanilla `pokeemerald` or `pokefirered` in v0.2.0 is purely additive: extend the `_DEFAULTS_BY_VERSION` table, drop the gate in `Project.load()`, write one fixture per new version. No parser refactor.
- Pokeemerald-expansion works on day one without any special enum value — its mask overrides ride through the config.
- Round-tripping `porymap.project.cfg` is straightforward: preserve `unknown_keys` and re-emit known keys alphabetically (matches Porymap's output for clean `git diff`).
- The MCP server has no global mutable state. Concurrency, hot-reload, and multi-tenant deployment are all open paths.

**Negative:**
- Parsers gain arguments. `decode_tile` now takes three masks instead of one base-game enum. Mitigated: pass them once at the call site (the tool layer holds the `Project`).
- Per-call `.load()` re-reads JSON and the cfg every time. For L1 this is negligible; if profiling later shows it dominates, a memoized loader can be added under the same signature without touching tool code.
- `Project.load()` becomes a wide function: cfg + layouts.json + map_groups.json + tilesets headers. We accept that — it's exactly the price of "no stale state". We will split it into lazy properties (`project.config`, `project.layouts`, ...) so cost is paid only for what a tool actually reads.

**Neutral:**
- `ProjectConfig` is a frozen dataclass with ~15 fields. Verbose, but every field is justified by a real Porymap key.
- `BaseGameVersion` is an `enum.Enum` (not `StrEnum`) with values matching Porymap's strings exactly: `pokeruby`, `pokefirered`, `pokeemerald`. The `UnsupportedBaseGameError` already declares `declared` and `supported` strings; we route through this without change.

---

## References

- Related ADRs:
  - [ADR-0001](0001-fastmcp-as-mcp-framework.md) — FastMCP is the framework consuming `Project`-using tools.
  - [ADR-0002](0002-target-pokeemerald-expansion-first.md) — establishes the supported-version policy this ADR implements concretely.
- Porymap config source: `src/config.cpp` (lines 379–403 for the reader; 1238–1322 for `ProjectConfig::getKeyValueMap`; 1066–1068 / 1148–1150 for the `BaseGameVersion` enum strings) — https://github.com/huderlem/porymap/blob/master/src/config.cpp
- Phase doc affected: [`phase-2-l1-filesystem.md`](../phases/phase-2-l1-filesystem.md) — implementation order steps 1 (`parsers/projectconfig.py`) and 2 (`project.py`).
- Operating manual: `CLAUDE.md` §5 (MCP tool design rules — "project path is always the first argument").
