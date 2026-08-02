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
from app.services.supabase_auth import AuthError, SupabaseTokenVerifier

logger = logging.getLogger(__name__)

# Reachable without a token even when auth is required, so load balancers
# and uptime checks don't need credentials.
_PUBLIC_PATHS = {"/api/health", "/docs", "/openapi.json", "/redoc"}


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
