from collections import Counter
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from merge_review.api.common import ensure_fetch_idle, latest_snapshot, lock_snapshot_cases
from merge_review.cases.rebuild import rebuild_queue
from merge_review.database import get_session
from merge_review.import_dataset import normalize_doi
from merge_review.models import Author, PublicationRecord
from merge_review.schemas import RefreshResponse, RefreshSource
from merge_review.sources.common import uncached_http_session
from merge_review.sources.refresh import (
    PUBLICATION_SOURCES,
    refresh_all_author_sources,
    refresh_author_source,
    refresh_publication_sources,
    refresh_source,
)

router = APIRouter()


def refresh_response(
    scope: str,
    target: str,
    results: Counter[str],
    cases: int,
) -> RefreshResponse:
    return RefreshResponse(
        scope=scope,
        target=target,
        results=dict(sorted(results.items())),
        cases=cases,
    )


def author_for_slug(session: Session, snapshot_id: UUID, author_slug: str) -> Author:
    author = session.scalar(
        select(Author).where(
            Author.dataset_snapshot_id == snapshot_id,
            Author.slug == author_slug,
        )
    )
    if author is None:
        raise HTTPException(404, detail="Author not found")
    return author


@router.post("/refresh/authors/{author_slug}", response_model=RefreshResponse)
def refresh_author(
    author_slug: str,
    session: Session = Depends(get_session),
) -> RefreshResponse:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")
    author = author_for_slug(session, snapshot.id, author_slug)

    lock_snapshot_cases(session, snapshot.id)
    ensure_fetch_idle(session)
    with uncached_http_session() as http_session:
        results = refresh_all_author_sources(session, http_session, author)
    cases = rebuild_queue(session, snapshot.id)
    session.commit()
    return refresh_response("author", author_slug, results, cases)


@router.post(
    "/refresh/authors/{author_slug}/sources/{source}",
    response_model=RefreshResponse,
)
def refresh_author_source_evidence(
    author_slug: str,
    source: RefreshSource,
    session: Session = Depends(get_session),
) -> RefreshResponse:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")
    author = author_for_slug(session, snapshot.id, author_slug)
    if source == "orcid" and not author.orcid_id:
        raise HTTPException(409, detail="Author has no ORCID identifier")

    lock_snapshot_cases(session, snapshot.id)
    ensure_fetch_idle(session)
    with uncached_http_session() as http_session:
        results = refresh_author_source(session, http_session, author, source)
    cases = rebuild_queue(session, snapshot.id)
    session.commit()
    return refresh_response("author_source", author_slug, results, cases)


@router.post("/refresh/dois/{doi:path}", response_model=RefreshResponse)
def refresh_doi(doi: str, session: Session = Depends(get_session)) -> RefreshResponse:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")
    normalized_doi = normalize_doi(doi)
    exists = session.scalar(
        select(PublicationRecord.id)
        .join(Author)
        .where(
            Author.dataset_snapshot_id == snapshot.id,
            PublicationRecord.normalized_doi == normalized_doi,
        )
        .limit(1)
    )
    if normalized_doi is None or exists is None:
        raise HTTPException(404, detail="DOI not found in the current dataset")

    lock_snapshot_cases(session, snapshot.id)
    ensure_fetch_idle(session)
    with uncached_http_session() as http_session:
        results = refresh_publication_sources(
            session,
            http_session,
            snapshot.id,
            [normalized_doi],
            set(PUBLICATION_SOURCES),
        )
    cases = rebuild_queue(session, snapshot.id)
    session.commit()
    return refresh_response("doi", normalized_doi, results, cases)


@router.post("/refresh/sources/{source}", response_model=RefreshResponse)
def refresh_source_evidence(
    source: RefreshSource,
    session: Session = Depends(get_session),
) -> RefreshResponse:
    snapshot = latest_snapshot(session)
    if snapshot is None:
        raise HTTPException(404, detail="No dataset imported")

    lock_snapshot_cases(session, snapshot.id)
    ensure_fetch_idle(session)
    with uncached_http_session() as http_session:
        results = refresh_source(session, http_session, snapshot.id, source)
    cases = rebuild_queue(session, snapshot.id)
    session.commit()
    return refresh_response("source", source, results, cases)
