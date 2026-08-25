from conftest import build_client


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
