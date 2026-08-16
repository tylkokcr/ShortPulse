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
import re

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

# Callers that legitimately have no user behind them.
#
# Stripe is the one that matters. It calls the webhook with a signed
# `Stripe-Signature` header and no bearer token — it has no user to
# authenticate as — so with REQUIRE_AUTH on it was answered 401 and the
# handler that grants the credits never ran. The purchase succeeded, the
# money was taken, and nothing was delivered. Nothing logged an error
# either: from the API's side a 401 is a normal answer.
#
# Exempting it gives nothing away. The route authenticates the request
# itself, by verifying the signature against STRIPE_WEBHOOK_SECRET, and
# rejects an unsigned or wrongly-signed payload with a 400 — which is
# strictly stronger than a bearer token here, since the token would prove
# only that *somebody* was logged in.
#
# Separate from _PUBLIC_PATHS because these stay rate-limited. Skipping
# authentication is not a reason to skip throttling, and Stripe's real
# traffic is orders of magnitude below the limit.
#
# The price list is here for a different reason: a visitor deciding
# whether to sign up has no account yet, and answering them 401 made the
# landing page quote its hardcoded USD fallback instead of what the
# deployment actually charges. It exposes nothing — it is the price list.
#
# Visual modes are there for the same reason as the price list, and for
# one more: the picker's fallback when the call fails is to offer
# everything, so a 401 here doesn't hide the modes — it puts back exactly
# the options this install cannot render.
#
# The catalog samples are the third and fourth callers found in this
# position, and the comment that shipped with the voice preview said the
# quiet part out loud: "it feeds an <audio> element, which can't carry an
# Authorization header — and the preview endpoint needs none". True when
# it was written, on an install with no accounts; false from the day
# REQUIRE_AUTH went on, and nothing announced the change. Auditioning a
# voice has been impossible on this service ever since, which is exactly
# as visible as a button that does nothing.
#
# Safe on the same grounds as the price list. The voice preview
# synthesizes one fixed line for one catalog voice — an arbitrary id is
# refused, because it reaches huggingface_hub as a repo path — caches the
# result and serialises generation behind a lock, so the work an anonymous
# caller can cause is bounded by the size of the catalog, once. The music
# preview serves a file resolved by track_path_for, which rejects anything
# escaping the music directory.
_UNAUTHENTICATED_PATHS = _PUBLIC_PATHS | {
    "/api/credits/webhook",
    "/api/credits/packs",
    "/api/visual-modes",
    "/api/voices/preview",
    "/api/music/preview",
}

# The media bytes, which carry their own credential in the URL.
#
# The same shape of bug as the webhook above, and found the same way — by
# a purchase that worked and a product that didn't arrive. A <video>
# element cannot send an Authorization header, and neither can a download
# navigation, so /media-url mints a short-lived token signed with
# MEDIA_URL_SECRET and puts it in the query string. With REQUIRE_AUTH on,
# this middleware answered those requests 401 before the route could check
# the signature: the render finished, the credits were spent, and the
# video was unreachable from the one browser that had just paid for it.
#
# A pattern rather than a literal because the project id is in the path,
# and it can never be covered by the exact-match set above.
_MEDIA_PATHS = re.compile(r"^/api/projects/[^/]+/(download|poster)$")


def _authenticates_itself(request: Request) -> bool:
    """Whether this request carries a credential this middleware can't read.

    The media routes qualify only when a token is actually presented.
    Without one they fall back to the bearer path and an ownership check,
    which must stay behind authentication — exempting them unconditionally
    would publish every finished video to anyone who could guess an id.

    Presenting a *wrong* token gains nothing: the route verifies it
    against MEDIA_URL_SECRET and answers 403. Same reasoning as the
    webhook — a signature scoped to one project is a stronger claim than a
    bearer token, which would prove only that somebody was logged in.
    """
    if request.url.path in _UNAUTHENTICATED_PATHS:
        return True
    return bool(_MEDIA_PATHS.match(request.url.path) and request.query_params.get("token"))


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

        # Re-rolling a scene belongs in the render budget, not the browsing
        # one. It bills a third party per call and re-encodes a whole video,
        # so leaving it on the per-minute allowance would protect the cheap
        # operation and expose the expensive one.
        path = request.url.path
        submitting_render = request.method == "POST" and (
            path == "/api/projects" or path.endswith("/regenerate")
        )
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

        elif self._require_auth and not _authenticates_itself(request):
            return _unauthorized("Not authenticated")

        return await call_next(request)


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )
