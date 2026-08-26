from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from merge_review.cases.evidence import orcid_evidence
from merge_review.cases.generate import (
    Candidate,
    IdentityCaseData,
    PriorityMaximums,
    case_id,
    generate_identity_cases,
    normalized_component,
    requires_identity_review,
    score_values,
)
from merge_review.models import (
    ActivityEvent,
    Author,
    Base,
    CaseEvidence,
    DatasetSnapshot,
    IdentityCandidate,
    IdentityCandidatePublication,
    PublicationRecord,
    ReviewDecision,
    ReviewSettings,
    SourceRecord,
    User,
    ValidationCase,
)
from merge_review.sources.common import FetchStatus
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

DUMMY_SNAPSHOT_HASH = "a" * 64
DUMMY_AUTHOR_ID = "A123"
DUMMY_AUTHOR_NAME = "Dummy Author"
DUMMY_ORCID = "0000-0000-0000-0000"
DUMMY_FETCHED_AT = datetime(2026, 8, 21, tzinfo=UTC)
DUMMY_DOIS = ("10.123/first", "10.123/second", "10.123/third")
DUMMY_INSTITUTION = "Dummy University"
DUMMY_CANDIDATE_IDS = ("candidateID1", "candidateID2")


def test_identity_review_threshold() -> None:
    at_threshold = Candidate("candidateID", (), 75.0, None, None)
    above_threshold = Candidate("candidateID", (), 75.1, None, None)

    assert requires_identity_review([at_threshold]) is True
    assert requires_identity_review([above_threshold]) is False


def test_case_ids_are_snapshot_scoped() -> None:
    first_snapshot_id = uuid4()
    second_snapshot_id = uuid4()

    assert case_id(first_snapshot_id, "Dummy_Author") == case_id(
        first_snapshot_id,
        "Dummy_Author",
    )
    assert case_id(first_snapshot_id, "Dummy_Author") != case_id(
        second_snapshot_id,
        "Dummy_Author",
    )


def test_component_score_is_zero_when_the_snapshot_has_no_maximum() -> None:
    assert normalized_component(0, 0) == 0.0
    assert normalized_component(3, 0) == 0.0


def test_configured_weights_change_score() -> None:
    author = Author(
        source_id=DUMMY_AUTHOR_ID,
        slug="Dummy_Author",
        name=DUMMY_AUTHOR_NAME,
        profile={},
    )
    candidates = [
        Candidate("candidateID1", (), 50.0, None, None),
        Candidate("candidateID2", (), 50.0, None, None),
    ]
    data = IdentityCaseData(author, candidates, [Mock()] * 5, {})
    maximums = PriorityMaximums(10, 50, 4)

    score, _, config = score_values(
        data,
        maximums,
        {"publication_impact": 0, "fragmentation": 1, "cluster_ambiguity": 0},
    )

    assert score == 100.0
    assert config["weights"] == {
        "publication_impact": 0.0,
        "fragmentation": 1.0,
        "cluster_ambiguity": 0.0,
    }


def source_result(
    snapshot_id: UUID,
    source: str,
    entity_type: str,
    entity_key: str,
    payload: dict,
) -> SourceRecord:
    return SourceRecord(
        id=uuid4(),
        dataset_snapshot_id=snapshot_id,
        source=source,
        entity_type=entity_type,
        entity_key=entity_key,
        source_record_id=entity_key,
        url="https://example.com",
        fetch_status=FetchStatus.SUCCESS,
        http_status=200,
        fetched_at=DUMMY_FETCHED_AT,
        from_cache=True,
        payload=payload,
    )


