# Phase 5 — Release & community launch

> **Status:** In progress (opened 2026-10-31). `v1.0.0` is on `main`; tag, GitHub Release and first PyPI upload are owner actions.
> **Estimated effort:** 2–3 days
> **Closes when:** `pip install porymap-mcp` works for the public, the project is announced in both the MCP and the ROM hack communities, and at least one external user has shipped a map with it.

---

## 1. Goal

Take `porymap-mcp` from "works on Hugo's laptop" to "any ROM hacker can install it and ship a map in 30 minutes". This phase is mostly about **discoverability, polish, and community trust**.

---

## 2. Exit criteria

- [ ] `pip install porymap-mcp` works from PyPI on Linux, macOS, Windows — `publish.yml` ready, waiting on the PyPI trusted publisher + `v1.0.0` tag
- [ ] `uvx porymap-mcp` works (zero-install via uv)
- [ ] README pass-the-5-minute-test (see `docs-curator` agent's rubric)
- [ ] All 5 example folders in `examples/` are runnable end-to-end on a clean machine
- [x] CHANGELOG complete from `0.1.0` to `1.0.0`
- [x] LICENSE (MIT) at repo root
- [ ] CONTRIBUTING.md complete
- [ ] GitHub Release with notes for `v1.0.0` — commands prepared (see §8, 2026-10-31)
- [ ] PyPI page renders correctly (description, badges, link to docs)
- [ ] MCP marketplace submission (if/when there's a registry — verify state at release time)
- [ ] **Announced in ≥ 3 places**: rh-hideout Discord, PokéCommunity (tools forum), Twitter/X, LinkedIn — *check each community's AI-content rules first* (see `rom-hack-domain` agent)
- [ ] **First external user**: someone other than Hugo opens an issue or PRs an example map

---

## 3. Pre-release polish

### Packaging
- [x] `pyproject.toml` complete: name, version, description, authors, license, classifiers, dependencies, optional `[render]` extra for Pillow
- [x] Wheel + sdist build cleanly (`uv build` + `twine check --strict` pass on 1.0.0)
- [x] `python -m porymap_mcp` is the documented entry point (also: `porymap-mcp` console script)

### Docs
- [ ] README at the level of `docs-curator`'s rubric — rewritten for v1.0.0 (PR #15, absolute URLs in #17), not yet scored by `docs-curator`
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

- [x] All tests green on CI matrix (ruff, ruff format, mypy now blocking)
- [x] Visual regression tests all pass on the 5-map corpus
- [x] CHANGELOG `[Unreleased]` section becomes `[1.0.0] — 2026-10-31`
- [x] `__version__` bumped in `src/porymap_mcp/__init__.py` (and `pyproject.toml`)
- [x] Commit: `chore: release v1.0.0` (PR #16)
- [ ] Configure the PyPI pending trusted publisher (`hugomrts/porymap-mcp`, workflow `publish.yml`, environment `pypi`) — owner, on pypi.org
- [ ] Optional: create the `pypi` environment on GitHub with a required reviewer — owner
- [ ] Tag `v1.0.0` on `main` (after the publish workflow is merged) — owner
- [ ] Push tag → triggers PyPI publish workflow (`.github/workflows/publish.yml`)
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

### 2026-10-31 — v1.0.0 release slice

Opened the phase. One PR per step, all squash-merged by the owner:

- **PR #14 `ci: make ruff check, ruff format and mypy blocking`.** CI had been
  green while `ruff format --check` and `mypy` failed behind
  `continue-on-error`. Fixed 4 mypy errors in `tests/unit/tools/`, excluded
  `*.md` from ruff (ruff 0.17 formats code fences in ADRs), pinned
  `ruff>=0.17,<0.18` and `mypy>=2.4,<3` in the `dev` extra, aligned the
  pre-commit revs.
- **PR #15 `docs(readme): rewrite for the v1.0.0 release`.** Pitch, iter1/iter2
  renders up top, pip/uvx install, MCP registration, first map in 5 minutes,
  24-tool table, ADR index, pointer to `MCP_PORYMAP.md`. The
  `gTileset_LittlerootTown` placeholder exists in neither vanilla
  `pokeemerald` nor the expansion (checked pret's `headers.h`): Littleroot uses
  `gTileset_General` + `gTileset_Petalburg` in both. README now uses that.
- **PR #16 `chore: release v1.0.0`.** CHANGELOG `[1.0.0] — 2026-10-31` with the
  four renderer fixes, version `1.0.0`, classifier Production/Stable.
- **PR #17 `ci: publish to PyPI via trusted publishing on v* tags`.**
  `publish.yml` (tag/version check, build, `twine check --strict`, OIDC upload
  from the `pypi` environment) + absolute README URLs so PyPI renders images
  and links.

This lifts the earlier "PyPI deferred" directive: the owner asked for the
publish workflow; the first upload happens when they push the tag.

**Remaining (owner):** PyPI pending publisher, tag `v1.0.0`, GitHub Release
(notes = CHANGELOG `[1.0.0]` section), then smoke-test
`uvx --from "porymap-mcp[render]" porymap-mcp`. **Remaining (next sessions):**
`docs-curator` pass on the README, CONTRIBUTING.md, issue/PR templates,
examples 01–03 and 05, announcements.

---

## 9. References

- Phase 4: [`phase-4-l3-vision.md`](phase-4-l3-vision.md)
- Docs agent: [`../../.claude/agents/docs-curator.md`](../../.claude/agents/docs-curator.md)
- Domain agent (community norms): [`../../.claude/agents/rom-hack-domain.md`](../../.claude/agents/rom-hack-domain.md)
