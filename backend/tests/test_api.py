from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from merge_review.api import router
from merge_review.database import get_session
from merge_review.models import (
    Author,
    Base,
    CaseEvidence,
    DatasetSnapshot,
    IdentityCandidate,
    IdentityCandidatePublication,
    PublicationRecord,
    SourceRecord,
    ValidationCase,
)
from merge_review.source_records import FetchStatus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

DUMMY_FETCHED_AT = datetime(2026, 8, 21, tzinfo=UTC)
DUMMY_SNAPSHOT_HASH = "a" * 64
DUMMY_DOI = "10.123/case"


def build_client() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    snapshot_id = uuid4()
    first_author_id = uuid4()
    second_author_id = uuid4()
    source_record_id = uuid4()
    candidate_id = uuid4()

    with factory.begin() as session:
        session.add(DatasetSnapshot(id=snapshot_id, dataset_sha256=DUMMY_SNAPSHOT_HASH))
        session.flush()
        session.add_all(
            [
                Author(
                    id=first_author_id,
                    dataset_snapshot_id=snapshot_id,
                    source_id="A123",
                    slug="Dummy_Author",
                    name="Dummy Author",
                    profile={"topics": ["Identity resolution"]},
                ),
                Author(
                    id=second_author_id,
                    dataset_snapshot_id=snapshot_id,
                    source_id="A456",
                    slug="Second_Author",
                    name="Second Author",
                    profile={},
                ),
            ]
        )
        session.add_all(
            [
                PublicationRecord(
                    author_id=first_author_id,
                    position=0,
                    normalized_doi=DUMMY_DOI,
                    title="Dummy Publication",
                    source="openalex",
                    payload={},
                ),
                PublicationRecord(
                    author_id=second_author_id,
                    position=0,
                    title="Second Publication",
                    source="openalex",
                    payload={},
                ),
            ]
        )
        session.add(
            SourceRecord(
                id=source_record_id,
                dataset_snapshot_id=snapshot_id,
                source="semantic_scholar",
                entity_type="publication",
                entity_key=DUMMY_DOI,
                source_record_id="paperID",
                url="https://example.com",
                fetch_status=FetchStatus.SUCCESS,
                http_status=200,
                fetched_at=DUMMY_FETCHED_AT,
                from_cache=True,
                payload={},
            )
        )
        session.add_all(
            [
                ValidationCase(
                    id="case-one",
                    dataset_snapshot_id=snapshot_id,
                    author_id=first_author_id,
                    case_type="author_identity",
                    status="pending",
                    priority="high",
                    affected_count=10,
                ),
                ValidationCase(
                    id="case-two",
                    dataset_snapshot_id=snapshot_id,
                    author_id=second_author_id,
                    case_type="author_identity",
                    status="deferred",
                    priority="medium",
                    affected_count=5,
                ),
            ]
        )
        session.flush()
        session.add(
            CaseEvidence(
                case_id="case-one",
                position=0,
                source="semantic_scholar",
                source_record_ids=[str(source_record_id)],
                source_refs=[{"entity_type": "author", "id": "candidateID"}],
                fetched_at=DUMMY_FETCHED_AT,
                fetch_status=FetchStatus.SUCCESS,
                field="author_identity",
                value="2 S2 IDs for publications matching this name",
                value_state="conflict",
                interpretation="Review signal",
            )
        )
        session.add(
            IdentityCandidate(
                id=candidate_id,
                case_id="case-one",
                position=0,
                semantic_scholar_author_id="candidateID",
                matched_publication_count=1,
                share=60.0,
                first_year=2020,
                last_year=2020,
            )
        )
        session.add(
            IdentityCandidatePublication(
                identity_candidate_id=candidate_id,
                position=0,
                doi=DUMMY_DOI,
                title="Dummy Publication",
                year=2020,
                source_record_id=source_record_id,
            )
        )

    def test_session():
        with factory() as session:
            yield session

    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_session] = test_session
    return TestClient(application)


def test_case_list_filters_search_and_pagination() -> None:
    client = build_client()

    response = client.get("/api/cases", params={"status": "pending", "query": "dum"})
    paged = client.get("/api/cases", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == ["case-one"]
    assert [row["id"] for row in paged.json()] == ["case-two"]


def test_case_detail_and_errors() -> None:
    client = build_client()

    response = client.get("/api/cases/case-one")

    assert response.status_code == 200
    assert response.json()["detail"]["top_share"] == 60.0
    assert response.json()["detail"]["candidate_ids"][0]["publications"] == [
        {"year": 2020, "title": "Dummy Publication"}
    ]
    assert client.get("/api/cases/missing").status_code == 404
    assert client.get("/api/cases", params={"status": "invalid"}).status_code == 422


def test_overview() -> None:
    client = build_client()

    response = client.get("/api/overview")

    assert response.status_code == 200
    assert response.json() == {
        "authors": 2,
        "publications": 15,
        "authors_audited": 2,
        "publications_audited": 2,
        "audited_at": "2026-08-21T00:00:00Z",
        "by_priority": {"high": 1, "medium": 1},
        "sources": [
            {
                "source": "semantic_scholar",
                "fetched_at": "2026-08-21T00:00:00Z",
                "state": "success",
                "note": "1 success",
            }
        ],
    }
