"""Verifying Supabase access tokens.

Supabase signs access tokens with an asymmetric key (ES256 by default) and
publishes the matching *public* keys at a well-known JWKS endpoint. That
means this service holds no auth secret at all: it fetches public keys over
HTTPS and checks signatures with them. Nothing here is worth stealing.

What a token must satisfy to be accepted:
  * signature from a key currently published in the project's JWKS
  * `iss` is this project's auth server — not some other Supabase project
  * `aud` is "authenticated" — not an anon or service token
  * `exp` / `iat` are current

Every one of those is load-bearing. Skipping the issuer check in particular
would let anyone mint a valid token on their own free Supabase project and
present it here as any user they liked.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx
import jwt
from jwt import PyJWK

logger = logging.getLogger(__name__)

# Supabase's edge caches the JWKS for 10 minutes, so a shorter TTL here
# buys nothing. Long enough to keep per-request latency at zero, short
# enough that a rotated-out key stops being accepted promptly.
_JWKS_TTL_S = 600

# Asymmetric only. HS256 is deliberately absent: a symmetric algorithm
# would mean holding a secret that can also *mint* tokens, and accepting it
# alongside asymmetric keys is the classic algorithm-confusion foothold.
_ALLOWED_ALGORITHMS = ["ES256", "RS256"]

_AUDIENCE = "authenticated"


class AuthError(Exception):
    """Token was missing, malformed, expired, or not ours."""


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str | None


class SupabaseTokenVerifier:
    """Verifies access tokens against a project's published JWKS.

    Keys are cached in-process. A token signed by a key we haven't seen
    triggers exactly one refetch — that's what makes key rotation
    transparent — but a bogus `kid` can't be used to hammer the JWKS
    endpoint, because the refetch is rate-limited by the same TTL.
    """

    def __init__(self, supabase_url: str, *, http_client: httpx.AsyncClient | None = None) -> None:
        base = supabase_url.rstrip("/")
        self.issuer = f"{base}/auth/v1"
        self.jwks_url = f"{base}/auth/v1/.well-known/jwks.json"
        self._client = http_client
        self._keys: dict[str, PyJWK] = {}
        self._fetched_at = 0.0

    async def _fetch_jwks(self) -> None:
        client = self._client or httpx.AsyncClient(timeout=10)
        try:
            response = await client.get(self.jwks_url)
            response.raise_for_status()
            payload = response.json()
        finally:
            if self._client is None:
                await client.aclose()

        keys: dict[str, PyJWK] = {}
        for entry in payload.get("keys", []):
            try:
                keys[entry["kid"]] = PyJWK.from_dict(entry)
            except (KeyError, jwt.PyJWKError, jwt.InvalidKeyError) as exc:
                logger.warning("Skipping unusable JWKS entry: %s", exc)

        if not keys:
            # Most likely cause: the project still signs with a legacy
            # shared secret, in which case the endpoint returns no keys at
            # all. Worth saying plainly — the symptom is otherwise just
            # "every login fails".
            raise AuthError(
                f"{self.jwks_url} published no usable keys. If this project still uses a "
                "legacy HS256 shared secret, migrate it to an asymmetric signing key."
            )

        self._keys = keys
        self._fetched_at = time.monotonic()
        logger.info("Loaded %d Supabase signing key(s)", len(keys))

    async def _key_for(self, kid: str) -> PyJWK:
        stale = time.monotonic() - self._fetched_at > _JWKS_TTL_S
        if not self._keys or stale:
            await self._fetch_jwks()
        if kid not in self._keys and not stale:
            # Unknown key on a fresh cache means rotation happened inside
            # the TTL window. One refetch, then give up.
            await self._fetch_jwks()
        try:
            return self._keys[kid]
        except KeyError:
            raise AuthError(f"Token signed by unknown key {kid!r}") from None

    async def verify(self, token: str) -> AuthenticatedUser:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthError(f"Malformed token: {exc}") from exc

        kid = header.get("kid")
        if not kid:
            raise AuthError("Token has no key id")
        if header.get("alg") not in _ALLOWED_ALGORITHMS:
            raise AuthError(f"Unsupported signing algorithm {header.get('alg')!r}")

        key = await self._key_for(kid)
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=_ALLOWED_ALGORITHMS,
                audience=_AUDIENCE,
                issuer=self.issuer,
                options={"require": ["exp", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthError(f"Rejected token: {exc}") from exc

        subject = claims.get("sub")
        if not subject:
            raise AuthError("Token has no subject")
        return AuthenticatedUser(id=str(subject), email=claims.get("email"))
