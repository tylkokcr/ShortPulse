"""Which platforms this deployment can actually publish to.

Configured per platform, the same way visual_engine decides which modes it
can run: a platform whose credentials are absent is not offered, rather
than offered and failing when someone presses the button. A self-hosted
install configures none of them and the whole feature disappears from the
UI.

Encryption is a precondition for all of them and not a per-platform
setting: without SOCIAL_TOKEN_SECRET the only way to store a grant would
be in plain text, and refusing to connect is the right answer to that.
"""

from __future__ import annotations

import logging

from app.core.config import Settings
from app.services.social.base import SocialPublisher
from app.services.social.youtube import YouTubePublisher

logger = logging.getLogger(__name__)

# Ordered as they should appear in the UI.
PLATFORMS = ("youtube", "instagram", "tiktok")


def redirect_uri(settings: Settings, platform: str) -> str:
    """Where the platform sends the browser back.

    Has to match what is registered in that platform's developer console
    character for character, which is why it is derived from one setting
    in one place rather than written out per platform.
    """
    return f"{settings.public_base_url.rstrip('/')}/api/social/callback/{platform}"


def build_publishers(settings: Settings) -> dict[str, SocialPublisher]:
    """Every platform this install is configured for."""
    if not settings.social_token_secret:
        # Reported by readiness.check as well, which is where an operator
        # is meant to see it. This is the enforcement.
        return {}

    publishers: dict[str, SocialPublisher] = {}

    if settings.youtube_client_id and settings.youtube_client_secret:
        publishers["youtube"] = YouTubePublisher(
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            redirect_uri=redirect_uri(settings, "youtube"),
        )

    # Instagram and TikTok land here once their app reviews clear. The
    # seam they plug into is already in base.py; what is missing is their
    # paperwork, not their code.

    if publishers:
        logger.info("Publishing enabled for: %s", ", ".join(sorted(publishers)))
    return publishers
