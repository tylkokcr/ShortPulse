"""Short-lived signed URLs for video playback and download.

The problem these solve is narrow and unavoidable: a `<video src=...>` tag
cannot send an Authorization header. Neither can a download triggered by
navigating to a URL. So once a project has an owner, there is no way for
the browser to prove who it is on the request that actually fetches the
bytes.

The answer is the same one S3 presigned URLs use — put a short-lived
signature in the URL itself. Possessing the token grants access to exactly
one project's video, for a few minutes, and nothing else. It carries no
personal data and cannot be extended or replayed against another project.

Not a substitute for the ownership check: the token is only ever issued to
a caller who already passed it on an authenticated request.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time

logger = logging.getLogger(__name__)


class InvalidMediaToken(Exception):
    """Token was malformed, tampered with, or has expired."""


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class MediaTokenSigner:
    def __init__(self, secret: str | None, *, ttl_s: int = 900) -> None:
        if secret:
            self._secret = secret.encode()
        else:
            # Usable out of the box, but links die with the process and
            # don't work across replicas. Fine for a single self-hosted
            # instance; a real deployment must set MEDIA_URL_SECRET.
            self._secret = secrets.token_bytes(32)
            logger.warning(
                "MEDIA_URL_SECRET is not set — generated an ephemeral one. Video links "
                "will stop working after a restart and won't validate across instances."
            )
        self._ttl_s = ttl_s

    def _signature(self, project_id: str, expires_at: int) -> str:
        # The project id is inside the signed payload, so a token minted
        # for one video cannot be replayed against another.
        message = f"{project_id}:{expires_at}".encode()
        return _b64(hmac.new(self._secret, message, hashlib.sha256).digest())

    def sign(self, project_id: str, *, ttl_s: int | None = None) -> tuple[str, int]:
        """Returns (token, unix expiry).

        `ttl_s` overrides the default for the one case that needs a longer
        life than playback: a URL handed to Instagram or TikTok, which
        fetch the video themselves on their own schedule. Nobody is
        waiting on that link, so the fifteen minutes that are generous for
        a <video> tag can expire while their queue is still working
        through it — and the failure surfaces on their side, as a media
        error with nothing pointing back here.
        """
        expires_at = int(time.time()) + (ttl_s or self._ttl_s)
        return f"{expires_at}.{self._signature(project_id, expires_at)}", expires_at

    def verify(self, project_id: str, token: str) -> None:
        """Raises InvalidMediaToken unless the token is valid for this project."""
        try:
            expiry_part, signature = token.split(".", 1)
            expires_at = int(expiry_part)
        except (ValueError, AttributeError) as exc:
            raise InvalidMediaToken("Malformed token") from exc

        # compare_digest, not ==, so a wrong signature can't be recovered
        # byte by byte from response timings.
        if not hmac.compare_digest(signature, self._signature(project_id, expires_at)):
            raise InvalidMediaToken("Bad signature")

        # Checked after the signature so an attacker can't learn anything
        # from which error they get.
        if expires_at < time.time():
            raise InvalidMediaToken("Token has expired")
