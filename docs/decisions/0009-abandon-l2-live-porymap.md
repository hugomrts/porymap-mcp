# ADR-0009: Abandon L2 (Live Porymap) and pivot directly to L3 (Vision)

- **Status:** Accepted
- **Date:** 2026-05-13
- **Deciders:** project owner

---

## Context

Phase 3 (L2 — Live Porymap) targeted *autonomous* live sync: when the agent edits the project, Porymap reloads within ~500 ms with no human action, no spurious modal prompts, and graceful degradation when Porymap is closed. See [`phase-3-l2-live-porymap.md`](../phases/phase-3-l2-live-porymap.md) §2 exit criteria.

A two-pass static audit of Porymap master (huderlem/porymap) — see Session log of the phase doc for sources — established the following facts:

1. **Porymap's native `QFileSystemWatcher` deliberately excludes the files we mutate.** `src/project/project.cpp` registers watches on `layouts.json`, `map_groups.json`, `region_map_entries.json`, `wild_encounters.json`, tileset *headers*, and several constants headers — but **not** `data/maps/<MAP>/map.json`, **not** `data/layouts/<LAYOUT>/map.bin`, **not** `border.bin`, **not** `metatile_attributes.bin`. The `map.json` exclusion is intentional (CHANGELOG 6.0.0: *"Fix all map.json files being added to the file watcher at launch."* — handle-exhaustion fix).

2. **When a watch *does* fire, the UX is a project-wide modal prompt** (`MainWindow::showFileWatcherWarning`: *"The file %1 has changed on disk. Would you like to reload the project?"*). Reload is whole-project, not file-scoped. Not "no human action".

3. **Porymap's JS scripting engine is a bare `QJSEngine` with `ConsoleExtension` only** (`src/scriptapi/scripting.cpp:42`). Static enumeration of every `Q_INVOKABLE` exposed to JS confirms: no `readFile`, no `fileExists`, no `stat`/`lastModified`, no `XMLHttpRequest` (QML-only, unavailable here), no `QFile`/`QNetwork`/`QTcp`/`QLocal`/`QWebSocket` binding. The one path-aware call (`overlay.addImage`) returns `void` to JS — no observable signal.

4. **No `map.reload()` / `project.reload()` / `reloadMap(name)` exists** in the scripting API. The closest call, `map.redraw()`, repaints from in-memory state and does **not** re-read disk.

5. **WSL2 ⇄ Windows is our actual setup** and is exactly where Qt's `QFileSystemWatcher` is least reliable (9P over `\\wsl$\` is a known weak spot for `ReadDirectoryChangesW`-based watchers).

Combined: a sentinel-file bridge script is impossible (the script cannot read disk), and Porymap's native watcher does not cover the right files. The only mechanically-feasible L2 paths are (a) touching a watched index file to force the modal prompt after every mutation, or (b) contributing `script.readFile` / `map.reload` upstream to Porymap. Neither matches the original phase-3 exit criteria; option (b) is on an external timeline.

Independently, the project's stated reason to exist — `paint → render → critique → fix → re-render` (`CLAUDE.md` §3, "Quality loop") — depends on L3 (Vision), not L2. L2's value is "user watches the agent build live". L3's value is "Claude sees its own output and improves it". The latter is the project's directive.

---

## Decision

We **abandon Phase 3 (L2 — Live Porymap)** as a shipped phase of `porymap-mcp` and pivot directly to **Phase 4 (L3 — Vision)** as the immediate next phase.

Concretely:

- Phase 3 status moves from *Next* to **Abandoned**. The phase doc remains in the repository as a record of the investigation and its conclusion.
- Phase 4 (L3) becomes the active phase. The renderer (`src/porymap_mcp/render/`), `render_map` family of tools, and the self-critique loop are the next deliverables. Versioning becomes: L3 ships as `v1.0.0` per the phase-4 doc (skipping `v0.2.0`); the L2 version slot is left unused.
- Phase 5 (PyPI publish) remains deferred. The owner's directive: publish only once L3 ships and there is real visual value to demonstrate. `v0.1.0` stays a GitHub tag, not a PyPI release.
- A **personal Porymap fork** providing local live-reload (e.g. a user-side build with `script.readFile` patched in) is out of scope for `porymap-mcp` proper. Any user who wants live reload can maintain such a fork independently; the MCP server will not depend on or require it.

This decision is not a deferral — there is no scheduled return to L2. If Porymap upstream gains the missing primitives (`script.readFile`, `map.reload`, an IPC channel, or watcher coverage for `map.bin`/`map.json`), a future ADR may reopen L2 as an *optional enhancement* to L3. It will not be a separate phase.

