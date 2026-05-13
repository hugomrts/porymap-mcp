"""The :class:`Project` class — single entrypoint for all L1 MCP tools.

See ADR-0003 for the design rationale. In one paragraph:

* Every MCP tool that touches a project takes ``project_path: Path`` and
  constructs a :class:`Project` per call. The server keeps no cached state.
* ``Project.load(path)`` is the only constructor. It reads
  ``porymap.project.cfg`` and validates the project's ``base_game_version``
  against :data:`SUPPORTED_BASE_GAME_VERSIONS` (currently only
  :attr:`BaseGameVersion.POKEEMERALD` in v0.1.0).
* Format parameters (metatile-id mask, collision mask, etc.) flow through
  ``project.config`` to parsers as explicit arguments — parsers never branch
  on ``base_game_version`` themselves.

Future fields (``layouts``, ``map_groups``, …) will be added as lazy
properties on this class as the corresponding parsers land.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from porymap_mcp.errors import ProjectError, UnsupportedBaseGameError
from porymap_mcp.parsers import projectconfig
from porymap_mcp.parsers.projectconfig import BaseGameVersion, ProjectConfig

#: Filename Porymap uses for the per-project config, sitting at the project root.
PROJECT_CONFIG_FILENAME: Final = "porymap.project.cfg"

#: Base-game versions this release implements end-to-end. The gate that enforces
#: the policy lives in :meth:`Project.load`; the parser layer is free to *parse*
#: any version Porymap recognizes, but ``Project`` refuses to construct an
#: instance for one we cannot serve correctly. See ADR-0003 §5.
SUPPORTED_BASE_GAME_VERSIONS: Final[frozenset[BaseGameVersion]] = frozenset(
    {BaseGameVersion.POKEEMERALD}
)


@dataclass(frozen=True, slots=True)
class Project:
    """A frozen, validated view of a pokeemerald-family project on disk.

    ``Project`` is constructed exclusively via :meth:`load`. It is intentionally
    minimal in v0.1.0 — it carries the project root and the resolved
    :class:`~porymap_mcp.parsers.projectconfig.ProjectConfig`. As subsequent
    parsers land, additional lazy properties (``layouts``, ``map_groups``,
    ``tilesets``) will be added without changing this constructor.
    """

    root: Path
    config: ProjectConfig

    @classmethod
    def load(cls, root: Path) -> Project:
        """Load and validate a project rooted at ``root``.

        Raises:
            ProjectError: ``root`` is not a directory, or the cfg file is
                missing/unreadable.
            FormatError: the cfg file is malformed.
            UnsupportedBaseGameError: the project declares a
                ``base_game_version`` outside :data:`SUPPORTED_BASE_GAME_VERSIONS`.
        """
        if not root.is_dir():
            raise ProjectError(f"project root is not a directory: {root}")

        config_path = root / PROJECT_CONFIG_FILENAME
        config = projectconfig.read(config_path)

        if config.base_game_version not in SUPPORTED_BASE_GAME_VERSIONS:
            raise UnsupportedBaseGameError(
                declared=config.base_game_version.value,
                supported=tuple(v.value for v in SUPPORTED_BASE_GAME_VERSIONS),
            )

        return cls(root=root, config=config)
