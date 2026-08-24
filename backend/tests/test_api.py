from collections import Counter
from datetime import UTC, datetime
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from merge_review.api import fetch_source_statuses, router
from merge_review.database import get_session
from merge_review.models import (
    AuditRun,
    Author,
    Base,
    CaseEvidence,
    DatasetSnapshot,
    IdentityCandidate,
    IdentityCandidatePublication,
    PublicationRecord,
    ReviewSettings,
    SourceRecord,
    ValidationCase,
)
from merge_review.source_records import FetchStatus
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


def test_fetch_source_statuses_aggregate_openalex_stages() -> None:
    fetch = AuditRun(
        status="complete",
        source_progress={
            "openalex_authors": {
                "completed": 500,
                "total": 500,
                "by_status": {"success": 500},
                "completed_at": "2026-08-21T00:00:00Z",
            },
            "openalex_publications": {
                "completed": 4124,
                "total": 4124,
                "by_status": {"success": 4057, "not_found": 67},
                "completed_at": "2026-08-21T00:01:00Z",
            },
        },
        finished_at=DUMMY_FETCHED_AT,
    )

    statuses = fetch_source_statuses(fetch)

    assert [status.model_dump() for status in statuses] == [
        {
            "source": "openalex",
            "fetched_at": datetime(2026, 8, 21, 0, 1, tzinfo=UTC),
            "state": "partially_available",
            "note": "4,557 found. 67 not found",
        }
    ]


def test_a_source_that_never_answered_is_unavailable() -> None:
    fetch = AuditRun(
        status="complete",
        source_progress={
            "orcid": {
                "completed": 3,
                "total": 3,
                "by_status": {"rate_limited": 3},
                "completed_at": "2026-08-21T00:00:00Z",
            }
        },
        finished_at=DUMMY_FETCHED_AT,
    )

    assert [status.state for status in fetch_source_statuses(fetch)] == ["unavailable"]


