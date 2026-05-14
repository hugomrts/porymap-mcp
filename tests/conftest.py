"""Shared pytest configuration."""

from __future__ import annotations

from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register CLI flags consumed by integration tests.

    ``--update-golden`` rewrites golden artefacts (currently
    ``tests/fixtures/renders/case_*/reference.png`` for the regression
    case 5) instead of asserting against them. Off by default.
    Maintainer-only — never enable in CI.
    """
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Rewrite golden render fixtures instead of asserting them. Maintainer-only.",
    )


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Absolute path to the ``tests/fixtures`` directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def update_golden(pytestconfig: pytest.Config) -> bool:
    """Whether ``--update-golden`` was passed on the pytest command line."""
    return bool(pytestconfig.getoption("--update-golden"))
