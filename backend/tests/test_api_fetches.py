from unittest.mock import patch
from uuid import uuid4

from support import DUMMY_FETCHED_AT, build_client


def test_fetch_run_blocks_application_requests() -> None:
    client = build_client()

    with patch("merge_review.api.fetches.run_fetch") as run_fetch:
        started = client.post("/api/fetches")

    current = client.get("/api/fetches/current")
    blocked = client.get("/api/cases")

    assert started.status_code == 202
    assert started.json()["status"] == "queued"
    assert current.json()["id"] == started.json()["id"]
    assert blocked.status_code == 423
    assert run_fetch.call_count == 1


def test_fetch_status_includes_last_successful_run() -> None:
    client = build_client(completed_fetch_at=DUMMY_FETCHED_AT)

    response = client.get("/api/fetches/current")

    assert response.status_code == 200
    assert response.json()["status"] == "complete"
    assert response.json()["last_completed_at"] == "2026-08-21T00:00:00Z"


def test_only_a_failed_fetch_can_be_abandoned() -> None:
    client = build_client()

    fetch_id = client.get("/api/fetches/current").json()["id"]

    complete = client.post(f"/api/fetches/{fetch_id}/abandon")

    assert complete.status_code == 409
    assert complete.json()["detail"] == "Only a failed fetch can be abandoned"
    assert client.post(f"/api/fetches/{uuid4()}/abandon").status_code == 404


def test_abandoning_a_failed_fetch_unblocks_a_new_one() -> None:
    client = build_client(fetch_status="failed")
    fetch_id = client.get("/api/fetches/current").json()["id"]

    abandoned = client.post(f"/api/fetches/{fetch_id}/abandon")
    with patch("merge_review.api.fetches.run_fetch"):
        restarted = client.post("/api/fetches")

    assert abandoned.status_code == 200
    assert abandoned.json()["status"] == "abandoned"
    assert restarted.status_code == 202
    assert restarted.json()["id"] != fetch_id
