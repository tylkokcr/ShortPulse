"""Supabase token verification.

Runs against a real ES256 keypair and a stub JWKS endpoint, so every
signature is genuinely produced and genuinely checked — no mocking of the
verification itself, which is the part that must not be wrong.

The attacks these tests stand against are the ones that actually work
against a careless JWT check: a token from someone else's Supabase
project, a token signed with a key we never published, an expired one, and
an unsigned one claiming `alg: none`.
"""

from __future__ import annotations

import time
import uuid

import jwt
import pytest

from app.services.supabase_auth import AuthError, SupabaseTokenVerifier
from tests.conftest import ISSUER, PROJECT_URL, Signer


@pytest.fixture
def verifier(jwks) -> SupabaseTokenVerifier:
    return SupabaseTokenVerifier(PROJECT_URL, http_client=jwks.client())


# --- the happy path ------------------------------------------------------


async def test_a_valid_token_identifies_the_user(verifier, signer):
    user_id = str(uuid.uuid4())
    user = await verifier.verify(signer.token(sub=user_id, email="a@b.test"))

    assert user.id == user_id
    assert user.email == "a@b.test"


async def test_jwks_url_follows_supabase_convention(verifier):
    assert verifier.jwks_url == f"{PROJECT_URL}/auth/v1/.well-known/jwks.json"
    assert verifier.issuer == ISSUER


async def test_keys_are_cached_across_requests(verifier, signer, jwks):
    for _ in range(5):
        await verifier.verify(signer.token())
    assert jwks.requests == 1


# --- forgeries and mistakes ---------------------------------------------


async def test_a_token_from_another_supabase_project_is_rejected(jwks, signer):
    """Anyone can create a free Supabase project. Without the issuer check
    they could sign themselves a token as any user id they like — but they
    can't publish their key in *our* JWKS, so the signature fails first.
    This pins the issuer check independently, in case a future change ever
    makes both projects' keys reachable."""
    verifier = SupabaseTokenVerifier(PROJECT_URL, http_client=jwks.client())
    foreign = signer.token(iss="https://someoneelse.supabase.co/auth/v1")

    with pytest.raises(AuthError, match="Rejected token"):
        await verifier.verify(foreign)


async def test_a_token_signed_by_an_unpublished_key_is_rejected(jwks):
    """The core forgery attempt: attacker generates their own keypair."""
    attacker = Signer(kid="key-1")  # same kid as ours, different key
    verifier = SupabaseTokenVerifier(PROJECT_URL, http_client=jwks.client())

    with pytest.raises(AuthError, match="Rejected token"):
        await verifier.verify(attacker.token())


async def test_an_unknown_key_id_is_rejected(jwks):
    attacker = Signer(kid="not-a-real-key")
    verifier = SupabaseTokenVerifier(PROJECT_URL, http_client=jwks.client())

    with pytest.raises(AuthError, match="unknown key"):
        await verifier.verify(attacker.token())


async def test_an_expired_token_is_rejected(verifier, signer):
    stale = signer.token(exp=int(time.time()) - 60)
    with pytest.raises(AuthError, match="Rejected token"):
        await verifier.verify(stale)


async def test_an_unsigned_token_is_rejected(verifier):
    """`alg: none` is the oldest JWT attack there is: strip the signature
    and hope the verifier takes the payload's word for it."""
    unsigned = jwt.encode(
        {"sub": "attacker", "aud": "authenticated", "iss": ISSUER,
         "exp": int(time.time()) + 3600},
        key="",
        algorithm="none",
        headers={"kid": "key-1"},
    )
    with pytest.raises(AuthError, match="Unsupported signing algorithm"):
        await verifier.verify(unsigned)


async def test_a_token_for_the_wrong_audience_is_rejected(verifier, signer):
    """Supabase issues tokens with other audiences too; only a logged-in
    end user's token carries `authenticated`."""
    with pytest.raises(AuthError, match="Rejected token"):
        await verifier.verify(signer.token(aud="anon"))


async def test_garbage_is_rejected(verifier):
    with pytest.raises(AuthError, match="Malformed token"):
        await verifier.verify("not-a-jwt")


async def test_a_token_without_a_key_id_is_rejected(verifier, signer):
    no_kid = jwt.encode({"sub": "x"}, signer._private, algorithm="ES256")
    with pytest.raises(AuthError, match="no key id"):
        await verifier.verify(no_kid)


# --- operational edges ---------------------------------------------------


async def test_key_rotation_is_picked_up(jwks, signer):
    """A key added after the cache was warmed must be accepted without
    waiting for the TTL, otherwise a rotation logs everyone out."""
    verifier = SupabaseTokenVerifier(PROJECT_URL, http_client=jwks.client())
    await verifier.verify(signer.token())  # warms the cache
    assert jwks.requests == 1

    rotated = Signer(kid="key-2")
    jwks.signers.append(rotated)

    user = await verifier.verify(rotated.token())
    assert user.id
    assert jwks.requests == 2  # exactly one refetch


async def test_an_empty_jwks_says_why(jwks):
    """The likely real-world cause is a project still on a legacy shared
    secret, and 'no usable keys' alone wouldn't hint at that."""
    jwks.signers.clear()
    verifier = SupabaseTokenVerifier(PROJECT_URL, http_client=jwks.client())

    with pytest.raises(AuthError, match="legacy HS256 shared secret"):
        await verifier.verify(Signer().token())
