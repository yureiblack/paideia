"""Where uploaded PDFs live on disk, and how they get there.

Purpose
-------
The database holds what was extracted from a PDF; the original file lives on
disk. This module is the only code that knows the layout under
settings.data_dir:

    uploads/<environment id>/<document id>.pdf    stored originals
    tmp/                                          uploads still arriving

Files are named by document id, never by the name they were uploaded with, so
a hostile filename can never become a path. tmp/ sits inside data_dir so the
final move is a rename within one disk, which is atomic: a document's file is
either fully in place or not there at all.

settings.data_dir is read at call time rather than import time, so the tests
can point every function here at a temporary folder.
"""

import hashlib
import os
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

PDF_SIGNATURE = b"%PDF-"
# The PDF standard lets the signature appear anywhere in the first kilobyte,
# and some real files carry a few stray bytes before it. Readers accept those,
# so this does too.
SIGNATURE_WINDOW = 1024


class UploadRejected(Exception):
    """An upload refused before it was stored. The message is shown to the user."""


class UploadTooLarge(UploadRejected):
    pass


class NotAPdf(UploadRejected):
    pass


@dataclass(frozen=True)
class StagedUpload:
    """A fully received upload, sitting in tmp/ until it is stored."""

    path: Path
    sha256: str
    size_bytes: int


def uploads_dir(environment_id: uuid.UUID) -> Path:
    return settings.data_dir / "uploads" / str(environment_id)


def document_path(environment_id: uuid.UUID, document_id: uuid.UUID) -> Path:
    return uploads_dir(environment_id) / f"{document_id}.pdf"


async def stage_upload(chunks: AsyncIterator[bytes], *, max_bytes: int) -> StagedUpload:
    """Receive an upload into tmp/, fingerprinting and counting it on the way.

    Reading stops as soon as the upload passes max_bytes, or as soon as the
    first kilobyte has arrived without a PDF signature. Either way the partial
    file is deleted and nothing more of the upload is read.
    """
    tmp_dir = settings.data_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=tmp_dir, suffix=".part")
    path = Path(name)

    digest = hashlib.sha256()
    size = 0
    head = b""
    try:
        with os.fdopen(handle, "wb") as out:
            async for chunk in chunks:
                size += len(chunk)
                if size > max_bytes:
                    raise UploadTooLarge(
                        f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit."
                    )
                if len(head) < SIGNATURE_WINDOW:
                    head += chunk[: SIGNATURE_WINDOW - len(head)]
                    if len(head) >= SIGNATURE_WINDOW and PDF_SIGNATURE not in head:
                        raise NotAPdf("The file is not a PDF.")
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise NotAPdf("The file is empty.")
        if PDF_SIGNATURE not in head:
            raise NotAPdf("The file is not a PDF.")
    except BaseException:
        path.unlink(missing_ok=True)
        raise

    return StagedUpload(path=path, sha256=digest.hexdigest(), size_bytes=size)


def store(
    staged: StagedUpload, environment_id: uuid.UUID, document_id: uuid.UUID
) -> Path:
    """Move a staged upload to its permanent place, named by document id."""
    target = document_path(environment_id, document_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged.path, target)
    return target


def discard(staged: StagedUpload) -> None:
    """Delete a staged upload that will not be stored, such as a duplicate."""
    staged.path.unlink(missing_ok=True)


def delete_document_file(environment_id: uuid.UUID, document_id: uuid.UUID) -> None:
    document_path(environment_id, document_id).unlink(missing_ok=True)


def delete_environment_files(environment_id: uuid.UUID) -> None:
    """Remove an environment's whole upload folder, if it has one."""
    shutil.rmtree(uploads_dir(environment_id), ignore_errors=True)
