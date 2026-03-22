"""Shared pytest fixtures for HCP CMS tests."""

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Provide a temporary database file path."""
    return tmp_path / "test_cs_tracker.db"
