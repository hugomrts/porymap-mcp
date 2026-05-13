"""Entry point: ``python -m porymap_mcp`` launches the FastMCP server."""

from __future__ import annotations


def main() -> None:
    """Boot the FastMCP server on stdio transport."""
    # Import lazily so ``--help``-style introspection (added later) does not
    # pull in FastMCP and its transitive deps just to print a help string.
    from porymap_mcp.server import build_server

    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
