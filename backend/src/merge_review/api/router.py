from fastapi import APIRouter, Depends

from merge_review.api import activity, auth, cases, exports, fetches, overview, queue, refresh
from merge_review.security import authenticate_writes

router = APIRouter(prefix="/api")
write_guarded_router = APIRouter(dependencies=[Depends(authenticate_writes)])
write_guarded_router.include_router(queue.router)
write_guarded_router.include_router(refresh.router)
write_guarded_router.include_router(cases.router)
write_guarded_router.include_router(exports.router)
write_guarded_router.include_router(activity.router)
write_guarded_router.include_router(overview.router)
router.include_router(auth.router)
router.include_router(fetches.router)
router.include_router(fetches.abandon_router)
router.include_router(write_guarded_router)