@pytest.fixture
def snapshot() -> tuple[sessionmaker, UUID]:
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    snapshot_id = uuid4()
    author_id = uuid4()

    with factory.begin() as session:
        session.add(DatasetSnapshot(id=snapshot_id, dataset_sha256=DUMMY_SNAPSHOT_HASH))
        session.flush()
        session.add(
            Author(
                id=author_id,
                dataset_snapshot_id=snapshot_id,
                source_id=DUMMY_AUTHOR_ID,
                slug="Dummy_Author",
                name=DUMMY_AUTHOR_NAME,
                affiliation=DUMMY_INSTITUTION,
                orcid_id=DUMMY_ORCID,
                profile={"topics": ["Identity resolution"]},
            )
        )
        session.add_all(
            PublicationRecord(
                author_id=author_id,
                position=position,
                normalized_doi=doi,
                title=f"Dummy Publication {position + 1}",
                year=2020 + position,
                source="openalex",
                payload={},
            )
            for position, doi in enumerate(DUMMY_DOIS)
        )
        session.add(
            source_result(
                snapshot_id,
                "openalex",
                "author",
                DUMMY_AUTHOR_ID,
                {
                    "display_name": DUMMY_AUTHOR_NAME,
                    "last_known_institutions": [{"display_name": DUMMY_INSTITUTION}],
                },
            )
        )
        session.add(
            source_result(
                snapshot_id,
                "orcid",
                "author",
                DUMMY_ORCID,
                {
                    "activities-summary": {
                        "employments": {
                            "affiliation-group": [
                                {
                                    "summaries": [
                                        {
                                            "employment-summary": {
                                                "organization": {"name": DUMMY_INSTITUTION}
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                },
            )
        )
        for position, doi in enumerate(DUMMY_DOIS):
            candidate_id = DUMMY_CANDIDATE_IDS[0] if position != 1 else DUMMY_CANDIDATE_IDS[1]
            session.add(
                source_result(
                    snapshot_id,
                    "semantic_scholar",
                    "publication",
                    doi,
                    {
                        "paperId": f"paperID{position + 1}",
                        "title": f"Dummy Publication {position + 1}",
                        "year": 2020 + position,
                        "authors": [{"authorId": candidate_id, "name": DUMMY_AUTHOR_NAME}],
                    },
                )
            )
    return factory, snapshot_id


def record_review(factory: sessionmaker, review_case_id: str) -> None:
    with factory.begin() as session:
        review_case = session.get(ValidationCase, review_case_id)
        reviewer_id = uuid4()
        session.add(
            User(
                id=reviewer_id,
                username="dummy",
                display_name=DUMMY_AUTHOR_NAME,
                password_hash="dummy",
            )
        )
        session.flush()
        decision_id = uuid4()
        session.add(
            ReviewDecision(
                id=decision_id,
                case_id=review_case.id,
                action="note",
                note="Keep this review context",
                reviewer_id=reviewer_id,
                expected_case_version=review_case.version,
                created_at=DUMMY_FETCHED_AT,
            )
        )
        session.flush()
        session.add(
            ActivityEvent(
                decision_id=decision_id,
                case_id=review_case.id,
                action_type="note",
                actor="dummy",
                target_name=DUMMY_AUTHOR_NAME,
                note="Keep this review context",
                before_status="pending",
                after_status="pending",
                created_at=DUMMY_FETCHED_AT,
            )
        )
        review_case.version += 1


def set_top_candidate_share(factory: sessionmaker, snapshot_id: UUID, share: float) -> int:
    with factory.begin() as session:
        session.get(ReviewSettings, snapshot_id).max_top_candidate_share = share
        return generate_identity_cases(session, snapshot_id)


def test_identity_case_is_built_from_every_source(snapshot) -> None:
    factory, snapshot_id = snapshot

    with factory.begin() as session:
        counts = generate_identity_cases(session, snapshot_id)

    with factory() as session:
        review_case = session.get(ValidationCase, case_id(snapshot_id, "Dummy_Author"))
        candidates = session.scalars(
            select(IdentityCandidate)
            .where(IdentityCandidate.case_id == review_case.id)
            .order_by(IdentityCandidate.position)
        ).all()
        evidence = session.scalars(
            select(CaseEvidence)
            .where(CaseEvidence.case_id == review_case.id)
            .order_by(CaseEvidence.position)
        ).all()
        publication_count = session.scalar(select(func.count(IdentityCandidatePublication.id)))

    assert counts == 1
    assert review_case.queue_eligible is True
    assert review_case.affected_count == 3
    assert review_case.priority_score == 100.0
    assert review_case.priority_components == {
        "publication_impact": {"value": 3.0, "snapshot_max": 3, "score": 100.0},
        "fragmentation": {"value": 33.3, "snapshot_max": 33.3, "score": 100.0},
        "cluster_ambiguity": {"value": 2.0, "snapshot_max": 2, "score": 100.0},
    }
    assert [candidate.matched_publication_count for candidate in candidates] == [2, 1]
    assert [candidate.share for candidate in candidates] == [66.7, 33.3]
    assert publication_count == 3
    assert [row.value_state for row in evidence] == [
        "conflict",
        "supports",
        "supports",
        "supports",
    ]
    assert [row.source for row in evidence] == [
        "semantic_scholar",
        "openalex",
        "openalex",
        "orcid",
    ]
    assert [row.field for row in evidence] == [
        "author_identity",
        "canonical_name",
        "affiliation",
        "affiliation",
    ]
    assert evidence[0].source_refs == [
        {"entity_type": "author", "id": DUMMY_CANDIDATE_IDS[0]},
        {"entity_type": "author", "id": DUMMY_CANDIDATE_IDS[1]},
    ]
    assert evidence[0].value == "2 S2 IDs for publications matching this name"
    assert [row.fetch_status for row in evidence] == [FetchStatus.SUCCESS] * 4
    assert [row.fetched_at for row in evidence] == [DUMMY_FETCHED_AT.replace(tzinfo=None)] * 4
    assert evidence[1].value == DUMMY_AUTHOR_NAME
    assert evidence[2].value == DUMMY_INSTITUTION
    assert evidence[3].value == DUMMY_INSTITUTION


@pytest.mark.parametrize(
    ("orcid_id", "fetch_status", "institution", "expected_state", "expected_fetch_status"),
    [
        (DUMMY_ORCID, FetchStatus.SUCCESS, DUMMY_INSTITUTION, "supports", FetchStatus.SUCCESS),
        (DUMMY_ORCID, FetchStatus.SUCCESS, "Other University", "conflict", FetchStatus.SUCCESS),
        (DUMMY_ORCID, FetchStatus.ERROR, DUMMY_INSTITUTION, "unverifiable", FetchStatus.ERROR),
        (None, FetchStatus.SUCCESS, DUMMY_INSTITUTION, "missing", FetchStatus.NOT_APPLICABLE),
    ],
)
def test_orcid_evidence_states(
    snapshot,
    orcid_id,
    fetch_status,
    institution,
    expected_state,
    expected_fetch_status,
) -> None:
    factory, _ = snapshot
    with factory.begin() as session:
        author = session.scalar(select(Author))
        record = session.scalar(select(SourceRecord).where(SourceRecord.source == "orcid"))
        author.orcid_id = orcid_id
        record.fetch_status = fetch_status
        record.payload = {
            "activities-summary": {
                "employments": {
                    "affiliation-group": [
                        {
                            "summaries": [
                                {"employment-summary": {"organization": {"name": institution}}}
                            ]
                        }
                    ]
                }
            }
        }
        row = orcid_evidence(session, author)

    assert row["source_refs"] == (
        [{"entity_type": "author", "id": DUMMY_ORCID}] if orcid_id else []
    )
    assert row["fetch_status"] == expected_fetch_status
    assert row["value_state"] == expected_state
    expected_value = institution if expected_state in {"supports", "conflict"} else None
    assert row["value"] == expected_value


def test_regenerating_after_a_refetch_updates_the_case_in_place(snapshot) -> None:
    factory, snapshot_id = snapshot

    with factory.begin() as session:
        generate_identity_cases(session, snapshot_id)
        original_version = session.get(
            ValidationCase,
            case_id(snapshot_id, "Dummy_Author"),
        ).version

    with factory.begin() as session:
        record = session.scalar(
            select(SourceRecord).where(SourceRecord.source == "semantic_scholar")
        )
        record.fetched_at = record.fetched_at.replace(hour=1)
        counts = generate_identity_cases(session, snapshot_id)

    with factory() as session:
        review_case = session.get(ValidationCase, case_id(snapshot_id, "Dummy_Author"))
        case_count = session.scalar(select(func.count(ValidationCase.id)))
        evidence_count = session.scalar(select(func.count(CaseEvidence.id)))

    assert counts == 1
    assert review_case.version == original_version
    assert case_count == 1
    assert evidence_count == 4


def test_reweighting_updates_the_existing_case(snapshot) -> None:
    factory, snapshot_id = snapshot

    with factory.begin() as session:
        generate_identity_cases(session, snapshot_id)
        review_case = session.get(ValidationCase, case_id(snapshot_id, "Dummy_Author"))
        original_version = review_case.version

    with factory.begin() as session:
        settings = session.get(ReviewSettings, snapshot_id)
        settings.priority_weights = {
            "publication_impact": 1,
            "fragmentation": 0,
            "cluster_ambiguity": 0,
        }
        generate_identity_cases(session, snapshot_id)

    with factory() as session:
        review_case = session.get(ValidationCase, case_id(snapshot_id, "Dummy_Author"))

    assert review_case.priority_config["weights"] == {
        "publication_impact": 1,
        "fragmentation": 0,
        "cluster_ambiguity": 0,
    }
    assert review_case.version > original_version


def test_a_case_below_the_share_threshold_is_archived_not_deleted(snapshot) -> None:
    factory, snapshot_id = snapshot

    with factory.begin() as session:
        generate_identity_cases(session, snapshot_id)
    record_review(factory, case_id(snapshot_id, "Dummy_Author"))

    counts = set_top_candidate_share(factory, snapshot_id, 50)

    with factory() as session:
        review_case = session.get(ValidationCase, case_id(snapshot_id, "Dummy_Author"))
        evidence_count = session.scalar(select(func.count(CaseEvidence.id)))
        decision_count = session.scalar(select(func.count(ReviewDecision.id)))
        activity_count = session.scalar(select(func.count(ActivityEvent.id)))

    assert counts == 0
    assert review_case.queue_eligible is False
    assert evidence_count == 4
    assert decision_count == 1
    assert activity_count == 1


def test_an_archived_case_returns_to_the_queue_when_it_qualifies_again(snapshot) -> None:
    factory, snapshot_id = snapshot

    with factory.begin() as session:
        generate_identity_cases(session, snapshot_id)
    record_review(factory, case_id(snapshot_id, "Dummy_Author"))
    set_top_candidate_share(factory, snapshot_id, 50)

    counts = set_top_candidate_share(factory, snapshot_id, 75)

    with factory() as session:
        review_case = session.get(ValidationCase, case_id(snapshot_id, "Dummy_Author"))
        decision_count = session.scalar(select(func.count(ReviewDecision.id)))

    assert counts == 1
    assert review_case.queue_eligible is True
    assert decision_count == 1
