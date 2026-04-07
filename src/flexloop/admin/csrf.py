"""CSRF protection for admin endpoints via Origin header check.

For state-changing methods on /api/admin/* paths, the request's Origin header
must match one of the configured allowed origins. GETs and non-admin routes
are not checked.

The login endpoint (/api/admin/auth/login) is EXEMPT because:
  1. It's unauthenticated — there's no existing auth to steal via CSRF
  2. Fresh VPS deployments need first-login to work before the admin can
     configure allowed origins via the UI (chicken-and-egg problem otherwise)

Combined with SameSite=Strict on the session cookie (set in auth router),
this gives belt-and-braces CSRF protection without needing signed tokens.
"""
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
PROTECTED_PREFIX = "/api/admin"
CSRF_EXEMPT_PATHS = {"/api/admin/auth/login"}


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces a whitelist of Origin headers on admin writes.

    The allowed_origins_getter is a callable (not a static list) so that later
    phases can hot-reload the allowed origins from app_settings without a
    server restart.
    """

    def __init__(
        self,
        app,
        allowed_origins_getter: Callable[[], list[str]],
    ):
        super().__init__(app)
        self._get_allowed = allowed_origins_getter

    async def dispatch(self, request: Request, call_next):
        # Skip if this isn't a protected path
        if not request.url.path.startswith(PROTECTED_PREFIX):
            return await call_next(request)
        # Skip GET/HEAD/OPTIONS — they're idempotent and don't need CSRF
        if request.method not in STATE_CHANGING_METHODS:
            return await call_next(request)
        # Skip exempt paths (login — see module docstring)
        if request.url.path in CSRF_EXEMPT_PATHS:
            return await call_next(request)

        origin = request.headers.get("origin")
        if origin is None or origin not in self._get_allowed():
            return JSONResponse(
                status_code=403,
                content={"detail": "origin check failed"},
            )
        return await call_next(request)
