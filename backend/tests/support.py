from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from merge_review.api import router
from merge_review.api.fetches import authenticate_fetch
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
from sqlalchemy.orm import Session, sessionmaker
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


@dataclass(frozen=True)
class ApiSeed:
    snapshot_id: UUID
    first_author_id: UUID
    second_author_id: UUID
    test_user_id: UUID


def make_response(status_code: int, payload: object | None = None) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 400
    response.created_at = DUMMY_FETCHED_AT
    response.from_cache = False
    response.headers = {}
    response.json.return_value = payload
    return response


def session_factory(query_log: list[str] | None) -> sessionmaker:
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
    return sessionmaker(bind=engine)


def seed_snapshot(
    session: Session,
    completed_fetch_at: datetime | None,
    fetch_status: str | None,
) -> ApiSeed:
    seed = ApiSeed(uuid4(), uuid4(), uuid4(), uuid4())
    session.add(
        User(
            id=seed.test_user_id,
            username="test-reviewer",
            display_name="Test Reviewer",
            password_hash="test-only",
        )
    )
    session.add(DatasetSnapshot(id=seed.snapshot_id, dataset_sha256=DUMMY_SNAPSHOT_HASH))
    session.flush()
    session.add(
        ReviewSettings(
            dataset_snapshot_id=seed.snapshot_id,
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
            dataset_snapshot_id=seed.snapshot_id,
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
    return seed


def seed_authors(session: Session, seed: ApiSeed) -> None:
    session.add_all(
        [
            Author(
                id=seed.first_author_id,
                dataset_snapshot_id=seed.snapshot_id,
                source_id="A123",
                slug="Dummy_Author",
                name="Dummy Author",
                affiliation="Dummy University",
                profile={"topics": ["Identity resolution"]},
            ),
            Author(
                id=seed.second_author_id,
                dataset_snapshot_id=seed.snapshot_id,
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
                author_id=seed.first_author_id,
                position=0,
                normalized_doi=DUMMY_DOI,
                title="Dummy Publication",
                source="openalex",
                payload={},
            ),
            PublicationRecord(
                author_id=seed.second_author_id,
                position=0,
                title="Second Publication",
                source="openalex",
                payload={},
            ),
        ]
    )


def seed_sources(session: Session, seed: ApiSeed) -> UUID:
    semantic_scholar_record_id = uuid4()
    session.add(
        SourceRecord(
            id=semantic_scholar_record_id,
            dataset_snapshot_id=seed.snapshot_id,
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
            id=uuid4(),
            dataset_snapshot_id=seed.snapshot_id,
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
    return semantic_scholar_record_id


def priority_components(
    publication_value: float,
    fragmentation_value: float,
    cluster_value: float,
) -> dict[str, dict[str, float]]:
    return {
        "publication_impact": {
            "value": publication_value,
            "snapshot_max": 10.0,
            "score": publication_value * 10,
        },
        "fragmentation": {
            "value": fragmentation_value,
            "snapshot_max": 50.0,
            "score": fragmentation_value * 2,
        },
        "cluster_ambiguity": {
            "value": cluster_value,
            "snapshot_max": 4.0,
            "score": cluster_value * 25,
        },
    }


def validation_case(
    *,
    case_id: str,
    snapshot_id: UUID,
    author_id: UUID,
    status: str,
    queue_eligible: bool,
    priority_score: float,
    components: dict[str, dict[str, float]],
    evidence_sha256: str,
    affected_count: int,
) -> ValidationCase:
    return ValidationCase(
        id=case_id,
        dataset_snapshot_id=snapshot_id,
        author_id=author_id,
        case_type="author_identity",
        status=status,
        queue_eligible=queue_eligible,
        priority_score=priority_score,
        priority_components=components,
        priority_config=DUMMY_PRIORITY_CONFIG,
        evidence_sha256=evidence_sha256,
        affected_count=affected_count,
    )


def seed_cases(
    session: Session,
    seed: ApiSeed,
    second_case_eligible: bool,
    extra_cases: int,
) -> None:
    session.add_all(
        [
            validation_case(
                case_id="case-one",
                snapshot_id=seed.snapshot_id,
                author_id=seed.first_author_id,
                status="pending",
                queue_eligible=True,
                priority_score=76.7,
                components=priority_components(10, 40, 2),
                evidence_sha256="a" * 64,
                affected_count=10,
            ),
            validation_case(
                case_id="case-two",
                snapshot_id=seed.snapshot_id,
                author_id=seed.second_author_id,
                status="deferred",
                queue_eligible=second_case_eligible,
                priority_score=41.7,
                components=priority_components(5, 25, 1),
                evidence_sha256="b" * 64,
                affected_count=5,
            ),
        ]
    )
    for index in range(extra_cases):
        author_id = uuid4()
        session.add(
            Author(
                id=author_id,
                dataset_snapshot_id=seed.snapshot_id,
                source_id=f"A{index:04d}",
                slug=f"Filler_Author_{index}",
                name=f"Filler Author {index}",
                profile={},
            )
        )
        session.add(
            validation_case(
                case_id=f"case-filler-{index}",
                snapshot_id=seed.snapshot_id,
                author_id=author_id,
                status="pending",
                queue_eligible=True,
                priority_score=10.0,
                components=priority_components(1, 5, 1),
                evidence_sha256=f"{index:064d}",
                affected_count=1,
            )
        )


def seed_case_details(session: Session, source_record_id: UUID) -> None:
    candidate_id = uuid4()
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


def test_client(factory: sessionmaker, user_id: UUID) -> TestClient:
    def test_session():
        with factory() as session:
            yield session

    def test_current_user():
        with factory() as session:
            return session.get(User, user_id)

    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_session] = test_session
    application.dependency_overrides[get_current_user] = test_current_user
    application.dependency_overrides[authenticate_writes] = test_current_user
    application.dependency_overrides[authenticate_fetch] = test_current_user
    application.state.session_factory = factory
    application.state.test_user_id = user_id
    return TestClient(application)


def build_client(
    query_log: list[str] | None = None,
    second_case_eligible: bool = True,
    completed_fetch_at: datetime | None = None,
    extra_cases: int = 0,
    fetch_status: str | None = None,
) -> TestClient:
    factory = session_factory(query_log)
    with factory.begin() as session:
        seed = seed_snapshot(session, completed_fetch_at, fetch_status)
        seed_authors(session, seed)
        source_record_id = seed_sources(session, seed)
        seed_cases(session, seed, second_case_eligible, extra_cases)
        session.flush()
        seed_case_details(session, source_record_id)
    return test_client(factory, seed.test_user_id)
