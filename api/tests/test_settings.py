"""Tests for the upload settings in app/config.py.

Purpose: prove where uploaded files go by default, that a relative DATA_DIR
cannot drift with the folder the server happens to start in, and that a
nonsensical upload limit is refused at startup.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import REPO_ROOT, Settings

URL = "postgresql+psycopg://unused"


def test_data_dir_defaults_to_data_at_the_repo_root():
    assert Settings(database_url=URL).data_dir == REPO_ROOT / "data"


def test_relative_data_dir_is_anchored_at_the_repo_root():
    assert Settings(database_url=URL, data_dir="files").data_dir == REPO_ROOT / "files"


def test_absolute_data_dir_is_kept_as_given(tmp_path: Path):
    assert Settings(database_url=URL, data_dir=tmp_path).data_dir == tmp_path


def test_upload_limit_is_converted_to_bytes():
    assert (
        Settings(database_url=URL, max_upload_mb=2).max_upload_bytes == 2 * 1024 * 1024
    )


@pytest.mark.parametrize("limit", [0, -5])
def test_upload_limit_must_be_positive(limit: int):
    with pytest.raises(ValidationError):
        Settings(database_url=URL, max_upload_mb=limit)
