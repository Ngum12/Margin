"""Turn domain and validation errors into the API error shape: {code, detail, issues}."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.errors import DomainError
from app.schemas.common import ErrorOut, IssueOut

logger = logging.getLogger(__name__)


def _response(status_code: int, body: ErrorOut) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


async def _domain_error(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):  # pragma: no cover - registered for DomainError only
        raise exc
    return _response(
        exc.status_code,
        ErrorOut(code=exc.code, detail=exc.message, issues=[IssueOut.of(i) for i in exc.issues]),
    )


async def _request_validation_error(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover
        raise exc
    # Report where and what kind of problem, never echo the submitted values (may be passwords).
    issues = [
        IssueOut(
            code=f"request.{err.get('type', 'invalid')}", path=list(err.get("loc", ())), params={}
        )
        for err in exc.errors()
    ]
    return _response(422, ErrorOut(code="request.invalid", detail="Invalid request", issues=issues))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _request_validation_error)
