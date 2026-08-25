from fastapi import APIRouter

from merge_review.api import activity, cases, fetches, overview, queue, refresh

router = APIRouter(prefix="/api")
router.include_router(fetches.router)
router.include_router(queue.router)
router.include_router(refresh.router)
router.include_router(cases.router)
router.include_router(activity.router)
router.include_router(overview.router)
