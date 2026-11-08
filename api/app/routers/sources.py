"""GET /api/chunks/{chunk_id}/preview: a cited passage shown in its place.

Purpose
-------
Opens a citation: the document and pages it points to, with the passage
highlighted within each page, so a reader can check a search result, or later
a summary's claim, against the material itself.
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.db import SessionDep
from app.schemas import SourcePreview
from app.services import sources as service

router = APIRouter(tags=["sources"])


@router.get("/chunks/{chunk_id}/preview", response_model=SourcePreview)
def read_preview(chunk_id: uuid.UUID, session: SessionDep) -> SourcePreview:
    found = service.preview(session, chunk_id)
    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=(
                "This passage is no longer in its document. The document may "
                "have been reprocessed or deleted; search again."
            ),
        )
    return found
