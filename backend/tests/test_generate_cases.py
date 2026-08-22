from datetime import UTC, datetime
from uuid import UUID, uuid4

from merge_review.generate_cases import (
    Candidate,
    case_id,
    generate_identity_cases,
    requires_identity_review,
)
from merge_review.models import (
    Author,
    Base,
    CaseEvidence,
    DatasetSnapshot,
    IdentityCandidate,
    IdentityCandidatePublication,
    PublicationRecord,
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
        second_counts = generate_identity_cases(session, snapshot_id)

    with factory() as session:
        review_case = session.get(ValidationCase, case_id("Dummy_Author"))
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

    assert first_counts == {"high": 0, "medium": 1}
    assert second_counts == first_counts
    assert review_case.priority == "medium"
    assert review_case.affected_count == 3
    assert [candidate.matched_publication_count for candidate in candidates] == [2, 1]
    assert [candidate.share for candidate in candidates] == [66.7, 33.3]
    assert publication_count == 3
    assert [row.value_state for row in evidence] == [
        "conflict",
        "supports",
        "supports",
        "supports",
    ]
