import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def settings(tmp_path, monkeypatch):
    from config import load_settings
    monkeypatch.setenv("CAFE_URL", "https://cafe.naver.com/testcafe")
    s = load_settings(env_file=tmp_path / "none.env")
    return replace(s, cafe_url="https://cafe.naver.com/testcafe", db_path=tmp_path / "t.db",
                   profile_dir=tmp_path / "profile", log_dir=tmp_path / "logs",
                   export_dir=tmp_path / "exports", media_dir=tmp_path / "media",
                   max_retries=2, retry_backoff_seconds=1.0, delay_min=1.0, delay_max=1.0,
                   media_download_policy_confirmed=False)


@pytest.fixture
def repo(tmp_path):
    from database.repository import Repository
    return Repository(tmp_path / "test.db")
