"""Shared test helpers.

The JWT fixtures here sign with a real ES256 keypair and serve a real JWKS
document over a stubbed transport. Nothing about the verification itself is
mocked — a test that faked signature checking would pass just as happily
against a verifier that checked nothing.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec


def _adopt_ffmpeg_paths_from_dotenv() -> None:
    """Let the render tests see the ffmpeg the app is configured to use.

    They need a build with libass and skip without one. The app finds it
    through pydantic-settings, which reads `.env`; pytest doesn't — so on a
    machine set up exactly as the README describes, those tests skipped
    silently and the suite still reported green. Anything already exported
    wins, so CI can override.
    """
    dotenv = Path(__file__).resolve().parents[1] / ".env"
    if not dotenv.exists():
        return
    for line in dotenv.read_text().splitlines():
        key, _, value = line.partition("=")
        key = key.strip()
        if key in ("FFMPEG_BINARY", "FFPROBE_BINARY") and key not in os.environ:
            os.environ[key] = value.strip()


_adopt_ffmpeg_paths_from_dotenv()

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
