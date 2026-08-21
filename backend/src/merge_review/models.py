from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
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


class DatasetSnapshot(Base):
    __tablename__ = "dataset_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dataset_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


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
        CheckConstraint("position >= 0", name="position_nonnegative"),
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
        CheckConstraint("position >= 0", name="position_nonnegative"),
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
            "fetch_status IN ('success', 'pending', 'never_attempted', 'empty', "
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
