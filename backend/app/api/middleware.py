"""Authentication middleware.

Turns an `Authorization: Bearer <supabase access token>` header into
`request.state.user_id`, which is what app/api/deps.py reads and what the
whole billing layer keys off.

Three behaviours, and the distinction between them matters:

  * **No token, auth not required** — anonymous. This is the self-hosted
    install: no accounts, no billing, everything works.
  * **A token that doesn't verify** — 401, always. Never silently
    downgraded to anonymous: on a hosted deployment that would turn an
    expired token into free renders.
  * **No token, auth required** — 401. `REQUIRE_AUTH=true` is what makes a
    public deployment safe; without it an unauthenticated caller would be
    treated as a self-hoster and billed nothing.
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.services import users
from app.services.rate_limit import TokenBucketLimiter
from app.services.supabase_auth import AuthError, SupabaseTokenVerifier

logger = logging.getLogger(__name__)

# Reachable without a token even when auth is required, so load balancers
# and uptime checks don't need credentials.
_PUBLIC_PATHS = {"/api/health", "/docs", "/openapi.json", "/redoc"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Throttle by user, falling back to client address for anonymous calls.

    Two budgets, because the costs differ by orders of magnitude: starting
    a render occupies a GPU for minutes, while reading a project is a
    single query. One shared limit would either leave renders unprotected
    or make ordinary browsing feel broken.

    Runs after authentication so it can key off the user — otherwise
    everyone behind one NAT would share a bucket.
    """

    def __init__(self, app, *, renders_per_hour: int, requests_per_minute: int) -> None:
        super().__init__(app)
        self._renders = TokenBucketLimiter(capacity=renders_per_hour, per_seconds=3600)
        self._general = TokenBucketLimiter(capacity=requests_per_minute, per_seconds=60)

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        user_id = getattr(request.state, "user_id", None)
        who = user_id or (request.client.host if request.client else "unknown")

        submitting_render = request.method == "POST" and request.url.path == "/api/projects"
        limiter = self._renders if submitting_render else self._general

        retry_after = limiter.check(who)
        if retry_after is not None:
            logger.info("Rate limited %s on %s", who, request.url.path)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        "Too many renders started. Try again shortly."
                        if submitting_render
                        else "Too many requests. Slow down."
                    )
                },
                headers={"Retry-After": str(max(1, int(retry_after)))},
            )
        return await call_next(request)


class SupabaseAuthMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        verifier: SupabaseTokenVerifier | None,
        require_auth: bool = False,
        signup_grant: int = 0,
    ) -> None:
        super().__init__(app)
        self._verifier = verifier
        self._require_auth = require_auth
        self._signup_grant = signup_grant

    async def dispatch(self, request: Request, call_next):
        request.state.user_id = None

        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        has_token = scheme.lower() == "bearer" and bool(token.strip())

        if has_token:
            if self._verifier is None:
                # A caller is presenting credentials to a deployment that
                # cannot check them. Refusing is the only safe answer.
                return _unauthorized("This deployment has no authentication configured")
            try:
                user = await self._verifier.verify(token.strip())
            except AuthError as exc:
                logger.info("Rejected token: %s", exc)
                return _unauthorized(str(exc))
            except Exception:  # noqa: BLE001 - JWKS fetch failures land here
                logger.exception("Could not verify token")
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Authentication service unavailable"},
                )

            request.state.user_id = user.id
            pool = getattr(request.app.state, "db_pool", None)
            if pool is not None:
                await users.ensure_user(
                    pool, user.id, user.email, signup_grant=self._signup_grant
                )

        elif self._require_auth and request.url.path not in _PUBLIC_PATHS:
            return _unauthorized("Not authenticated")

        return await call_next(request)


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )
