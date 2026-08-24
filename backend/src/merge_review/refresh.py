from collections import Counter
from uuid import UUID

from requests import Session
from sqlalchemy import select
from sqlalchemy.orm import Session as DatabaseSession

from merge_review.config import get_settings
from merge_review.models import Author, PublicationRecord
from merge_review.sync_openalex import sync_openalex_authors
from merge_review.sync_sources import (
    merge_counts,
    snapshot_dois,
    sync_openalex_author_publications,
    sync_openalex_publication_records,
    sync_orcid_records,
    sync_semantic_scholar_records,
)

PUBLICATION_SOURCES = (
    "openalex",
    "semantic_scholar",
)
AUTHOR_SOURCES = (*PUBLICATION_SOURCES, "orcid")


def author_dois(session: DatabaseSession, author_id: UUID) -> list[str]:
    return list(
        session.scalars(
            select(PublicationRecord.normalized_doi)
            .where(
                PublicationRecord.author_id == author_id,
                PublicationRecord.normalized_doi.is_not(None),
            )
            .distinct()
            .order_by(PublicationRecord.normalized_doi)
        )
    )


def refresh_publication_sources(
    session: DatabaseSession,
    http_session: Session,
    snapshot_id: UUID,
    dois: list[str],
    sources: set[str],
) -> Counter[str]:
    counts: Counter[str] = Counter()
    mailto = get_settings().mailto
    if "openalex" in sources:
        merge_counts(
            counts,
            "openalex_publications",
            sync_openalex_publication_records(
                session, http_session, snapshot_id, dois, mailto, force=True
            ),
        )
    if "semantic_scholar" in sources:
        merge_counts(
            counts,
            "semantic_scholar",
            sync_semantic_scholar_records(session, http_session, snapshot_id, dois, force=True),
        )
    return counts


def refresh_author_source(
    session: DatabaseSession,
    http_session: Session,
    author: Author,
    source: str,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    mailto = get_settings().mailto
    if source == "openalex":
        merge_counts(
            counts,
            "openalex_author",
            sync_openalex_authors(
                session,
                http_session,
                author.dataset_snapshot_id,
                mailto,
                [author.source_id],
                force=True,
            ),
        )
        merge_counts(
            counts,
            "openalex_author_publications",
            sync_openalex_author_publications(
                session,
                http_session,
                author.dataset_snapshot_id,
                mailto,
                [author.source_id],
                force=True,
            ),
        )
    elif source == "orcid" and author.orcid_id:
        merge_counts(
            counts,
            "orcid",
            sync_orcid_records(
                session,
                http_session,
                author.dataset_snapshot_id,
                [author.orcid_id],
                force=True,
            ),
        )
    if source in PUBLICATION_SOURCES:
        counts.update(
            refresh_publication_sources(
                session,
                http_session,
                author.dataset_snapshot_id,
                author_dois(session, author.id),
                {source},
            )
        )
    return counts


def refresh_author_sources(
    session: DatabaseSession,
    http_session: Session,
    author: Author,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for source in AUTHOR_SOURCES:
        counts.update(refresh_author_source(session, http_session, author, source))
    return counts


def refresh_source(
    session: DatabaseSession,
    http_session: Session,
    snapshot_id: UUID,
    source: str,
) -> Counter[str]:
    if source == "orcid":
        counts: Counter[str] = Counter()
        merge_counts(
            counts,
            "orcid",
            sync_orcid_records(session, http_session, snapshot_id, force=True),
        )
        return counts

    counts = refresh_publication_sources(
        session,
        http_session,
        snapshot_id,
        snapshot_dois(session, snapshot_id),
        {source},
    )
    if source == "openalex":
        mailto = get_settings().mailto
        merge_counts(
            counts,
            "openalex_author",
            sync_openalex_authors(session, http_session, snapshot_id, mailto, force=True),
        )
        merge_counts(
            counts,
            "openalex_author_publications",
            sync_openalex_author_publications(
                session, http_session, snapshot_id, mailto, force=True
            ),
        )
    return counts