---

## Alternatives considered

### Alternative 1 — Ship a narrowed L2 v0.2.0 (Approach D, modal reload)
- **Upside:** Mechanically works today. ~1 day of code. Every successful mutation touches `layouts.json`'s mtime so Porymap's native watcher fires its "Reload project?" prompt; user clicks once per batch.
- **Downside:** Trades a clear UX ("agent edits, user reloads when they like") for a worse one (a modal pops on every paint, interrupting the user's read of the agent's actions). Whole-project reload also resets Porymap's undo stack and any panning/zoom state. None of this UX investment carries over to L3 — every line of the bridge code is throwaway once L3 lets the agent see its own output without Porymap at all.
- **Why not:** Negative ROI. L3 makes L2's value obsolete (the agent no longer needs Porymap to be open to see its work).

### Alternative 2 — Upstream contribution to Porymap (`script.readFile` or `map.reload`)
- **Upside:** Unlocks the original autonomous-sync vision and benefits every Porymap user.
- **Downside:** External dependency on a maintainer we don't control. Realistic timeline is weeks-to-months: PR review, possible API debate (security implications of `readFile` from a script), release cadence. The project owner explicitly rejected non-mastered external dependencies.
- **Why not:** Out of our control. We will not block L3 on it. May happen in parallel, on someone else's initiative, in which case future-us can reopen the question.

### Alternative 3 — PyPI publish v0.1.0 first
- **Upside:** Real users can `pip install porymap-mcp` today.
- **Downside:** L1 alone (map files editable, no visual feedback) is not the compelling value proposition. Publishing now spends the project's one "first impression" before L3. The owner's directive is to publish *with* L3.
- **Why not:** Premature. Defer to post-L3.

### Alternative 4 — Maintain a `porymap-mcp` fork of Porymap
- **Upside:** We could ship a patched Porymap binary with `script.readFile` and a bundled JS bridge, giving local autonomous sync.
- **Downside:** Requires us to track Porymap upstream, build cross-platform binaries, sign them, distribute them. Massive scope creep for a Python MCP server project.
- **Why not:** Out of scope. A user who wants live local reload can fork Porymap on their own; `porymap-mcp` does not bundle or assume it.

---

## Consequences

- **Positive:**
  - The roadmap is honest. Anyone reading `STATUS.md` and the phase docs sees what's achievable and what isn't.
  - All implementation energy in upcoming sessions goes to L3 (the project's strategic core), not to a workaround that L3 makes redundant.
  - The version timeline collapses: `v0.1.0` (L1, shipped) → `v1.0.0` (L3, first stable). No throwaway `v0.2.0`.
  - Users get a stronger first PyPI release (full paint → render → critique loop) instead of an interim "L1 + flaky reload" build.

- **Negative:**
  - Users currently editing with `porymap-mcp` alongside Porymap will continue to need to manually trigger "Reload Project" in Porymap to see edits. This was already the L1 status quo; we are formalizing that this will not change before L3.
  - Loss of the "watch the agent build live in Porymap" demo. L3 replaces this with "see the agent's render inline in the conversation", which is different but, per the project directive, more valuable.

- **Neutral:**
  - `phase-3-l2-live-porymap.md` remains in the repo (status: Abandoned). Its investigation findings are useful future reference if the upstream landscape changes.
  - `phase-4-l3-vision.md` becomes the active phase doc; `STATUS.md` is updated accordingly. Version numbering note added: `v0.2.0` is intentionally skipped.

---

## References

- Phase 3 doc (now Abandoned): [`../phases/phase-3-l2-live-porymap.md`](../phases/phase-3-l2-live-porymap.md)
- Phase 4 doc (now Active): [`../phases/phase-4-l3-vision.md`](../phases/phase-4-l3-vision.md)
- Porymap source (audited): https://github.com/huderlem/porymap — `src/project/project.cpp` (file watcher set), `src/scriptapi/scripting.cpp` (engine setup), `src/scriptapi/apioverlay.cpp` (`addImage` returns void), `include/scriptutility.h` and `include/ui/mapview.h` (full `Q_INVOKABLE` enumeration).
- Porymap scripting capabilities: https://huderlem.github.io/porymap/manual/scripting-capabilities.html
- Porymap CHANGELOG 6.0.0 entry on `map.json` watcher exclusion: https://github.com/huderlem/porymap/blob/master/CHANGELOG.md
- Strategic vision: [`../../MCP_PORYMAP.md`](../../MCP_PORYMAP.md), [`../../CLAUDE.md`](../../CLAUDE.md) §3 "Quality loop"
