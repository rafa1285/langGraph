"""Global pytest configuration and isolation fixtures for AgentOffice."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def isolate_test_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Hermetically isolate all tests from production/dev SQLite and workspaces."""
    test_db = tmp_path / "office_data_isolated.sqlite"
    test_checkpoints = tmp_path / "checkpoints_isolated.sqlite"
    test_workspaces = tmp_path / "workspaces_isolated"
    test_workspaces.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "OFFICE_DB_PATH", str(test_db))
    monkeypatch.setattr(settings, "CHECKPOINT_DB_PATH", str(test_checkpoints))
    monkeypatch.setattr(settings, "WORKSPACES_DIR", str(test_workspaces))
    monkeypatch.setattr(settings, "USE_MOCK_LLM", True)

    yield
