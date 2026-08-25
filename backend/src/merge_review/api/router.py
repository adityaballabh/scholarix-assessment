from fastapi import APIRouter, Depends

from merge_review.api import activity, auth, cases, exports, fetches, overview, queue, refresh
from merge_review.security import authenticate_writes

router = APIRouter(prefix="/api")
protected_router = APIRouter(dependencies=[Depends(authenticate_writes)])
protected_router.include_router(queue.router)
protected_router.include_router(refresh.router)
protected_router.include_router(cases.router)
protected_router.include_router(exports.router)
protected_router.include_router(activity.router)
protected_router.include_router(overview.router)
router.include_router(auth.router)
# Fetch routes carry their own guard: it has to exempt the bootstrap fetch, which the
# blanket by-method rule cannot express. See api/fetches.authenticate_fetch.
router.include_router(fetches.router)
router.include_router(protected_router)
