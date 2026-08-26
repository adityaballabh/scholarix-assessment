from unittest.mock import patch

from conftest import build_client


def test_queue_settings_are_versioned_and_rebuild_recomputes_cases() -> None:
    client = build_client()

    current = client.get("/api/queue/settings")
    with patch(
        "merge_review.api.queue.rebuild_queue",
        return_value=1,
    ) as rebuild_queue:
        updated = client.put(
            "/api/queue/settings",
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
        fetch = client.post("/api/queue/rebuild")
    stale = client.put(
        "/api/queue/settings",
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
    assert fetch.status_code == 200
    assert fetch.json() == {
        "config_version": 2,
        "cases": 1,
    }
    assert rebuild_queue.call_count == 1
    assert stale.status_code == 409
