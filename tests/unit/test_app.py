"""Tests for app entry point."""

from pathlib import Path


class TestAppConfig:
    def test_get_default_db_path(self):
        from hcp_cms.app import get_default_db_path

        path = get_default_db_path()
        assert isinstance(path, Path)
        assert path.name == "cs_tracker.db"
        assert "HCP_CMS" in str(path)
