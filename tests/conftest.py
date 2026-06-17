"""Test fixtures — her test geçici, izole bir SQLite DB kullanır."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Testler arası temiz DB; offline mod garanti."""
    import config

    db = tmp_path / "test.db"
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "OFFLINE_MODE", True)
    monkeypatch.setattr(config, "USE_REAL_KB", False)

    import datasource

    # seed durumunu sıfırla ki yeni DB tohumlansın.
    datasource._seed_checked = False
    importlib.reload  # no-op; netlik için
    yield
    datasource._seed_checked = False
