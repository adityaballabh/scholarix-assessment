from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

json_type = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DatasetSnapshot(Base):
    __tablename__ = "dataset_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dataset_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class ReviewSettings(Base):
    __tablename__ = "review_settings"
    __table_args__ = (
        CheckConstraint(
            "max_top_candidate_share >= 0 AND max_top_candidate_share <= 100",
            name="review_settings_valid_top_share",
        ),
    )

    dataset_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_snapshots.id", ondelete="CASCADE"), primary_key=True
    )
    max_top_candidate_share: Mapped[float] = mapped_column(Float)
    priority_weights: Mapped[dict] = mapped_column(json_type)
    version: Mapped[int] = mapped_column(Integer, default=1)
    queue_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class FetchRun(Base):
    __tablename__ = "fetch_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'complete', 'failed', 'abandoned')",
            name="fetch_runs_valid_status",
        ),
        Index("ix_fetch_runs_snapshot_status", "dataset_snapshot_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dataset_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_snapshots.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(16))
    current_source: Mapped[str | None] = mapped_column(String(64))
    source_progress: Mapped[dict] = mapped_column(json_type, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Author(Base):
    __tablename__ = "authors"
    __table_args__ = (
        UniqueConstraint("dataset_snapshot_id", "slug"),
        UniqueConstraint("dataset_snapshot_id", "source_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dataset_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_snapshots.id", ondelete="CASCADE")
    )
    source_id: Mapped[str] = mapped_column(String(64))
    slug: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(Text)
    affiliation: Mapped[str | None] = mapped_column(Text)
    orcid_id: Mapped[str | None] = mapped_column(String(32))
    profile: Mapped[dict] = mapped_column(json_type)


class PublicationRecord(Base):
    __tablename__ = "publication_records"
    __table_args__ = (
        CheckConstraint("position >= 0", name="publication_records_position_nonnegative"),
        UniqueConstraint("author_id", "position"),
        Index("ix_publication_records_normalized_doi", "normalized_doi"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("authors.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    normalized_doi: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    journal: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(SmallInteger)
    citations: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(json_type)


class BroadImpactRecord(Base):
    __tablename__ = "broad_impact_records"
    __table_args__ = (
        CheckConstraint("position >= 0", name="broad_impact_records_position_nonnegative"),
        UniqueConstraint("author_id", "position"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("authors.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    url: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64))
    relevance_score: Mapped[int | None] = mapped_column(Integer)
    snippet: Mapped[str | None] = mapped_column(Text)
    reasoning: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(json_type)


class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (
        CheckConstraint(
            "fetch_status IN ('success', 'pending', 'not_applicable', 'empty', "
            "'not_found', 'rate_limited', 'timeout', 'error')",
            name="valid_fetch_status",
        ),
        UniqueConstraint(
            "dataset_snapshot_id",
            "source",
            "entity_type",
            "entity_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dataset_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_snapshots.id", ondelete="CASCADE")
    )
    source: Mapped[str] = mapped_column(String(32))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_key: Mapped[str] = mapped_column(Text)
    source_record_id: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    fetch_status: Mapped[str] = mapped_column(String(32))
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    from_cache: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(json_type)


class ValidationCase(Base):
    __tablename__ = "validation_cases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'deferred', 'uncertain', 'one_author', 'needs_split')",
            name="validation_cases_valid_status",
        ),
        Index(
            "ix_validation_cases_snapshot_queue",
            "dataset_snapshot_id",
            "queue_eligible",
        ),
        UniqueConstraint("dataset_snapshot_id", "case_type", "author_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    dataset_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_snapshots.id", ondelete="CASCADE")
    )
    author_id: Mapped[UUID] = mapped_column(ForeignKey("authors.id", ondelete="CASCADE"))
    case_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    queue_eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    priority_score: Mapped[float] = mapped_column(Float)
    priority_components: Mapped[dict] = mapped_column(json_type)
    priority_config: Mapped[dict] = mapped_column(json_type)
    evidence_sha256: Mapped[str] = mapped_column(String(64))
    affected_count: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class CaseEvidence(Base):
    __tablename__ = "case_evidence"
    __table_args__ = (
        CheckConstraint(
            "value_state IN ('supports', 'conflict', 'missing', 'unverifiable')",
            name="case_evidence_valid_value_state",
        ),
        UniqueConstraint("case_id", "position"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[str] = mapped_column(ForeignKey("validation_cases.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(32))
    source_record_ids: Mapped[list] = mapped_column(json_type)
    source_refs: Mapped[list] = mapped_column(json_type)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetch_status: Mapped[str] = mapped_column(String(32))
    field: Mapped[str] = mapped_column(String(64))
    value: Mapped[str | None] = mapped_column(Text)
    value_state: Mapped[str] = mapped_column(String(32))
    interpretation: Mapped[str] = mapped_column(Text, default="")


class IdentityCandidate(Base):
    __tablename__ = "identity_candidates"
    __table_args__ = (
        UniqueConstraint("case_id", "semantic_scholar_author_id"),
        UniqueConstraint("case_id", "position"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[str] = mapped_column(ForeignKey("validation_cases.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    semantic_scholar_author_id: Mapped[str] = mapped_column(String(64))
    matched_publication_count: Mapped[int] = mapped_column(Integer)
    share: Mapped[float] = mapped_column(Float)
    first_year: Mapped[int | None] = mapped_column(SmallInteger)
    last_year: Mapped[int | None] = mapped_column(SmallInteger)


class IdentityCandidatePublication(Base):
    __tablename__ = "identity_candidate_publications"
    __table_args__ = (
        UniqueConstraint("identity_candidate_id", "position"),
        UniqueConstraint("identity_candidate_id", "doi"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    identity_candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_candidates.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    doi: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(SmallInteger)
    source_record_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_records.id", ondelete="CASCADE")
    )


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    __table_args__ = (
        CheckConstraint(
            "action IN ('reopen', 'confirm_one_author', 'flag_for_split', "
            "'mark_uncertain', 'defer', 'note')",
            name="review_decisions_valid_action",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[str] = mapped_column(ForeignKey("validation_cases.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text)
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    expected_case_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    decision_id: Mapped[UUID] = mapped_column(
        ForeignKey("review_decisions.id", ondelete="CASCADE"),
        unique=True,
    )
    case_id: Mapped[str] = mapped_column(ForeignKey("validation_cases.id", ondelete="CASCADE"))
    action_type: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(64))
    target_name: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    before_status: Mapped[str | None] = mapped_column(String(32))
    after_status: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
