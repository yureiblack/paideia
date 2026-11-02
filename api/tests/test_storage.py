"""Tests for app/storage.py: receiving, storing and deleting upload files.

Purpose: prove an upload is fingerprinted correctly, refused early when it is
too large or not a PDF, never leaves a partial file behind, and lands at the
path named by its document id.
"""

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app import storage
from tests import pdfs


class Source:
    """An upload arriving in chunks, recording how much was actually read."""

    def __init__(self, data: bytes, chunk_size: int = 1024):
        self.data, self.chunk_size, self.bytes_read = data, chunk_size, 0

    async def chunks(self) -> AsyncIterator[bytes]:
        for start in range(0, len(self.data), self.chunk_size):
            chunk = self.data[start : start + self.chunk_size]
            self.bytes_read += len(chunk)
            yield chunk


def stage(data: bytes, max_bytes: int = 10_000_000, chunk_size: int = 1024):
    source = Source(data, chunk_size)
    return asyncio.run(
        storage.stage_upload(source.chunks(), max_bytes=max_bytes)
    ), source


def leftovers(data_dir: Path) -> list[Path]:
    return list((data_dir / "tmp").glob("*"))


def test_staging_fingerprints_and_keeps_the_exact_bytes(data_dir: Path):
    data = pdfs.pdf("Processes", "Threads")

    staged, _ = stage(data)

    assert staged.sha256 == hashlib.sha256(data).hexdigest()
    assert staged.size_bytes == len(data)
    assert staged.path.read_bytes() == data


def test_stray_bytes_before_the_signature_are_accepted(data_dir: Path):
    staged, _ = stage(b"\xef\xbb\xbf\n" + pdfs.pdf("x"))

    assert staged.size_bytes > 0


def test_too_large_is_refused_without_reading_the_rest(data_dir: Path):
    data = b"%PDF-1.7\n" + b"x" * 100_000

    with pytest.raises(storage.UploadTooLarge, match="limit"):
        stage(data, max_bytes=20_000)
    assert leftovers(data_dir) == []


def test_reading_stops_at_the_limit(data_dir: Path):
    source = Source(b"%PDF-1.7\n" + b"x" * 100_000)

    with pytest.raises(storage.UploadTooLarge):
        asyncio.run(storage.stage_upload(source.chunks(), max_bytes=20_000))
    assert source.bytes_read < 25_000


def test_a_non_pdf_is_refused_after_the_first_kilobyte(data_dir: Path):
    source = Source(b"just some text\n" * 10_000)

    with pytest.raises(storage.NotAPdf, match="not a PDF"):
        asyncio.run(storage.stage_upload(source.chunks(), max_bytes=10_000_000))
    assert source.bytes_read <= 2048
    assert leftovers(data_dir) == []


@pytest.mark.parametrize(
    ("data", "message"),
    [
        pytest.param(b"", "empty", id="empty"),
        pytest.param(b"%PD", "not a PDF", id="shorter than the signature"),
        pytest.param(pdfs.png(), "not a PDF", id="png"),
    ],
)
def test_small_bad_uploads_are_refused(data_dir: Path, data: bytes, message: str):
    with pytest.raises(storage.NotAPdf, match=message):
        stage(data)
    assert leftovers(data_dir) == []


def test_store_moves_the_file_under_its_environment_named_by_id(data_dir: Path):
    staged, _ = stage(pdfs.pdf("x"))
    environment_id, document_id = uuid.uuid4(), uuid.uuid4()

    path = storage.store(staged, environment_id, document_id)

    assert path == data_dir / "uploads" / str(environment_id) / f"{document_id}.pdf"
    assert path.exists()
    assert not staged.path.exists()


def test_delete_helpers_remove_only_their_target(data_dir: Path):
    env_a, env_b = uuid.uuid4(), uuid.uuid4()
    doc_a1, doc_a2, doc_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for env, doc in [(env_a, doc_a1), (env_a, doc_a2), (env_b, doc_b)]:
        storage.store(stage(pdfs.pdf("x"))[0], env, doc)

    storage.delete_document_file(env_a, doc_a1)
    assert not storage.document_path(env_a, doc_a1).exists()
    assert storage.document_path(env_a, doc_a2).exists()

    storage.delete_environment_files(env_a)
    assert not storage.uploads_dir(env_a).exists()
    assert storage.document_path(env_b, doc_b).exists()


def test_deleting_what_is_not_there_is_harmless(data_dir: Path):
    storage.delete_document_file(uuid.uuid4(), uuid.uuid4())
    storage.delete_environment_files(uuid.uuid4())
