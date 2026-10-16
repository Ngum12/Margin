"""Defence in depth for the optional public student hostname."""

from urllib.parse import unquote

from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send


class StudentHostMiddleware:
    def __init__(self, app: ASGIApp, hostname: str) -> None:
        self.app = app
        self.hostname = hostname.lower().strip()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self.hostname:
            host = Headers(scope=scope).get("host", "").split(":")[0].lower()
            if host == self.hostname:
                path = unquote(scope.get("path", "/"))
                safe = path == "/student" or path.startswith(
                    ("/student/", "/api/student/", "/assets/")
                )
                if not safe or ".." in path or "\\" in path:
                    await Response(status_code=404)(scope, receive, send)
                    return
        await self.app(scope, receive, send)
