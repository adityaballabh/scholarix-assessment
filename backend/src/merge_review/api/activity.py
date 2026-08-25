from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from merge_review.api.common import ensure_fetch_idle, utc_datetime
from merge_review.database import get_session
from merge_review.models import ActivityEvent
from merge_review.schemas import ActivityEventResponse

router = APIRouter()


def activity_response(event: ActivityEvent) -> ActivityEventResponse:
    return ActivityEventResponse(
        id=str(event.id),
        case_id=event.case_id,
        action_type=event.action_type,
        actor=event.actor,
        created_at=utc_datetime(event.created_at),
        target_name=event.target_name,
        note=event.note,
        before=event.before_status,
        after=event.after_status,
    )


@router.get("/activity", response_model=list[ActivityEventResponse])
def list_activity(session: Session = Depends(get_session)) -> list[ActivityEventResponse]:
    ensure_fetch_idle(session)
    events = session.scalars(
        select(ActivityEvent).order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
    )
    return [activity_response(event) for event in events]
