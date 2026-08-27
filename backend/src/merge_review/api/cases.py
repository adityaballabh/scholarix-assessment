from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from merge_review.api.activity import activity_response
from merge_review.api.case_read import case_responses, filtered_case_rows
from merge_review.api.common import lock_current_snapshot_for_read
from merge_review.database import get_session
from merge_review.models import (
    ActivityEvent,
    Author,
    ReviewDecision,
    User,
    ValidationCase,
)
from merge_review.schemas import (
    ActivityEventResponse,
    DecisionRequest,
    QueueScope,
    ValidationCaseResponse,
)
from merge_review.security import get_current_user

router = APIRouter()
ACTION_STATUS = {
    "reopen": "pending",
    "confirm_one_author": "one_author",
    "flag_for_split": "needs_split",
    "mark_uncertain": "uncertain",
    "defer": "deferred",
}


@router.get("/cases", response_model=list[ValidationCaseResponse])
def list_cases(
    status: str | None = None,
    scope: QueueScope = "active",
    query: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[ValidationCaseResponse]:
    snapshot = lock_current_snapshot_for_read(session)
    if snapshot is None:
        return []
    rows = filtered_case_rows(
        session,
        snapshot_id=snapshot.id,
        status=status,
        scope=scope,
        query=query,
        limit=limit,
        offset=offset,
    )
    return case_responses(session, rows)


@router.get("/cases/{case_id}", response_model=ValidationCaseResponse)
def get_case(case_id: str, session: Session = Depends(get_session)) -> ValidationCaseResponse:
    snapshot = lock_current_snapshot_for_read(session)
    if snapshot is None:
        raise HTTPException(404, detail="Case not found")
    row = session.execute(
        select(ValidationCase, Author)
        .join(Author)
        .where(
            ValidationCase.id == case_id,
            ValidationCase.dataset_snapshot_id == snapshot.id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, detail="Case not found")
    return case_responses(session, [(row[0], row[1])])[0]


@router.post("/cases/{case_id}/decisions", response_model=ActivityEventResponse)
def post_decision(
    case_id: str,
    request: DecisionRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ActivityEventResponse:
    snapshot = lock_current_snapshot_for_read(session)
    if snapshot is None:
        raise HTTPException(404, detail="Case not found")
    review_case = session.scalar(
        select(ValidationCase)
        .where(
            ValidationCase.id == case_id,
            ValidationCase.dataset_snapshot_id == snapshot.id,
        )
        .with_for_update()
    )
    if review_case is None:
        raise HTTPException(404, detail="Case not found")
    if review_case.version != request.expected_version:
        raise HTTPException(409, detail="Case changed after it was loaded")
    if request.action == "note" and request.note is None:
        raise HTTPException(422, detail="A note is required")

    before = review_case.status
    after = before if request.action == "note" else ACTION_STATUS[request.action]
    if request.action != "note" and after == before:
        raise HTTPException(409, detail="Case is already in that state")

    author = session.get(Author, review_case.author_id)
    if author is None:
        raise RuntimeError(f"Case {review_case.id} has no author")
    created_at = datetime.now(UTC)
    decision_id = uuid4()
    event = ActivityEvent(
        id=uuid4(),
        decision_id=decision_id,
        case_id=review_case.id,
        action_type=request.action,
        actor=current_user.display_name,
        target_name=author.name,
        note=request.note,
        before_status=before,
        after_status=after,
        created_at=created_at,
    )
    decision = ReviewDecision(
        id=decision_id,
        case_id=review_case.id,
        action=request.action,
        note=request.note,
        reviewer_id=current_user.id,
        expected_case_version=request.expected_version,
        created_at=created_at,
    )
    session.add(decision)
    session.flush()
    session.add(event)
    review_case.status = after
    review_case.version += 1
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    return activity_response(event)
