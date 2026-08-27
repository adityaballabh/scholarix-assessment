import pytest
from merge_review.models import IdentityCandidate, ValidationCase
from sqlalchemy import delete
from support import build_client


def test_case_list_filters_search_and_pagination() -> None:
    client = build_client()

    response = client.get("/api/cases", params={"status": "pending", "query": "dum"})
    paged = client.get("/api/cases", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == ["case-one"]
    assert [row["id"] for row in paged.json()] == ["case-two"]


def test_deferred_cases_keep_their_score_order_before_pagination() -> None:
    client = build_client(extra_cases=1)

    response = client.get("/api/cases")
    paged = client.get("/api/cases", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [
        "case-one",
        "case-two",
        "case-filler-0",
    ]
    assert paged.status_code == 200
    assert [row["id"] for row in paged.json()] == ["case-two"]


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ((90, 20, 1, 5, "deferred"), (80, 80, 3, 20, "pending"), ["case-one", "case-two"]),
        ((80, 70, 1, 5, "deferred"), (80, 60, 3, 20, "pending"), ["case-one", "case-two"]),
        ((80, 60, 3, 5, "deferred"), (80, 60, 2, 20, "pending"), ["case-one", "case-two"]),
        ((80, 60, 2, 20, "deferred"), (80, 60, 2, 10, "pending"), ["case-one", "case-two"]),
        ((80, 60, 2, 10, "needs_split"), (80, 60, 2, 10, "one_author"), ["case-two", "case-one"]),
        ((80, 60, 2, 10, "pending"), (80, 60, 2, 10, "pending"), ["case-one", "case-two"]),
        ((80, 0, 1, 10, "pending"), (80, None, 0, 10, "pending"), ["case-one", "case-two"]),
    ],
    ids=["score", "top-share", "candidates", "publications", "status", "case-id", "missing-share"],
)
def test_case_order_uses_column_tiebreakers_before_pagination(first, second, expected) -> None:
    client = build_client()
    with client.app.state.session_factory.begin() as session:
        session.execute(delete(IdentityCandidate))
        for case_id, values in [("case-one", first), ("case-two", second)]:
            score, share, candidates, publications, status = values
            review_case = session.get(ValidationCase, case_id)
            review_case.priority_score = score
            review_case.affected_count = publications
            review_case.status = status
            for position in range(candidates):
                session.add(
                    IdentityCandidate(
                        case_id=case_id,
                        position=position,
                        semantic_scholar_author_id=f"candidate-{position}",
                        matched_publication_count=1,
                        share=share if position == 0 else 0,
                    )
                )

    listed = client.get("/api/cases")
    paged = client.get("/api/cases", params={"limit": 1, "offset": 1})
    exported = client.get("/api/export")

    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == expected
    assert paged.status_code == 200
    assert [row["id"] for row in paged.json()] == expected[1:]
    assert exported.status_code == 200
    assert [row["id"] for row in exported.json()["cases"]] == expected


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
    assert response.json()["target"] == {
        "author_slug": "Dummy_Author",
        "author_name": "Dummy Author",
        "author_affiliation": "Dummy University",
        "openalex_id": "A123",
    }
    assert response.json()["detail"]["top_share"] == 60.0
    assert response.json()["detail"]["openalex_topics"] == ["Fetched Identity Topic"]
    assert response.json()["detail"]["candidate_ids"][0]["publications"] == [
        {"year": 2020, "title": "Dummy Publication"}
    ]
    assert "interpretation" not in response.json()["evidence"][0]
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
