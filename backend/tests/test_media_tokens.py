"""Signed media URLs.

A `<video>` tag cannot send an Authorization header, so the credential for
playback has to travel in the URL. That makes the URL itself the thing
protecting the file, and the properties below are what stop it becoming a
permanent, transferable key to someone else's video.
"""

from __future__ import annotations

import time

import pytest

from app.services.media_tokens import InvalidMediaToken, MediaTokenSigner

PROJECT = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def signer() -> MediaTokenSigner:
    return MediaTokenSigner("a-test-secret", ttl_s=900)


def test_a_freshly_signed_token_verifies(signer):
    token, expires_at = signer.sign(PROJECT)
    signer.verify(PROJECT, token)
    assert expires_at > time.time()


def test_a_token_is_useless_against_another_project(signer):
    """The whole point of signing the project id in. Otherwise one valid
    link would unlock every video on the service."""
    token, _ = signer.sign(PROJECT)
    with pytest.raises(InvalidMediaToken, match="Bad signature"):
        signer.verify(OTHER, token)


def test_a_token_from_a_different_secret_is_rejected(signer):
    """Someone who knows the format still can't mint one."""
    forged, _ = MediaTokenSigner("not-our-secret", ttl_s=900).sign(PROJECT)
    with pytest.raises(InvalidMediaToken, match="Bad signature"):
        signer.verify(PROJECT, forged)


def test_an_expired_token_is_rejected():
    signer = MediaTokenSigner("a-test-secret", ttl_s=-1)  # already expired
    token, _ = signer.sign(PROJECT)
    with pytest.raises(InvalidMediaToken, match="expired"):
        signer.verify(PROJECT, token)


def test_extending_the_expiry_invalidates_the_signature(signer):
    """The expiry is in the URL in plain sight, so the obvious attack is to
    edit it. It's inside the signed payload precisely to stop that."""
    token, _ = signer.sign(PROJECT)
    _, signature = token.split(".", 1)
    far_future = int(time.time()) + 10_000_000

    with pytest.raises(InvalidMediaToken, match="Bad signature"):
        signer.verify(PROJECT, f"{far_future}.{signature}")


@pytest.mark.parametrize("junk", ["", "nonsense", "abc.def", "...", "999", "1.2.3"])
def test_malformed_tokens_are_rejected_not_crashed(signer, junk):
    with pytest.raises(InvalidMediaToken):
        signer.verify(PROJECT, junk)


def test_each_instance_without_a_configured_secret_is_isolated():
    """Documents why MEDIA_URL_SECRET must be set in a real deployment:
    without it every process invents its own, so a link minted by one
    replica is rejected by the next."""
    token, _ = MediaTokenSigner(None).sign(PROJECT)
    with pytest.raises(InvalidMediaToken):
        MediaTokenSigner(None).verify(PROJECT, token)


def test_a_configured_secret_survives_a_restart():
    """The same secret must produce interchangeable signers, or links break
    on every deploy."""
    token, _ = MediaTokenSigner("shared-secret").sign(PROJECT)
    MediaTokenSigner("shared-secret").verify(PROJECT, token)  # must not raise
