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

A picture, PNG or JPEG, a scan, a photograph of a board or a screenshot, is
made into a one-page PDF as it arrives and stored as one (decision record
29): everything after this module reads PDFs only. The same picture always
gives the same PDF, so a picture uploaded twice is found to be a duplicate.

sweep() removes what a crash can leave behind (decision record 21): a part
of an upload that never finished arriving, a stored file whose row was never
committed or whose deletion stopped halfway, and the folder of an
environment that no longer has any documents. It spares anything changed
recently, since an upload in progress has its file in place a moment
before its row is committed.
"""

import hashlib
import io
import os
import shutil
import tempfile
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from app.config import settings

PDF_SIGNATURE = b"%PDF-"
# Pictures, by the bytes they begin with.
PICTURE_SIGNATURES = {b"\x89PNG\r\n\x1a\n": "png", b"\xff\xd8\xff": "jpeg"}
# A picture is set on a page as wide as A4, so text in it is read at a
# sensible size, and never taller than a PDF page may be.
PICTURE_PAGE_WIDTH = 595.0
PICTURE_PAGE_MAX_HEIGHT = 14_000.0
EXIF_ORIENTATION = 0x0112
NOT_ACCEPTED = "The file is not a PDF or a picture (PNG or JPEG)."
# The PDF standard lets the signature appear anywhere in the first kilobyte,
# and some real files carry a few stray bytes before it. Readers accept those,
# so this does too.
SIGNATURE_WINDOW = 1024


class UploadRejected(Exception):
    """An upload refused before it was stored. The message is shown to the user."""


class UploadTooLarge(UploadRejected):
    pass


class NotAPdf(UploadRejected):
    """Neither a PDF nor a picture this app reads."""


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
                    if len(head) >= SIGNATURE_WINDOW and _kind(head) is None:
                        raise NotAPdf(NOT_ACCEPTED)
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise NotAPdf("The file is empty.")
        kind = _kind(head)
        if kind is None:
            raise NotAPdf(NOT_ACCEPTED)
        if kind != "pdf":
            return _as_pdf(path, kind)
    except BaseException:
        path.unlink(missing_ok=True)
        raise

    return StagedUpload(path=path, sha256=digest.hexdigest(), size_bytes=size)


def _kind(head: bytes) -> str | None:
    """pdf, png or jpeg, by the bytes the file begins with, or None."""
    for signature, kind in PICTURE_SIGNATURES.items():
        if head.startswith(signature):
            return kind
    return "pdf" if PDF_SIGNATURE in head else None


def picture_pdf(data: bytes) -> bytes:
    """A picture as a one-page PDF: turned upright as the camera recorded,
    on a page as wide as A4. The same picture always gives the same bytes."""
    try:
        with Image.open(io.BytesIO(data)) as opened:
            opened.load()
            size = opened.size
            # A camera records how it was held in the EXIF orientation tag:
            # 1 is upright, 2 to 8 a turn or a mirror to undo.
            if opened.getexif().get(EXIF_ORIENTATION, 1) in range(2, 9):
                upright = ImageOps.exif_transpose(opened)
                size = upright.size
                buffer = io.BytesIO()
                upright.convert("RGB").save(buffer, "JPEG", quality=92)
                data = buffer.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise NotAPdf("The picture could not be read.") from exc
    width = PICTURE_PAGE_WIDTH
    height = width * size[1] / size[0]
    if height > PICTURE_PAGE_MAX_HEIGHT:
        width, height = (
            width * PICTURE_PAGE_MAX_HEIGHT / height,
            PICTURE_PAGE_MAX_HEIGHT,
        )
    document = pymupdf.open()
    page = document.new_page(width=width, height=height)
    page.insert_image(page.rect, stream=data)
    pdf = document.tobytes(no_new_id=True, garbage=3, deflate=True)
    document.close()
    return pdf


def _as_pdf(path: Path, kind: str) -> StagedUpload:
    """The staged picture replaced by its PDF, fingerprinted and counted
    as the file that will be stored."""
    try:
        pdf = picture_pdf(path.read_bytes())
    finally:
        path.unlink(missing_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, suffix=".part")
    target = Path(name)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(pdf)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return StagedUpload(
        path=target, sha256=hashlib.sha256(pdf).hexdigest(), size_bytes=len(pdf)
    )


def store(
    staged: StagedUpload, environment_id: uuid.UUID, document_id: uuid.UUID
) -> Path:
    """Move a staged upload to its permanent place, named by document id."""
    target = document_path(environment_id, document_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged.path, target)
    return target


def fingerprint(path: Path) -> str | None:
    """The SHA-256 of a stored file, or None if it is missing."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
    except FileNotFoundError:
        return None
    return digest.hexdigest()


