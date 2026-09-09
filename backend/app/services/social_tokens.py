"""Encrypting the platform tokens at rest.

What is being protected here is not a ShortPulse credential. It is an
access grant to somebody's YouTube channel or TikTok account, and the
consequence of losing one is a stranger publishing in their name. That is
a different class of secret from anything else this service stores, and it
is why these do not sit in the database as text the way an API key from a
settings file might.

The threat this actually answers is a copy of the database going somewhere
it shouldn't — a backup, a snapshot, a query run by the wrong person, a
`select *` in a log. In all of those the ciphertext is useless without
SOCIAL_TOKEN_SECRET, which lives in the environment and never in a row. It
does not defend against an attacker who already has the running process,
and nothing at this layer could: that process has to be able to decrypt.

Fernet rather than a hand-rolled construction. It is AES-128-CBC with an
HMAC over the ciphertext, which means a tampered token is a decryption
error rather than a decrypted lie, and it comes from `cryptography` —
already installed here, because pyjwt[crypto] needs it to verify the
ES256 tokens Supabase issues. No new dependency for this.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class TokenDecryptionError(Exception):
    """Stored ciphertext could not be read back.

    In practice this means one thing: SOCIAL_TOKEN_SECRET is not the one
    the row was written with. There is no recovering the token, so callers
    should treat the connection as dead and ask the user to reconnect —
    which costs them one OAuth round trip and is the only honest option.
    """


def _fernet_key(secret: str) -> bytes:
    """Turn whatever is in the env var into a key Fernet will accept.

    Fernet wants exactly 32 bytes, urlsafe-base64 encoded. Requiring the
    operator to produce that shape by hand invites the failure where a
    plausible-looking value is rejected at boot — or worse, where somebody
    pads a short string to make the error go away. Hashing accepts any
    input and always produces the right shape.

    SHA-256 with no stretching is deliberate and worth being explicit
    about: this is a format conversion, not password hashing. The input is
    expected to be high-entropy already, because it sits in the same file
    as the database URL and is generated, not chosen:

        openssl rand -base64 48

    A short human-picked passphrase here would be brute-forceable, and no
    iteration count would make it a good idea.
    """
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


class TokenCipher:
    """Encrypts and decrypts platform tokens.

    One instance per process, built from settings at startup. Rotating the
    secret orphans every stored token — there is no second key and no
    re-encryption pass, because the recovery for a connection that cannot
    be decrypted is the same either way: the user reconnects. Anything
    cleverer would be machinery guarding a thirty-second inconvenience.
    """

    def __init__(self, secret: str) -> None:
        self._fernet = Fernet(_fernet_key(secret))

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode())

    def decrypt(self, blob: bytes | memoryview | None) -> str | None:
        """Read a token back. None in, None out — a connection with no
        refresh token is normal on platforms that don't issue one."""
        if blob is None:
            return None
        try:
            return self._fernet.decrypt(bytes(blob)).decode()
        except InvalidToken as exc:
            # Deliberately says nothing about which row or which user: this
            # lands in logs, and the interesting part is the configuration,
            # not the payload.
            raise TokenDecryptionError(
                "Stored platform token could not be decrypted. SOCIAL_TOKEN_SECRET "
                "does not match the value these rows were written with."
            ) from exc
