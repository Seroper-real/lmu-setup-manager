import os
from datetime import datetime, timedelta

import pytest


@pytest.fixture
def prune():
    from main import _prune_old_logs
    return _prune_old_logs


def _make_log(dir_, name: str, age_days: int) -> None:
    path = dir_ / name
    path.write_text("log line\n")
    mtime = (datetime.now() - timedelta(days=age_days)).timestamp()
    os.utime(path, (mtime, mtime))


def test_deletes_files_older_than_max_age(tmp_path, prune):
    _make_log(tmp_path, "app-old.log", age_days=10)
    _make_log(tmp_path, "app-recent.log", age_days=2)

    prune(tmp_path, max_age_days=7)

    remaining = {p.name for p in tmp_path.glob("*.log")}
    assert remaining == {"app-recent.log"}


def test_keeps_file_exactly_at_the_boundary(tmp_path, prune):
    now = datetime.now()
    _make_log(tmp_path, "app-boundary.log", age_days=6)

    prune(tmp_path, max_age_days=7, now=now)

    assert (tmp_path / "app-boundary.log").exists()


def test_ignores_non_matching_files(tmp_path, prune):
    other = tmp_path / "settings.db"
    other.write_text("not a log")
    mtime = (datetime.now() - timedelta(days=30)).timestamp()
    os.utime(other, (mtime, mtime))

    prune(tmp_path, max_age_days=7)

    assert other.exists()


def test_empty_directory_does_not_raise(tmp_path, prune):
    prune(tmp_path, max_age_days=7)
