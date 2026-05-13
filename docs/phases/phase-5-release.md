# Phase 5 — Release & community launch

> **Status:** Not started (blocked on Phase 4 ship)
> **Estimated effort:** 2–3 days
> **Closes when:** `pip install porymap-mcp` works for the public, the project is announced in both the MCP and the ROM hack communities, and at least one external user has shipped a map with it.

---

## 1. Goal

Take `porymap-mcp` from "works on Hugo's laptop" to "any ROM hacker can install it and ship a map in 30 minutes". This phase is mostly about **discoverability, polish, and community trust**.

---

## 2. Exit criteria

- [ ] `pip install porymap-mcp` works from PyPI on Linux, macOS, Windows
- [ ] `uvx porymap-mcp` works (zero-install via uv)
- [ ] README pass-the-5-minute-test (see `docs-curator` agent's rubric)
- [ ] All 5 example folders in `examples/` are runnable end-to-end on a clean machine
- [ ] CHANGELOG complete from `0.1.0` to `1.0.0`
- [ ] LICENSE (MIT) at repo root
- [ ] CONTRIBUTING.md complete
- [ ] GitHub Release with notes for `v1.0.0`
- [ ] PyPI page renders correctly (description, badges, link to docs)
- [ ] MCP marketplace submission (if/when there's a registry — verify state at release time)
- [ ] **Announced in ≥ 3 places**: rh-hideout Discord, PokéCommunity (tools forum), Twitter/X, LinkedIn — *check each community's AI-content rules first* (see `rom-hack-domain` agent)
- [ ] **First external user**: someone other than Hugo opens an issue or PRs an example map

---

## 3. Pre-release polish

### Packaging
- [ ] `pyproject.toml` complete: name, version, description, authors, license, classifiers, dependencies, optional `[render]` extra for Pillow
- [ ] Wheel + sdist build cleanly
- [ ] `python -m porymap_mcp` is the documented entry point (also: `porymap-mcp` console script)

### Docs
- [ ] README at the level of `docs-curator`'s rubric
- [ ] `docs/guides/`: "Authoring your first map", "Setting up L2", "Custom prefabs", "Troubleshooting"
- [ ] `docs/reference/`: full tool reference (auto-generated from FastMCP signatures + docstrings)
- [ ] All 5 `examples/` folders complete with screenshots
- [ ] `CONTRIBUTING.md` covers: dev setup, running tests, the agent system in `.claude/agents/` (community contributors can use them too)

### Community readiness
- [ ] Issue templates: bug report, feature request, "my map broke"
- [ ] PR template referencing CHANGELOG conventions
- [ ] Code of conduct (Contributor Covenant standard)
- [ ] Tag `good first issue` on 3–5 small tasks
- [ ] Security policy (private vuln reporting via GitHub)

---

## 4. Release checklist

When cutting `v1.0.0`:

- [ ] All tests green on CI matrix
- [ ] Visual regression tests all pass on the 5-map corpus
- [ ] CHANGELOG `[Unreleased]` section becomes `[1.0.0] — YYYY-MM-DD`
- [ ] `__version__` bumped in `src/porymap_mcp/__init__.py`
- [ ] Commit: `chore: release v1.0.0`, tag `v1.0.0`
- [ ] Push tag → triggers PyPI publish workflow
- [ ] GitHub Release notes published
- [ ] Announcement posts drafted, reviewed for tone (no "🚀"), sent
- [ ] Smoke test from a clean VM: `pipx install porymap-mcp`, run first example

---

## 5. Communication plan

Drafts of each post live in `docs/announcements/` (gitignored from public docs/, source of truth for the messages).

| Channel | Audience | Tone | Length |
|---------|----------|------|--------|
| rh-hideout Discord | Active ROM hackers | Casual, technical | 3-paragraph + screenshot |
| PokéCommunity forum | Broader ROM hack | Formal, link-rich | One thread post + 1 follow-up |
| Anthropic MCP Discord | MCP devs | Technical | 2-paragraph + GIF |
| Twitter/X | Mixed | Concise, visual | Thread of 4 tweets + 1 demo video |
| LinkedIn | Professional / portfolio | Project retrospective | 1 long post with lessons |

**Critical for ROM hack channels:** lead with the *user value* (faster mapping, no manual file editing), not "we built an AI tool". The communities are sensitive about AI hype. The agent stays in the background of the message.

---

## 6. Post-release maintenance commitments

What we commit to publicly:

- Critical bugs (data loss, file corruption): patch within 1 week
- Compatibility breaks from new pokeemerald-expansion releases: patch within 1 month
- Feature requests: triaged but not promised; community PRs welcome
- Long-term: stay alive for at least 6 months of active response, then re-evaluate

Document this in `MAINTENANCE.md`.

---

## 7. Open questions

- **OQ1**: Versioning of bundled prefabs? Likely tied to the package version, but document.
- **OQ2**: How to handle pokeemerald-expansion version drift? Pin which expansion versions are tested.
- **OQ3**: Should we offer a hosted demo (web-based MCP client + sample project)? Probably not for v1.0 — too much infra.

---

## 8. Session log

*(empty — phase not started)*

---

## 9. References

- Phase 4: [`phase-4-l3-vision.md`](phase-4-l3-vision.md)
- Docs agent: [`../../.claude/agents/docs-curator.md`](../../.claude/agents/docs-curator.md)
- Domain agent (community norms): [`../../.claude/agents/rom-hack-domain.md`](../../.claude/agents/rom-hack-domain.md)
