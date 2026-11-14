"""Concepts: an environment's inventory, and each document's extraction.

Purpose
-------
    GET  /api/environments/{environment_id}/concepts   every concept, and
                                                       each document's state
    GET  /api/documents/{document_id}/concepts         one document's
    POST /api/documents/{document_id}/concepts         make sure they are
                                                       extracted (or retry)

Concepts are extracted in the background once a document is read. POST asks
for the same by hand: it never extracts twice for the same text, model and
prompt, and answers 200 when ready, 202 when waiting or being extracted.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status

from app.db import SessionDep, SessionFactoryDep
from app.routers.deps import DispatcherDep, LLMDep
from app.routers.documents import DocumentDep
from app.routers.environments import EnvironmentDep
from app.schemas import ConceptInventory, DocumentConceptsRead
from app.services import concepts as service
from app.services import jobs
from app.services import summaries as summary_service

router = APIRouter(tags=["concepts"])


@router.get("/environments/{environment_id}/concepts", response_model=ConceptInventory)
def read_inventory(
    environment: EnvironmentDep, session: SessionDep, llm: LLMDep
) -> ConceptInventory:
    return service.inventory(session, environment.id, llm)


@router.get("/documents/{document_id}/concepts", response_model=DocumentConceptsRead)
def read_document_concepts(
    document: DocumentDep, session: SessionDep, llm: LLMDep
) -> DocumentConceptsRead:
    return service.document_concepts(session, document, llm)


@router.post(
    "/documents/{document_id}/concepts",
    response_model=DocumentConceptsRead,
    responses={202: {"description": "Waiting or being extracted"}},
)
def request_concepts(
    document: DocumentDep,
    session: SessionDep,
    session_factory: SessionFactoryDep,
    llm: LLMDep,
    dispatcher: DispatcherDep,
    background: BackgroundTasks,
    response: Response,
) -> DocumentConceptsRead:
    try:
        artifact, write_now = service.request_extraction(session, document, llm)
    except summary_service.NotReadyToSummarize as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if artifact.status == "failed":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=artifact.error
        )
    body = service.document_concepts(session, document, llm)
    session.commit()  # end this read before the background task (record 09)
    if write_now:
        jobs.queue_model_work(
            session,
            document.environment_id,
            "concepts",
            f"Extracting concepts from {document.filename}",
            [
                jobs.step(
                    "write_extraction", "Extracting concepts", artifact_id=artifact.id
                ),
                jobs.step(
                    "graph",
                    "Updating the knowledge map",
                    environment_id=document.environment_id,
                ),
                jobs.step(
                    "roadmap",
                    "Updating the roadmap",
                    environment_id=document.environment_id,
                ),
            ],
            session_factory=session_factory,
            llm=llm,
            dispatcher=dispatcher,
            background=background,
        )
    if artifact.status != "ready":
        response.status_code = status.HTTP_202_ACCEPTED
    return body
