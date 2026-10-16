from fastapi import APIRouter

from app.api import ai, auth, classes, exams, hardware, health, results, review, scans, users

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
