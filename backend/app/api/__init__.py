from fastapi import APIRouter

from app.api import (
    ai,
    answer_sheets,
    auth,
    classes,
    exams,
    hardware,
    health,
    results,
    review,
    scans,
    scheme_documents,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(classes.router)
api_router.include_router(exams.router)
api_router.include_router(scans.router)
api_router.include_router(ai.router)
api_router.include_router(review.router)
api_router.include_router(results.router)

api_router.include_router(hardware.router)

api_router.include_router(answer_sheets.router)

api_router.include_router(scheme_documents.router)
