from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID, uuid4

from merge_review.generate_cases import (
    Candidate,
    IdentityCaseData,
    PriorityMaximums,
    case_id,
    generate_identity_cases,
    institutions_match,
    normalized_component,
    normalized_institution,
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
    ValidationCase,
)
from merge_review.source_records import FetchStatus
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


def test_snapshot_max_normalization() -> None:
    assert normalized_component(25, 50) == 50.0
    assert normalized_component(50, 50) == 100.0
    assert normalized_component(0, 0) == 0.0


def test_institution_normalization_ignores_at() -> None:
    assert normalized_institution(
        "University of Illinois Urbana-Champaign"
    ) == normalized_institution("University of Illinois at Urbana-Champaign")
    assert normalized_institution("Research and Development Center") == (
        normalized_institution("The Research Development Center")
    )


def test_institution_matching_does_not_infer_parent_system() -> None:
    assert not institutions_match(
        "University of Illinois Urbana-Champaign",
        "University of Illinois System",
    )
    assert not institutions_match(
        "University of Illinois Urbana-Champaign",
        "Argonne National Laboratory",
    )


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


def test_generate_identity_cases() -> None:
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

    with factory.begin() as session:
        first_counts = generate_identity_cases(session, snapshot_id)
    with factory.begin() as session:
        semantic_scholar_record = session.scalar(
            select(SourceRecord).where(SourceRecord.source == "semantic_scholar")
        )
        semantic_scholar_record.fetched_at = semantic_scholar_record.fetched_at.replace(hour=1)
        second_counts = generate_identity_cases(session, snapshot_id)

    with factory.begin() as session:
        settings = session.get(ReviewSettings, snapshot_id)
        settings.priority_weights = {
            "publication_impact": 1,
            "fragmentation": 0,
            "cluster_ambiguity": 0,
        }
        generate_identity_cases(session, snapshot_id)

    with factory.begin() as session:
        review_case = session.get(ValidationCase, case_id(snapshot_id, "Dummy_Author"))
        settings = session.get(ReviewSettings, snapshot_id)
        decision_id = uuid4()
        session.add(
            ReviewDecision(
                id=decision_id,
                case_id=review_case.id,
                action="note",
                note="Keep this review context",
                reviewer_id="dummy",
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
        settings.max_top_candidate_share = 50
        archived_counts = generate_identity_cases(session, snapshot_id)

    with factory() as session:
        archived_case = session.get(ValidationCase, case_id(snapshot_id, "Dummy_Author"))
        assert archived_case.queue_eligible is False
        assert session.scalar(select(func.count(CaseEvidence.id))) == 4
        assert session.scalar(select(func.count(ReviewDecision.id))) == 1
        assert session.scalar(select(func.count(ActivityEvent.id))) == 1

    with factory.begin() as session:
        settings = session.get(ReviewSettings, snapshot_id)
        settings.max_top_candidate_share = 75
        reactivated_counts = generate_identity_cases(session, snapshot_id)

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
        decision_count = session.scalar(select(func.count(ReviewDecision.id)))
        activity_count = session.scalar(select(func.count(ActivityEvent.id)))

    assert first_counts == 1
    assert second_counts == first_counts
    assert review_case.priority_score == 100.0
    assert review_case.queue_eligible is True
    assert review_case.version == 5
    assert review_case.priority_components == {
        "publication_impact": {"value": 3.0, "snapshot_max": 3, "score": 100.0},
        "fragmentation": {"value": 33.3, "snapshot_max": 33.3, "score": 100.0},
        "cluster_ambiguity": {"value": 2.0, "snapshot_max": 2, "score": 100.0},
    }
    assert review_case.affected_count == 3
    assert [candidate.matched_publication_count for candidate in candidates] == [2, 1]
    assert [candidate.share for candidate in candidates] == [66.7, 33.3]
    assert publication_count == 3
    assert decision_count == 1
    assert activity_count == 1
    assert archived_counts == 0
    assert reactivated_counts == 1
    assert [row.value_state for row in evidence] == [
        "conflict",
        "supports",
        "supports",
        "supports",
    ]
