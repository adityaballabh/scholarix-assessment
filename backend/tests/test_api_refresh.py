from collections import Counter
from unittest.mock import Mock, patch

from conftest import DUMMY_DOI, build_client


def test_refresh_doi_bypasses_cache_and_recomputes_cases() -> None:
    client = build_client()
    http_session = Mock()
    http_context = Mock()
    http_context.__enter__ = Mock(return_value=http_session)
    http_context.__exit__ = Mock(return_value=False)

    with (
        patch("merge_review.api.refresh.uncached_http_session", return_value=http_context),
        patch("merge_review.api.refresh.lock_snapshot_cases") as lock_cases,
        patch(
            "merge_review.api.refresh.refresh_publication_sources",
            return_value=Counter({"semantic_scholar:success": 1}),
        ) as refresh,
        patch(
            "merge_review.api.refresh.rebuild_queue",
            return_value=1,
        ) as fetch,
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
    assert fetch.call_count == 1


def test_refresh_author_and_source_scopes() -> None:
    client = build_client()
    http_session = Mock()
    http_context = Mock()
    http_context.__enter__ = Mock(return_value=http_session)
    http_context.__exit__ = Mock(return_value=False)

    with (
        patch("merge_review.api.refresh.uncached_http_session", return_value=http_context),
        patch("merge_review.api.refresh.lock_snapshot_cases") as lock_cases,
        patch(
            "merge_review.api.refresh.refresh_all_author_sources",
            return_value=Counter({"openalex_author:success": 1}),
        ) as refresh_author,
        patch(
            "merge_review.api.refresh.refresh_author_source",
            return_value=Counter({"semantic_scholar:success": 1}),
        ) as refresh_author_source,
        patch(
            "merge_review.api.refresh.refresh_source",
            return_value=Counter({"orcid:success": 1}),
        ) as refresh_source,
        patch(
            "merge_review.api.refresh.rebuild_queue",
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
    assert client.post("/api/refresh/authors/Dummy_Author/sources/orcid").status_code == 409
    assert client.post("/api/refresh/authors/Dummy_Author/sources/unknown").status_code == 422
    assert client.post("/api/refresh/sources/unknown").status_code == 422
