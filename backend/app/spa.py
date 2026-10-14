"""Serve the built React app with client-side routing fallback."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from starlette.responses import Response

NOT_BUILT_MESSAGE = (
    "The frontend has not been built. Run `npm run build` in frontend/, "
    "or use `python scripts/run.py`, which builds it for you."
)


def mount_spa(app: FastAPI, dist_dir: Path) -> None:
    """Register a catch-all GET route. Must be called after all API routes are added."""
    dist = dist_dir.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> Response:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        index = dist / "index.html"
        if not index.is_file():
            return PlainTextResponse(NOT_BUILT_MESSAGE, status_code=503)

        if full_path:
            candidate = (dist / full_path).resolve()
            if not candidate.is_relative_to(dist):
                raise HTTPException(status_code=404, detail="Not found")
            if candidate.is_file():
                return FileResponse(candidate)
            # Missing asset files are real 404s; anything else is a client-side route.
            if full_path.startswith("assets/"):
                raise HTTPException(status_code=404, detail="Not found")

        return FileResponse(index, headers={"Cache-Control": "no-cache"})
