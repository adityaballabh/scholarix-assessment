import json

from conftest import build_client


def test_case_export_carries_the_whole_case_and_a_download_filename() -> None:
    client = build_client()

    response = client.get("/api/cases/case-one/export")
    document = response.json()
    exported_case = document["cases"][0]

    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="merge-review-evidence-dummy-author.json"'
    )
    assert document["case_count"] == 1
    assert document["filters"] is None
    assert document["dataset_snapshot"]["dataset_sha256"]
    assert document["queue_settings"]["version"] >= 1
    assert document["exported_at"]
    # The whole case, not a bare evidence array: without the target and the score the
    # evidence has no author attached to it and no reason for being flagged.
    assert exported_case["id"] == "case-one"
    assert exported_case["target"]["author_name"]
    assert exported_case["priority_score"] == 76.7
    assert exported_case["evidence"]
    assert exported_case["detail"]["candidate_ids"]
    assert client.get("/api/cases/missing/export").status_code == 404


def test_queue_export_selects_exactly_what_the_same_filters_list() -> None:
    client = build_client()

    filters = {"status": "pending", "query": "dum"}
    listed = client.get("/api/cases", params=filters)
    exported = client.get("/api/export", params=filters)
    document = exported.json()

    assert exported.status_code == 200
    assert [row["id"] for row in document["cases"]] == [row["id"] for row in listed.json()]
    assert document["case_count"] == len(listed.json())
    assert document["filters"] == {"scope": "active", "status": "pending", "query": "dum"}
    assert (
        'attachment; filename="merge-review-evidence-active-'
        in (exported.headers["content-disposition"])
    )
    assert client.get("/api/export", params={"status": "invalid"}).status_code == 422


def test_archived_scope_exports_the_archived_set() -> None:
    client = build_client(second_case_eligible=False)

    active = client.get("/api/export", params={"scope": "active"}).json()
    archived = client.get("/api/export", params={"scope": "archived"}).json()

    assert [row["id"] for row in active["cases"]] == ["case-one"]
    assert [row["id"] for row in archived["cases"]] == ["case-two"]
    assert archived["filters"]["scope"] == "archived"


def export_query_count(extra_cases: int) -> tuple[int, int]:
    query_log: list[str] = []
    client = build_client(query_log, extra_cases=extra_cases)
    query_log.clear()

    response = client.get("/api/export", params={"limit": 100})

    assert response.status_code == 200
    return response.json()["case_count"], len(query_log)


def test_export_batches_queries_instead_of_querying_per_case() -> None:
    small_cases, small_queries = export_query_count(0)
    large_cases, large_queries = export_query_count(20)

    assert (small_cases, large_cases) == (2, 22)
    assert small_queries == large_queries
    assert large_queries < 15


def test_export_is_unavailable_while_a_fetch_is_running() -> None:
    client = build_client(fetch_status="running")

    assert client.get("/api/export").status_code == 423
    assert client.get("/api/cases/case-one/export").status_code == 423


def test_export_is_readable_json_for_a_signed_out_reviewer() -> None:
    client = build_client()

    response = client.get("/api/export")

    assert response.status_code == 200
    assert json.loads(response.content)["cases"]
    # The file exists to be read, so it is indented rather than minified onto one line.
    assert response.text.startswith('{\n  "exported_at"')
    assert response.text.count("\n") > 50


def test_queue_export_is_not_capped_by_the_list_page_size() -> None:
    # The queue list stops at 50 by default because it is a screen. A file that stopped
    # there too would under-report the review state with nothing to say it had.
    client = build_client(extra_cases=60)

    listed = client.get("/api/cases", params={"limit": 200})
    default_page = client.get("/api/cases")
    exported = client.get("/api/export")

    assert len(listed.json()) == 62
    assert len(default_page.json()) == 50
    assert exported.json()["case_count"] == 62
    assert len(exported.json()["cases"]) == 62
