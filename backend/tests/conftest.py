from datetime import UTC, datetime
from unittest.mock import Mock
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
    FetchRun,
    IdentityCandidate,
    IdentityCandidatePublication,
    PublicationRecord,
    ReviewSettings,
    SourceRecord,
    User,
    ValidationCase,
)
from merge_review.security import authenticate_writes, get_current_user
from merge_review.sources.common import FetchStatus
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

DUMMY_FETCHED_AT = datetime(2026, 8, 21, tzinfo=UTC)
DUMMY_SNAPSHOT_HASH = "a" * 64
DUMMY_DOI = "10.123/case"
DUMMY_PRIORITY_CONFIG = {
    "weights": {
        "publication_impact": 1 / 3,
        "fragmentation": 1 / 3,
        "cluster_ambiguity": 1 / 3,
    },
    "max_top_candidate_share": 75.0,
}


def make_response(status_code: int, payload: object | None = None) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 400
    response.created_at = DUMMY_FETCHED_AT
    response.from_cache = False
    response.headers = {}
    response.json.return_value = payload
    return response


def build_client(
    query_log: list[str] | None = None,
    second_case_eligible: bool = True,
    completed_fetch_at: datetime | None = None,
    extra_cases: int = 0,
    fetch_status: str | None = None,
) -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    if query_log is not None:

        def record_query(
            _connection,
            _cursor,
            statement,
            _parameters,
            _context,
            _executemany,
        ) -> None:
            query_log.append(statement)

        event.listen(engine, "before_cursor_execute", record_query)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    snapshot_id = uuid4()
    first_author_id = uuid4()
    second_author_id = uuid4()
    source_record_id = uuid4()
    openalex_source_record_id = uuid4()
    candidate_id = uuid4()
    test_user_id = uuid4()

    with factory.begin() as session:
        session.add(
            User(
                id=test_user_id,
                username="test-reviewer",
                display_name="Test Reviewer",
                password_hash="test-only",
            )
        )
        session.add(DatasetSnapshot(id=snapshot_id, dataset_sha256=DUMMY_SNAPSHOT_HASH))
        session.flush()
        session.add(
            ReviewSettings(
                dataset_snapshot_id=snapshot_id,
                max_top_candidate_share=75,
                priority_weights={
                    "publication_impact": 1,
                    "fragmentation": 1,
                    "cluster_ambiguity": 1,
                },
                version=1,
                queue_updated_at=DUMMY_FETCHED_AT,
            )
        )
        fetch_completed_at = completed_fetch_at or DUMMY_FETCHED_AT
        session.add(
            FetchRun(
                dataset_snapshot_id=snapshot_id,
                status=fetch_status or "complete",
                source_progress={
                    "semantic_scholar": {
                        "completed": 1,
                        "total": 1,
                        "by_status": {"success": 1},
                        "completed_at": fetch_completed_at.isoformat(),
                    }
                },
                created_at=fetch_completed_at,
                started_at=fetch_completed_at,
                finished_at=fetch_completed_at,
            )
        )
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
                payload={
                    "title": "Dummy Publication",
                    "year": 2020,
                    "authors": [{"authorId": "candidateID", "name": "Dummy Author"}],
                },
            )
        )
        session.add(
            SourceRecord(
                id=openalex_source_record_id,
                dataset_snapshot_id=snapshot_id,
                source="openalex",
                entity_type="author",
                entity_key="A123",
                source_record_id="A123",
                url="https://openalex.org/A123",
                fetch_status=FetchStatus.SUCCESS,
                http_status=200,
                fetched_at=DUMMY_FETCHED_AT,
                from_cache=True,
                payload={
                    "topics": [
                        {
                            "id": "https://openalex.org/T123",
                            "display_name": "Fetched Identity Topic",
                        }
                    ]
                },
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
                    queue_eligible=True,
                    priority_score=76.7,
                    priority_components={
                        "publication_impact": {
                            "value": 10.0,
                            "snapshot_max": 10.0,
                            "score": 100.0,
                        },
                        "fragmentation": {
                            "value": 40.0,
                            "snapshot_max": 50.0,
                            "score": 80.0,
                        },
                        "cluster_ambiguity": {
                            "value": 2.0,
                            "snapshot_max": 4.0,
                            "score": 50.0,
                        },
                    },
                    priority_config=DUMMY_PRIORITY_CONFIG,
                    evidence_sha256="a" * 64,
                    affected_count=10,
                ),
                ValidationCase(
                    id="case-two",
                    dataset_snapshot_id=snapshot_id,
                    author_id=second_author_id,
                    case_type="author_identity",
                    status="deferred",
                    queue_eligible=second_case_eligible,
                    priority_score=41.7,
                    priority_components={
                        "publication_impact": {
                            "value": 5.0,
                            "snapshot_max": 10.0,
                            "score": 50.0,
                        },
                        "fragmentation": {
                            "value": 25.0,
                            "snapshot_max": 50.0,
                            "score": 50.0,
                        },
                        "cluster_ambiguity": {
                            "value": 1.0,
                            "snapshot_max": 4.0,
                            "score": 25.0,
                        },
                    },
                    priority_config=DUMMY_PRIORITY_CONFIG,
                    evidence_sha256="b" * 64,
                    affected_count=5,
                ),
            ]
        )
        for index in range(extra_cases):
            filler_author_id = uuid4()
            session.add(
                Author(
                    id=filler_author_id,
                    dataset_snapshot_id=snapshot_id,
                    source_id=f"A{index:04d}",
                    slug=f"Filler_Author_{index}",
                    name=f"Filler Author {index}",
                    profile={},
                )
            )
            session.add(
                ValidationCase(
                    id=f"case-filler-{index}",
                    dataset_snapshot_id=snapshot_id,
                    author_id=filler_author_id,
                    case_type="author_identity",
                    status="pending",
                    queue_eligible=True,
                    priority_score=10.0,
                    priority_components={
                        "publication_impact": {
                            "value": 1.0,
                            "snapshot_max": 10.0,
                            "score": 10.0,
                        },
                        "fragmentation": {
                            "value": 5.0,
                            "snapshot_max": 50.0,
                            "score": 10.0,
                        },
                        "cluster_ambiguity": {
                            "value": 1.0,
                            "snapshot_max": 4.0,
                            "score": 25.0,
                        },
                    },
                    priority_config=DUMMY_PRIORITY_CONFIG,
                    evidence_sha256=f"{index:064d}",
                    affected_count=1,
                )
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

    def test_current_user():
        with factory() as session:
            return session.get(User, test_user_id)

    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_session] = test_session
    application.dependency_overrides[get_current_user] = test_current_user
    application.dependency_overrides[authenticate_writes] = test_current_user
    application.state.session_factory = factory
    application.state.test_user_id = test_user_id
    return TestClient(application)