def build_client(
    query_log: list[str] | None = None,
    second_case_eligible: bool = True,
    completed_audit_at: datetime | None = None,
    extra_cases: int = 0,
    audit_status: str | None = None,
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

    with factory.begin() as session:
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
                last_audited_at=DUMMY_FETCHED_AT,
            )
        )
        fetch_completed_at = completed_audit_at or DUMMY_FETCHED_AT
        session.add(
            AuditRun(
                dataset_snapshot_id=snapshot_id,
                status=audit_status or "complete",
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


def case_list_query_count(extra_cases: int) -> tuple[int, int]:
    query_log: list[str] = []
    client = build_client(query_log, extra_cases=extra_cases)
    query_log.clear()

    response = client.get("/api/cases", params={"limit": 100})

    assert response.status_code == 200
    assert any("validation_cases" in statement and "LIMIT" in statement for statement in query_log)
    return len(response.json()), len(query_log)


def test_case_list_batches_detail_queries_instead_of_querying_per_case() -> None:
    small_cases, small_queries = case_list_query_count(0)
    large_cases, large_queries = case_list_query_count(20)

    assert (small_cases, large_cases) == (2, 22)
    assert small_queries == large_queries
    assert large_queries < 15


def test_case_detail_and_errors() -> None:
    client = build_client()

    response = client.get("/api/cases/case-one")

    assert response.status_code == 200
    assert response.json()["queue_eligible"] is True
    assert response.json()["priority_score"] == 76.7
    assert response.json()["priority_components"]["fragmentation"] == {
        "value": 40.0,
        "snapshot_max": 50.0,
        "score": 80.0,
    }
    assert response.json()["detail"]["top_share"] == 60.0
    assert response.json()["detail"]["openalex_topics"] == [
        "Fetched Identity Topic"
    ]
    assert response.json()["detail"]["candidate_ids"][0]["publications"] == [
        {"year": 2020, "title": "Dummy Publication"}
    ]
    assert client.get("/api/cases/missing").status_code == 404
    assert client.get("/api/cases", params={"status": "invalid"}).status_code == 422


def test_archived_cases_are_separate_from_the_active_queue() -> None:
    client = build_client(second_case_eligible=False)

    active = client.get("/api/cases")
    archived = client.get("/api/cases", params={"scope": "archived"})
    overview = client.get("/api/overview")

    assert [row["id"] for row in active.json()] == ["case-one"]
    assert [row["id"] for row in archived.json()] == ["case-two"]
    assert archived.json()[0]["queue_eligible"] is False
    assert overview.json()["flagged_authors"] == 1
    assert overview.json()["affected_publications"] == 10
    assert client.get("/api/cases", params={"scope": "unknown"}).status_code == 422


def test_overview() -> None:
    client = build_client()

    response = client.get("/api/overview")

    assert response.status_code == 200
    assert response.json() == {
        "flagged_authors": 2,
        "affected_publications": 15,
        "total_authors": 2,
        "total_publications": 2,
        "audited_at": "2026-08-21T00:00:00Z",
        "sources": [
            {
                "source": "semantic_scholar",
                "fetched_at": "2026-08-21T00:00:00Z",
                "state": "available",
                "note": "1 found",
            }
        ],
    }


def test_audit_config_is_versioned_and_audit_recomputes_cases() -> None:
    client = build_client()

    current = client.get("/api/audit-config")
    with patch(
        "merge_review.api.run_audit",
        return_value=1,
    ) as run_audit:
        updated = client.put(
            "/api/audit-config",
            json={
                "max_top_candidate_share": 100,
                "weights": {
                    "publication_impact": 2,
                    "fragmentation": 1,
                    "cluster_ambiguity": 1,
                },
                "expected_version": 1,
            },
        )
        audit = client.post("/api/audits")
    stale = client.put(
        "/api/audit-config",
        json={
            "max_top_candidate_share": 75,
            "weights": {
                "publication_impact": 1,
                "fragmentation": 1,
                "cluster_ambiguity": 1,
            },
            "expected_version": 1,
        },
    )

    assert current.status_code == 200
    assert current.json()["version"] == 1
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["weights"]["publication_impact"] == 2
    assert audit.status_code == 200
    assert audit.json() == {
        "config_version": 2,
        "cases": 1,
    }
    assert run_audit.call_count == 1
    assert stale.status_code == 409


def test_audit_run_blocks_application_requests() -> None:
    client = build_client()

    with patch("merge_review.api.run_full_audit") as run_audit:
        started = client.post("/api/fetches")

    current = client.get("/api/fetches/current")
    blocked = client.get("/api/cases")

    assert started.status_code == 202
    assert started.json()["status"] == "queued"
    assert current.json()["id"] == started.json()["id"]
    assert blocked.status_code == 423
    assert run_audit.call_count == 1


def test_audit_status_includes_last_successful_run() -> None:
    client = build_client(completed_audit_at=DUMMY_FETCHED_AT)

    response = client.get("/api/fetches/current")

    assert response.status_code == 200
    assert response.json()["status"] == "complete"
    assert response.json()["last_completed_at"] == "2026-08-21T00:00:00Z"


def test_only_a_failed_audit_can_be_abandoned() -> None:
    client = build_client()

    fetch_id = client.get("/api/fetches/current").json()["id"]

    complete = client.post(f"/api/fetches/{fetch_id}/abandon")

    assert complete.status_code == 409
    assert complete.json()["detail"] == "Only a failed audit can be abandoned"
    assert client.post(f"/api/fetches/{uuid4()}/abandon").status_code == 404


def test_abandoning_a_failed_audit_unblocks_a_new_one() -> None:
    client = build_client(audit_status="failed")
    fetch_id = client.get("/api/fetches/current").json()["id"]

    abandoned = client.post(f"/api/fetches/{fetch_id}/abandon")
    with patch("merge_review.api.run_full_audit"):
        restarted = client.post("/api/fetches")

    assert abandoned.status_code == 200
    assert abandoned.json()["status"] == "abandoned"
    assert restarted.status_code == 202
    assert restarted.json()["id"] != fetch_id


def test_refresh_doi_bypasses_cache_and_recomputes_cases() -> None:
    client = build_client()
    http_session = Mock()
    http_context = Mock()
    http_context.__enter__ = Mock(return_value=http_session)
    http_context.__exit__ = Mock(return_value=False)

    with (
        patch("merge_review.api.uncached_http_session", return_value=http_context),
        patch("merge_review.api.lock_snapshot_cases") as lock_cases,
        patch(
            "merge_review.api.refresh_publication_sources",
            return_value=Counter({"semantic_scholar:success": 1}),
        ) as refresh,
        patch(
            "merge_review.api.run_audit",
            return_value=1,
        ) as audit,
    ):
        response = client.post(f"/api/refresh/dois/{DUMMY_DOI}")

    assert response.status_code == 200
    assert response.json() == {
        "scope": "doi",
        "target": DUMMY_DOI,
        "results": {"semantic_scholar:success": 1},
        "cases": 1,
    }
    assert refresh.call_args.args[3] == [DUMMY_DOI]
    assert lock_cases.call_count == 1
    assert audit.call_count == 1


def test_refresh_author_and_source_scopes() -> None:
    client = build_client()
    http_session = Mock()
    http_context = Mock()
    http_context.__enter__ = Mock(return_value=http_session)
    http_context.__exit__ = Mock(return_value=False)

    with (
        patch("merge_review.api.uncached_http_session", return_value=http_context),
        patch("merge_review.api.lock_snapshot_cases") as lock_cases,
        patch(
            "merge_review.api.refresh_author_sources",
            return_value=Counter({"openalex_author:success": 1}),
        ) as refresh_author,
        patch(
            "merge_review.api.refresh_author_source",
            return_value=Counter({"semantic_scholar:success": 1}),
        ) as refresh_author_source,
        patch(
            "merge_review.api.refresh_source",
            return_value=Counter({"orcid:success": 1}),
        ) as refresh_source,
        patch(
            "merge_review.api.run_audit",
            return_value=1,
        ),
    ):
        author_response = client.post("/api/refresh/authors/Dummy_Author")
        author_source_response = client.post(
            "/api/refresh/authors/Dummy_Author/sources/semantic_scholar"
        )
        source_response = client.post("/api/refresh/sources/orcid")

    assert author_response.status_code == 200
    assert author_response.json()["scope"] == "author"
    assert author_source_response.status_code == 200
    assert author_source_response.json()["scope"] == "author_source"
    assert source_response.status_code == 200
    assert source_response.json()["scope"] == "source"
    assert refresh_author.call_count == 1
    assert refresh_author_source.call_args.args[3] == "semantic_scholar"
    assert refresh_source.call_args.args[3] == "orcid"
    assert lock_cases.call_count == 3
    assert (
        client.post("/api/refresh/authors/Dummy_Author/sources/orcid").status_code
        == 409
    )
    assert (
        client.post("/api/refresh/authors/Dummy_Author/sources/unknown").status_code
        == 422
    )
    assert client.post("/api/refresh/sources/unknown").status_code == 422


def test_decisions_are_versioned_and_append_activity() -> None:
    client = build_client()

    first = client.post(
        "/api/cases/case-one/decisions",
        json={
            "action": "flag_for_split",
            "note": "  Distinct publication clusters  ",
            "expected_version": 1,
        },
    )
    stale = client.post(
        "/api/cases/case-one/decisions",
        json={"action": "mark_uncertain", "expected_version": 1},
    )
    reopened = client.post(
        "/api/cases/case-one/decisions",
        json={"action": "reopen", "expected_version": 2},
    )
    detail = client.get("/api/cases/case-one")
    activity = client.get("/api/activity")

    assert first.status_code == 200
    assert first.json()["before"] == "pending"
    assert first.json()["after"] == "needs_split"
    assert first.json()["note"] == "Distinct publication clusters"
    assert stale.status_code == 409
    assert reopened.status_code == 200
    assert detail.json()["status"] == "pending"
    assert detail.json()["version"] == 3
    assert [event["action_type"] for event in activity.json()] == [
        "reopen",
        "flag_for_split",
    ]


def test_every_decision_action_moves_the_case_to_its_status() -> None:
    client = build_client()
    statuses = []

    for version, action in enumerate(
        ["defer", "mark_uncertain", "confirm_one_author", "reopen"],
        start=1,
    ):
        response = client.post(
            "/api/cases/case-one/decisions",
            json={"action": action, "expected_version": version},
        )
        assert response.status_code == 200
        statuses.append(response.json()["after"])

    assert statuses == ["deferred", "uncertain", "one_author", "pending"]


def test_repeating_a_decision_is_rejected_but_a_note_is_not() -> None:
    client = build_client()

    repeated = client.post(
        "/api/cases/case-one/decisions",
        json={"action": "reopen", "expected_version": 1},
    )
    noted = client.post(
        "/api/cases/case-one/decisions",
        json={"action": "note", "note": "Still pending", "expected_version": 1},
    )

    assert repeated.status_code == 409
    assert repeated.json()["detail"] == "Case is already in that state"
    assert noted.status_code == 200
    assert noted.json()["before"] == noted.json()["after"] == "pending"


def test_note_requires_content() -> None:
    client = build_client()

    response = client.post(
        "/api/cases/case-one/decisions",
        json={"action": "note", "note": "   ", "expected_version": 1},
    )

    assert response.status_code == 422
    assert client.get("/api/activity").json() == []
