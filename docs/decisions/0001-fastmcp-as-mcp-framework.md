# ADR-0001: Use FastMCP as the MCP framework

- **Status:** Accepted
- **Date:** 2026-05-13
- **Deciders:** Hugo Martins

---

## Context

The project ships an MCP server in Python. The Model Context Protocol (MCP) is implemented by several Python libraries:

- The official `mcp` SDK from Anthropic — low-level, exposes the protocol primitives.
- **FastMCP** — decorator-based, modeled on FastAPI, the de-facto "high-level" choice in the Python MCP ecosystem in 2026.
- Hand-rolled implementations on top of the JSON-RPC wire format.

The strategic doc (`MCP_PORYMAP.md` §5) already names FastMCP, but only as an implementation note — no explicit weighing of alternatives. We are recording the decision here because it's load-bearing: changing the framework after we ship would invalidate every tool's signature.

---

## Decision

We use **FastMCP** as the framework for the `porymap-mcp` server.

All tools are defined with `@mcp.tool()` decorators. Type annotations on tool parameters generate the JSON schema MCP clients see. Tool docstrings become the LLM-facing tool descriptions.

---

## Alternatives considered

### Alternative 1 — Official `mcp` SDK (low-level)

The official Anthropic-maintained Python SDK.

- **Upside:** authoritative, will track protocol updates fastest, no third-party dependency
- **Downside:** verbose. Each tool requires manual schema construction, manual dispatch wiring, manual error formatting. ~3× the boilerplate per tool.
- **Why not:** we have 25+ tools planned across L1/L2/L3. Boilerplate compounds.

### Alternative 2 — Hand-rolled JSON-RPC

Implement MCP directly on top of `asyncio` + JSON-RPC.

- **Upside:** zero dependencies, full control
- **Downside:** reinventing the wheel, no benefit
- **Why not:** no upside vs. FastMCP and significant downside in maintenance.

### Alternative 3 — `fastmcp` v1 vs `fastmcp` v2

FastMCP went through a major rewrite (v1 → v2). v2 is the maintained line, with breaking changes to tool registration and lifespan.

- **Why we pick v2:** it's the current line; v1 is in maintenance mode.

---

## Consequences

**Positive:**
- Tool signatures are concise: one decorator + Python type hints generates the entire MCP schema.
- Docstrings double as tool descriptions, which is exactly the contract we want with LLM clients.
- FastMCP handles `Image` content blocks natively — critical for the L3 rendering loop.
- Active community + frequent releases.

**Negative:**
- Adds a non-stdlib runtime dependency. Mitigated: it's a small, focused library.
- Tied to FastMCP's API evolution. If they make a breaking change in v3, we'll feel it. Mitigated: pin a major version range in `pyproject.toml`.
- The framework's lifespan abstraction is opinionated. If we need a startup hook FastMCP doesn't support, we're slightly stuck.

**Neutral:**
- Tool descriptions live in docstrings, which means our doc style for tool functions is constrained (LLM-facing prose). Documented in `CLAUDE.md` §5 and the `mcp-tool-designer` agent.

---

## References

- FastMCP: https://github.com/jlowin/fastmcp
- FastMCP docs: https://gofastmcp.com
- Official MCP SDK: https://github.com/modelcontextprotocol/python-sdk
- MCP spec: https://modelcontextprotocol.io
- Related: `MCP_PORYMAP.md` §5, `CLAUDE.md` §2, `.claude/agents/mcp-tool-designer.md`
- Phase doc affected: `docs/phases/phase-2-l1-filesystem.md` (entire implementation)
