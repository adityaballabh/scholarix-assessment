from datetime import UTC, datetime

from conftest import DUMMY_FETCHED_AT, build_client
from merge_review.api.overview import fetch_source_statuses
from merge_review.models import FetchRun


def test_fetch_source_statuses_aggregate_openalex_stages() -> None:
    fetch = FetchRun(
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
    fetch = FetchRun(
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


def test_overview() -> None:
    client = build_client()

    response = client.get("/api/overview")

    assert response.status_code == 200
    assert response.json() == {
        "flagged_authors": 2,
        "affected_publications": 15,
        "total_authors": 2,
        "total_publications": 2,
        "queue_updated_at": "2026-08-21T00:00:00Z",
        "sources": [
            {
                "source": "semantic_scholar",
                "fetched_at": "2026-08-21T00:00:00Z",
                "state": "available",
                "note": "1 found",
            }
        ],
    }
