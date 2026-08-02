"""Shared test helpers.

The JWT fixtures here sign with a real ES256 keypair and serve a real JWKS
document over a stubbed transport. Nothing about the verification itself is
mocked — a test that faked signature checking would pass just as happily
against a verifier that checked nothing.
"""

from __future__ import annotations

import json
import time
import uuid

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

PROJECT_URL = "https://testproject.supabase.co"
ISSUER = f"{PROJECT_URL}/auth/v1"


class Signer:
    """Stands in for one Supabase project's signing key."""

    def __init__(self, kid: str = "key-1") -> None:
        self.kid = kid
        self._private = ec.generate_private_key(ec.SECP256R1())

    def jwk(self) -> dict:
        public = jwt.algorithms.ECAlgorithm.to_jwk(self._private.public_key(), as_dict=True)
        return {**public, "kid": self.kid, "use": "sig", "alg": "ES256"}

    def token(self, **overrides) -> str:
        now = int(time.time())
        claims = {
            "sub": str(uuid.uuid4()),
            "email": "someone@example.test",
            "aud": "authenticated",
            "iss": ISSUER,
            "iat": now,
            "exp": now + 3600,
            **overrides,
        }
        return jwt.encode(claims, self._private, algorithm="ES256", headers={"kid": self.kid})


class JWKSServer:
    """Serves whatever keys it is given, and counts how often it's asked."""

    def __init__(self, *signers: Signer) -> None:
        self.signers = list(signers)
        self.requests = 0

    def client(self) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests += 1
            return httpx.Response(
                200, content=json.dumps({"keys": [s.jwk() for s in self.signers]})
            )

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def signer() -> Signer:
    return Signer()


@pytest.fixture
def jwks(signer) -> JWKSServer:
    return JWKSServer(signer)