def set_aside(environment_id: uuid.UUID, document_id: uuid.UUID) -> Path | None:
    """Move a document's file aside before replacing it, so it can be put
    back if the change is not committed. None if there was no file."""
    current = document_path(environment_id, document_id)
    aside = current.with_name(current.name + ".previous")
    try:
        os.replace(current, aside)
    except FileNotFoundError:
        return None
    return aside


def put_back(
    aside: Path | None, environment_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    """Restore a file set aside, over whatever replaced it."""
    if aside is not None:
        os.replace(aside, document_path(environment_id, document_id))


def forget(aside: Path | None) -> None:
    """Delete a file set aside, once its replacement is committed."""
    if aside is not None:
        aside.unlink(missing_ok=True)


def discard(staged: StagedUpload) -> None:
    """Delete a staged upload that will not be stored, such as a duplicate."""
    staged.path.unlink(missing_ok=True)


def delete_document_file(environment_id: uuid.UUID, document_id: uuid.UUID) -> None:
    document_path(environment_id, document_id).unlink(missing_ok=True)


def delete_environment_files(environment_id: uuid.UUID) -> None:
    """Remove an environment's whole upload folder, if it has one."""
    shutil.rmtree(uploads_dir(environment_id), ignore_errors=True)


# A stored file or folder younger than this may belong to an upload whose
# row is about to be committed; a part in tmp/ younger than TMP_GRACE may
# still be arriving.
STORED_GRACE = 60 * 60  # seconds
TMP_GRACE = 24 * 60 * 60


@dataclass
class Swept:
    """What a sweep removed."""

    parts: list[Path] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)
    folders: list[Path] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.parts or self.files or self.folders)


def _as_uuid(text: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(text)
    except ValueError:
        return None


def sweep(
    documents: set[tuple[uuid.UUID, uuid.UUID]], now: float | None = None
) -> Swept:
    """Remove what no document accounts for. documents holds every
    (environment id, document id) in the database."""
    now = time.time() if now is None else now
    swept = Swept()

    def old(path: Path, grace: int) -> bool:
        return now - path.stat().st_mtime > grace

    tmp_dir = settings.data_dir / "tmp"
    if tmp_dir.is_dir():
        for path in tmp_dir.iterdir():
            if path.is_file() and old(path, TMP_GRACE):
                path.unlink(missing_ok=True)
                swept.parts.append(path)

    uploads = settings.data_dir / "uploads"
    if not uploads.is_dir():
        return swept
    in_use = {environment_id for environment_id, _ in documents}
    for folder in uploads.iterdir():
        if not folder.is_dir():
            continue
        environment_id = _as_uuid(folder.name)
        for path in folder.iterdir():
            document_id = _as_uuid(path.stem) if path.suffix == ".pdf" else None
            known = (environment_id, document_id) in documents
            if path.is_file() and not known and old(path, STORED_GRACE):
                path.unlink(missing_ok=True)
                swept.files.append(path)
        empty = not any(folder.iterdir())
        if empty and environment_id not in in_use and old(folder, STORED_GRACE):
            folder.rmdir()
            swept.folders.append(folder)
    return swept
