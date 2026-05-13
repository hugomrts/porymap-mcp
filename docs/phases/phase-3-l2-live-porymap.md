# Phase 3 — L2: Live Porymap

> **Status:** Not started (blocked on Phase 2 ship)
> **Estimated effort:** 2–3 days
> **Closes when:** Porymap, open in parallel, reloads automatically as the agent edits, with no human action.

---

## 1. Goal

When the user has Porymap open and the agent is editing the project, the changes should appear in Porymap **in real time**. This turns the workflow from "agent works, user reloads, user looks" into "user watches the agent build the map live".

Crucially, L2 does **not** change any tool signature from L1 — it adds behavior on top. An L1 client using v0.2.0 server should keep working.

---

## 2. Exit criteria

- [ ] Porymap reloads within ~500 ms of an L1 mutation completing
- [ ] No spurious reloads (the bridge debounces; doesn't trigger on read-only tool calls)
- [ ] Bridge gracefully degrades when Porymap isn't running (no errors, just no reload)
- [ ] `is_porymap_connected()` discovery tool reflects reality
- [ ] `notify_porymap_reload()` works for manual force-reload
- [ ] All L1 integration tests still pass
- [ ] New integration test: spin up Porymap headlessly, edit, screenshot, assert reload happened
- [ ] Tagged `v0.2.0`

---

## 3. Technical approach (to be validated)

Two candidate mechanisms, ordered by preference:

### Approach A — Porymap JS API + file watcher (preferred)

Porymap has a built-in JavaScript scripting API. The plan:
1. Ship a `porymap_mcp_bridge.js` script in the package.
2. User loads it once into Porymap (one-time setup: Tools → Scripts → Load script).
3. The script watches a small "trigger file" in the project (e.g. `.porymap-mcp/reload-signal`).
4. On change, the script triggers Porymap's `map.reload()` (or equivalent — verify exact API).
5. The MCP server, after every write, touches the trigger file with the changed map name.

**Pros:** clean, no Qt automation, survives Porymap version updates if the JS API is stable.
**Cons:** requires a one-time user setup. The Porymap JS API is undocumented for some operations.

### Approach B — File watcher inside Porymap (native)

Porymap may already have native file-watching that re-reads `map.bin` if it changes externally. If so, we just need to write the files and Porymap notices.

**Investigation needed in Phase 1 POC.** If native watching works for all the files we touch (`map.bin`, `border.bin`, `map.json`, `layouts.json`, `map_groups.json`), no bridge is needed.

**Pros:** zero setup. Best UX possible.
**Cons:** unverified. Native watching may not exist or only cover some files.

### Approach C (fallback) — Qt automation

Drive Porymap via Qt accessibility (PyAutoGUI, xdotool, PyQt's QTestLib). Send a Ctrl+R or similar.

**Pros:** works everywhere.
**Cons:** brittle, platform-specific, terrible UX.

---

## 4. Investigation tasks (do these first)

- [ ] **Try Approach B**: open Porymap, edit `map.bin` externally with `xxd`, watch if Porymap notices
- [ ] If A is needed: read Porymap source (`src/scriptapi/`) to enumerate available JS calls
- [ ] Confirm the bridge script can survive Porymap restarts (probably needs auto-load)
- [ ] Decide: should bridge be optional (L2 = "best-effort") or required (L2 = "you must install the bridge")?

---

## 5. Tool surface changes

### New tools

| Tool | Signature | Notes |
|------|-----------|-------|
| `is_porymap_connected` | `(project_path: Path)` | Returns `True` if the bridge is alive (heartbeat file recent). |
| `notify_porymap_reload` | `(project_path, map_name=None)` | Force a reload signal. Useful after manual file edits. |

### Implicit changes

All L1 mutation tools start emitting the reload signal at the end of their successful path. No signature change. Document in each tool's description.

---

## 6. Synthetic fixture changes

The fixture project gains a `.porymap-mcp/` directory with the bridge's trigger file format documented. The bridge script itself is tested standalone (JS test runner) and via a manual integration test (this isn't automatable cheaply in CI).

---

## 7. Open questions

- **OQ1**: Does the bridge run *one per project* (watcher scoped to a project path) or *one global* (watches everything)? Per-project keeps state simple; global is one-time setup.
- **OQ2**: What's the failure mode if Porymap is open on a *different* project than the agent is editing? Probably just no-op (different trigger file), but document.
- **OQ3**: Should we ship a Porymap *plugin* (heavier setup, better UX) instead of a JS script (lighter, but requires manual load)?

---

## 8. Session log

*(empty — phase not started)*

---

## 9. References

- Phase 2: [`phase-2-l1-filesystem.md`](phase-2-l1-filesystem.md)
- Phase 4 (next): [`phase-4-l3-vision.md`](phase-4-l3-vision.md)
- Porymap scripting API: https://huderlem.github.io/porymap/manual/scripting-api.html
