"""L1 event-mutation tools (ADR-0007).

Implements:

  - ``add_warp``
  - ``add_object_event``
  - ``add_sign``  (also generates a poryscript / .inc stub)
  - ``add_trigger``
  - ``remove_event``

Events are stored as ``tuple[dict[str, object], ...]`` on
:class:`MapJson` (see ``parsers/mapjson.py``); typed event dataclasses
are deferred to v0.2.0 per ADR-0007 §"Decision". The tools build dicts
matching pokeemerald's canonical per-event schema and append/remove
from the appropriate array.

``_event_id`` synthesized in ``list_events`` (ADR-0005 §7) has the form
``"<class>:<index>"`` — :func:`remove_event` accepts that verbatim.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from porymap_mcp._atomic import write_atomic_text
from porymap_mcp.errors import CoordinatesOutOfBoundsError, ProjectError
from porymap_mcp.parsers import mapjson
from porymap_mcp.parsers.mapjson import MapJson
from porymap_mcp.project import Project
from porymap_mcp.tools._common import load_project as _load_project
from porymap_mcp.tools._common import maybe_attach_render as _maybe_attach_render
from porymap_mcp.tools._common import posix_str as _posix_str
from porymap_mcp.tools._common import summarize_files as _summarize_files

if TYPE_CHECKING:
    from fastmcp import FastMCP


_EVENT_CLASSES = ("object_events", "warp_events", "coord_events", "bg_events")


# --- Shared helpers -------------------------------------------------------


def _check_coords(x: int, y: int, width: int, height: int) -> None:
    if not (0 <= x < width and 0 <= y < height):
        raise CoordinatesOutOfBoundsError(x, y, width, height)


def _resolve_for_mutation(
    project_path: str, map_name: str
) -> tuple[Project, str, MapJson, int, int]:
    """Common preamble: load project, resolve map, fetch dimensions.

    Returns ``(project, bare_name, map_json, width, height)``.
    """
    project = _load_project(project_path)
    bare, _group, doc = project.get_map_entry(map_name)
    layout_entry = project.get_layout(doc.layout)
    return project, bare, doc, layout_entry.width, layout_entry.height


def _append_event(doc: MapJson, class_name: str, event: dict[str, object]) -> int:
    """Append ``event`` to ``doc.<class_name>`` and return its index."""
    existing = getattr(doc, class_name) or ()
    new_arr = (*existing, event)
    setattr(doc, class_name, new_arr)
    return len(new_arr) - 1


def _save_map_json(project: Project, bare: str, doc: MapJson) -> Path:
    """Atomically write ``doc`` back to ``data/maps/<bare>/map.json``."""
    target = project.maps_dir / bare / "map.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    write_atomic_text(target, mapjson.write(doc))
    return target


# --- 1. add_warp ----------------------------------------------------------


def add_warp(
    project_path: str,
    map_name: str,
    x: int,
    y: int,
    dest_map: str,
    dest_warp_id: int,
    elevation: int = 0,
    return_render: bool = False,
) -> Any:
    """See ADR-0007 §1."""
    project, bare, doc, width, height = _resolve_for_mutation(project_path, map_name)
    _check_coords(x, y, width, height)
    event: dict[str, object] = {
        "x": x,
        "y": y,
        "elevation": elevation,
        "dest_map": dest_map,
        "dest_warp_id": str(dest_warp_id),
    }
    idx = _append_event(doc, "warp_events", event)
    target = _save_map_json(project, bare, doc)
    event_id = f"warp_events:{idx}"
    response: dict[str, Any] = {
        "summary": (f"Added {event_id} at ({x}, {y}) on {map_name} -> {dest_map}:{dest_warp_id}."),
        "project_path": _posix_str(project.root),
        "map_name": map_name,
        "event_id": event_id,
        "x": x,
        "y": y,
        "dest_map": dest_map,
        "dest_warp_id": str(dest_warp_id),
        "files_modified": _summarize_files([target], project.root),
    }
    return _maybe_attach_render(
        response, project_path=project_path, map_name=map_name, return_render=return_render
    )


# --- 2. add_object_event --------------------------------------------------


def add_object_event(
    project_path: str,
    map_name: str,
    x: int,
    y: int,
    graphics_id: str,
    movement_type: str = "MOVEMENT_TYPE_NONE",
    script: str = "",
    flag: str = "0",
    elevation: int = 3,
    movement_range_x: int = 0,
    movement_range_y: int = 0,
    trainer_type: str = "TRAINER_TYPE_NONE",
    trainer_sight_or_berry_tree_id: str = "0",
    return_render: bool = False,
) -> Any:
    """See ADR-0007 §2."""
    project, bare, doc, width, height = _resolve_for_mutation(project_path, map_name)
    _check_coords(x, y, width, height)
    event: dict[str, object] = {
        "graphics_id": graphics_id,
        "x": x,
        "y": y,
        "elevation": elevation,
        "movement_type": movement_type,
        "movement_range_x": movement_range_x,
        "movement_range_y": movement_range_y,
        "trainer_type": trainer_type,
        "trainer_sight_or_berry_tree_id": trainer_sight_or_berry_tree_id,
        "script": script if script else "0",
        "flag": flag,
    }
    idx = _append_event(doc, "object_events", event)
    target = _save_map_json(project, bare, doc)
    event_id = f"object_events:{idx}"
    response: dict[str, Any] = {
        "summary": (f"Added {event_id} ({graphics_id}) at ({x}, {y}) on {map_name}."),
        "project_path": _posix_str(project.root),
        "map_name": map_name,
        "event_id": event_id,
        "x": x,
        "y": y,
        "graphics_id": graphics_id,
        "files_modified": _summarize_files([target], project.root),
    }
    return _maybe_attach_render(
        response, project_path=project_path, map_name=map_name, return_render=return_render
    )


# --- 3. add_sign ----------------------------------------------------------


def add_sign(
    project_path: str,
    map_name: str,
    x: int,
    y: int,
    text: str,
    player_facing_dir: str = "BG_EVENT_PLAYER_FACING_ANY",
    elevation: int = 0,
    return_render: bool = False,
) -> Any:
    """See ADR-0007 §3."""
    project, bare, doc, width, height = _resolve_for_mutation(project_path, map_name)
    _check_coords(x, y, width, height)

    # Determine the next free sign index for this map's bg_events array.
    sign_indices: list[int] = []
    for bg in doc.bg_events or ():
        script_value = bg.get("script")
        if isinstance(script_value, str) and script_value.startswith(f"{bare}_EventScript_Sign_"):
            tail = script_value[len(f"{bare}_EventScript_Sign_") :]
            if tail.isdigit():
                sign_indices.append(int(tail))
    next_n = (max(sign_indices) + 1) if sign_indices else 0
    script_symbol = f"{bare}_EventScript_Sign_{next_n}"

    # Choose script file + content based on use_poryscript.
    use_pory = _project_uses_poryscript(project)
    script_filename = "scripts.pory" if use_pory else "scripts.inc"
    script_path = project.maps_dir / bare / script_filename

    if script_path.is_file():
        existing_text = script_path.read_text(encoding="utf-8")
        if _script_symbol_exists(existing_text, script_symbol, use_pory):
            raise ProjectError(
                f"add_sign: script symbol {script_symbol!r} already exists in "
                f"{script_path.relative_to(project.root).as_posix()}. "
                "Pick a different sign placement or remove the existing stub first."
            )
    else:
        existing_text = ""

    stub = _build_sign_stub(script_symbol, text, bare, next_n, use_pory)
    new_script_text = _append_script_stub(existing_text, stub)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic_text(script_path, new_script_text)

    event: dict[str, object] = {
        "type": "sign",
        "x": x,
        "y": y,
        "elevation": elevation,
        "player_facing_dir": player_facing_dir,
        "script": script_symbol,
    }
    idx = _append_event(doc, "bg_events", event)
    target = _save_map_json(project, bare, doc)
    event_id = f"bg_events:{idx}"
    response: dict[str, Any] = {
        "summary": (
            f"Added {event_id} (sign) at ({x}, {y}) on {map_name} with script {script_symbol}."
        ),
        "project_path": _posix_str(project.root),
        "map_name": map_name,
        "event_id": event_id,
        "x": x,
        "y": y,
        "script_symbol": script_symbol,
        "script_file": script_path.relative_to(project.root).as_posix(),
        "files_modified": _summarize_files([target, script_path], project.root),
    }
    return _maybe_attach_render(
        response, project_path=project_path, map_name=map_name, return_render=return_render
    )


def _project_uses_poryscript(project: Project) -> bool:
    """Return ``True`` when the project declares ``use_poryscript=1``.

    Defaults to ``True`` when the project config is unreadable —
    poryscript is the modern decomp default. (A config-missing project
    is unusual; we don't fail the whole tool on it.)
    """
    try:
        return project.config.use_poryscript
    except ProjectError:
        return True


def _build_sign_stub(symbol: str, text: str, bare: str, n: int, use_pory: bool) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    if use_pory:
        return f'\nscript {symbol} {{\n    msgbox("{escaped}", MSGBOX_SIGN)\n}}\n'
    text_symbol = f"{bare}_EventText_Sign_{n}"
    return (
        f"\n{symbol}::\n"
        f"\tmsgbox {text_symbol}, MSGBOX_SIGN\n"
        f"\tend\n\n"
        f"{text_symbol}:\n"
        f'\t.string "{escaped}$"\n'
    )


def _append_script_stub(existing: str, stub: str) -> str:
    if not existing:
        return stub.lstrip("\n")
    if existing.endswith("\n"):
        return existing + stub
    return existing + "\n" + stub


def _script_symbol_exists(text: str, symbol: str, use_pory: bool) -> bool:
    if use_pory:
        return f"script {symbol}" in text or f"script {symbol} " in text
    return f"{symbol}::" in text


# --- 4. add_trigger -------------------------------------------------------


def add_trigger(
    project_path: str,
    map_name: str,
    x: int,
    y: int,
    var: str,
    value: int,
    script: str,
    elevation: int = 0,
    return_render: bool = False,
) -> Any:
    """See ADR-0007 §4."""
    project, bare, doc, width, height = _resolve_for_mutation(project_path, map_name)
    _check_coords(x, y, width, height)
    event: dict[str, object] = {
        "type": "trigger",
        "x": x,
        "y": y,
        "elevation": elevation,
        "var": var,
        "var_value": str(value),
        "script": script,
    }
    idx = _append_event(doc, "coord_events", event)
    target = _save_map_json(project, bare, doc)
    event_id = f"coord_events:{idx}"
    response: dict[str, Any] = {
        "summary": (
            f"Added {event_id} (trigger) at ({x}, {y}) on {map_name}: {var}={value} -> {script}."
        ),
        "project_path": _posix_str(project.root),
        "map_name": map_name,
        "event_id": event_id,
        "x": x,
        "y": y,
        "var": var,
        "value": value,
        "script": script,
        "files_modified": _summarize_files([target], project.root),
    }
    return _maybe_attach_render(
        response, project_path=project_path, map_name=map_name, return_render=return_render
    )


# --- 5. remove_event ------------------------------------------------------


def remove_event(
    project_path: str,
    map_name: str,
    event_id: str,
    return_render: bool = False,
) -> Any:
    """See ADR-0007 §5."""
    project, bare, doc, _width, _height = _resolve_for_mutation(project_path, map_name)
    class_name, index = _parse_event_id(event_id)

    existing = getattr(doc, class_name) or ()
    response_base: dict[str, Any] = {
        "project_path": _posix_str(project.root),
        "map_name": map_name,
        "event_id": event_id,
    }
    if index >= len(existing):
        noop_response: dict[str, Any] = {
            **response_base,
            "summary": (f"{event_id} not present on {map_name}; nothing to remove."),
            "removed_event": None,
            "files_modified": [],
        }
        return _maybe_attach_render(
            noop_response,
            project_path=project_path,
            map_name=map_name,
            return_render=return_render,
        )
    removed = dict(existing[index])
    new_arr = (*existing[:index], *existing[index + 1 :])
    setattr(doc, class_name, new_arr)
    target = _save_map_json(project, bare, doc)
    response: dict[str, Any] = {
        **response_base,
        "summary": f"Removed {event_id} from {map_name}.",
        "removed_event": removed,
        "files_modified": _summarize_files([target], project.root),
    }
    return _maybe_attach_render(
        response, project_path=project_path, map_name=map_name, return_render=return_render
    )


def _parse_event_id(event_id: str) -> tuple[str, int]:
    if ":" not in event_id:
        raise ProjectError(
            f"remove_event: event_id {event_id!r} is malformed; "
            "expected '<class>:<index>' (e.g. 'warp_events:1')."
        )
    cls, _, idx_str = event_id.partition(":")
    if cls not in _EVENT_CLASSES:
        raise ProjectError(
            f"remove_event: unknown event class {cls!r}. Valid: {', '.join(_EVENT_CLASSES)}."
        )
    try:
        idx = int(idx_str)
    except ValueError as exc:
        raise ProjectError(f"remove_event: event_id {event_id!r} has non-integer index.") from exc
    if idx < 0:
        raise ProjectError(f"remove_event: event_id {event_id!r} has negative index.")
    return cls, idx


# --- FastMCP registration -------------------------------------------------


def register(mcp: FastMCP) -> None:
    mcp.tool(name="add_warp")(_tool_add_warp)
    mcp.tool(name="add_object_event")(_tool_add_object_event)
    mcp.tool(name="add_sign")(_tool_add_sign)
    mcp.tool(name="add_trigger")(_tool_add_trigger)
    mcp.tool(name="remove_event")(_tool_remove_event)


def _tool_add_warp(
    project_path: str,
    map_name: str,
    x: int,
    y: int,
    dest_map: str,
    dest_warp_id: int,
    elevation: int = 0,
    return_render: bool = False,
) -> Any:
    """Append a warp event to a map.

    A warp teleports the player to dest_map's dest_warp_id (the
    destination warp's index, 0-based, in its own warp_events array).

    Args:
      project_path: project root.
      map_name: MAP_* constant of the SOURCE map (where the warp lives).
      x, y: tile coordinates of the warp.
      dest_map: MAP_* constant of the DESTINATION map.
      dest_warp_id: 0-based index into dest_map's warp_events array.
      elevation: 0..15. Default 0.
      return_render: if True, attach a PNG render of the post-mutation
        map to the response.
    """
    return add_warp(
        project_path,
        map_name,
        x,
        y,
        dest_map,
        dest_warp_id,
        elevation,
        return_render=return_render,
    )


def _tool_add_object_event(
    project_path: str,
    map_name: str,
    x: int,
    y: int,
    graphics_id: str,
    movement_type: str = "MOVEMENT_TYPE_NONE",
    script: str = "",
    flag: str = "0",
    elevation: int = 3,
    movement_range_x: int = 0,
    movement_range_y: int = 0,
    trainer_type: str = "TRAINER_TYPE_NONE",
    trainer_sight_or_berry_tree_id: str = "0",
    return_render: bool = False,
) -> Any:
    """Append an object event (NPC, item ball, static) to a map.

    Does NOT generate a script stub — too varied for boilerplate. The
    caller is responsible for authoring the referenced script symbol
    elsewhere (or leaving script="" for a non-interactive NPC).

    Args:
      project_path: project root.
      map_name: MAP_* constant.
      x, y: tile coordinates.
      graphics_id: OBJ_EVENT_GFX_* constant (e.g. "OBJ_EVENT_GFX_MOM").
      movement_type: MOVEMENT_TYPE_* constant. Default static.
      script: script symbol name (e.g. "LittlerootTown_EventScript_Mom"),
        or "" for none.
      flag: flag controlling visibility (e.g. "FLAG_HIDE_X"), "0" for none.
      elevation: 0..15. Default 3.
    """
    return add_object_event(
        project_path,
        map_name,
        x,
        y,
        graphics_id,
        movement_type,
        script,
        flag,
        elevation,
        movement_range_x,
        movement_range_y,
        trainer_type,
        trainer_sight_or_berry_tree_id,
        return_render=return_render,
    )


def _tool_add_sign(
    project_path: str,
    map_name: str,
    x: int,
    y: int,
    text: str,
    player_facing_dir: str = "BG_EVENT_PLAYER_FACING_ANY",
    elevation: int = 0,
    return_render: bool = False,
) -> Any:
    """Append a sign with inline text. Generates a script stub.

    Writes a poryscript stub by default (use_poryscript=1) or a legacy
    .inc stub. Script symbol: <bare>_EventScript_Sign_<N> where <N> is
    the next free index for this map. The script file is created if
    missing; the stub is appended.

    Args:
      project_path: project root.
      map_name: MAP_* constant.
      x, y: tile coordinates.
      text: the message displayed when the sign is read.
      player_facing_dir: BG_EVENT_PLAYER_FACING_* constant.
      elevation: 0..15. Default 0.
      return_render: if True, attach a PNG render of the post-mutation
        map to the response.
    """
    return add_sign(
        project_path,
        map_name,
        x,
        y,
        text,
        player_facing_dir,
        elevation,
        return_render=return_render,
    )


def _tool_add_trigger(
    project_path: str,
    map_name: str,
    x: int,
    y: int,
    var: str,
    value: int,
    script: str,
    elevation: int = 0,
    return_render: bool = False,
) -> Any:
    """Append a coord-based script trigger.

    Fires the script when the player steps on (x, y) AND var equals
    value. Does NOT generate a script stub; the caller authors the
    referenced symbol elsewhere.

    Args:
      project_path: project root.
      map_name: MAP_* constant.
      x, y: tile coordinates.
      var: VAR_* constant controlling fire condition.
      value: integer compared against var.
      script: script symbol to run.
      elevation: 0..15. Default 0.
      return_render: if True, attach a PNG render of the post-mutation
        map to the response.
    """
    return add_trigger(
        project_path,
        map_name,
        x,
        y,
        var,
        value,
        script,
        elevation,
        return_render=return_render,
    )


def _tool_remove_event(
    project_path: str,
    map_name: str,
    event_id: str,
    return_render: bool = False,
) -> Any:
    """Remove any event by its synthesized _event_id.

    Get the id from list_events. Format: "<class>:<index>" (e.g.
    "warp_events:1"). Ids shift across mutations — call list_events
    again after any add_*/remove_event. Idempotent: removing an
    already-absent id is a no-op success.

    Script files are NOT deleted; if you removed a sign, its stub stays
    in data/maps/<bare>/scripts.pory (or .inc).

    Args:
      project_path: project root.
      map_name: MAP_* constant.
      event_id: e.g. "warp_events:1".
    """
    return remove_event(project_path, map_name, event_id, return_render=return_render)


__all__ = [
    "add_object_event",
    "add_sign",
    "add_trigger",
    "add_warp",
    "register",
    "remove_event",
]
