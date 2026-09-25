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
import os

from app.core.config import Settings
from app.services.social.base import SocialPublisher
from app.services.social.facebook import FacebookPublisher
from app.services.social.instagram import InstagramPublisher
from app.services.social.tiktok import TikTokPublisher
from app.services.social.youtube import YouTubePublisher

logger = logging.getLogger(__name__)

# Ordered as they should appear in the UI, which is the order their
# reviews were expected to clear rather than anything about the code.
PLATFORMS = ("youtube", "instagram", "facebook", "tiktok")


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

    # Two Meta destinations, two apps. They used to be configured
    # together on the reading that one app id served both, which is true
    # of the Facebook Login route to Instagram and false of Instagram
    # Business Login — that use case issues its own id and secret, and
    # the Facebook pair is refused by instagram.com's dialog. Tying them
    # together meant Instagram was offered the moment Facebook was
    # configured, and then failed before the user saw a consent screen.
    if settings.meta_app_id and settings.meta_app_secret:
        publishers["facebook"] = FacebookPublisher(
            app_id=settings.meta_app_id,
            app_secret=settings.meta_app_secret,
            redirect_uri=redirect_uri(settings, "facebook"),
        )

    if settings.instagram_app_id and settings.instagram_app_secret:
        publishers["instagram"] = InstagramPublisher(
            app_id=settings.instagram_app_id,
            app_secret=settings.instagram_app_secret,
            redirect_uri=redirect_uri(settings, "instagram"),
        )

    if settings.tiktok_client_key and settings.tiktok_client_secret:
        publishers["tiktok"] = TikTokPublisher(
            client_key=settings.tiktok_client_key,
            client_secret=settings.tiktok_client_secret,
            redirect_uri=redirect_uri(settings, "tiktok"),
        )

    _report(settings, publishers)
    return publishers


# The two settings each platform needs, and the names an operator is most
# likely to reach for instead.
#
# The alternates are not typos, they are the other true name: Meta's own
# OAuth dialog takes `client_id` and `client_secret`, while its console
# labels the same pair "Instagram app ID" and "Instagram app secret".
# Someone copying from the dialog docs writes CLIENT and gets silence —
# the platform simply does not appear, with nothing anywhere saying why.
# This is the same confusion TikTok's `client_key` is commented about in
# config.py, one step worse because both spellings are plausible.
_CREDENTIALS: dict[str, tuple[tuple[str, str], tuple[str, str]]] = {
    "youtube": (("YOUTUBE_CLIENT_ID", ""), ("YOUTUBE_CLIENT_SECRET", "")),
    "facebook": (("META_APP_ID", ""), ("META_APP_SECRET", "")),
    "instagram": (
        ("INSTAGRAM_APP_ID", "INSTAGRAM_CLIENT_ID"),
        ("INSTAGRAM_APP_SECRET", "INSTAGRAM_CLIENT_SECRET"),
    ),
    "tiktok": (("TIKTOK_CLIENT_KEY", ""), ("TIKTOK_CLIENT_SECRET", "")),
}


def _report(settings: Settings, publishers: dict[str, SocialPublisher]) -> None:
    """Say what is on, what is off, and — where we can tell — why.

    Absence is the failure mode here. A platform that is not configured
    is simply missing from the Connections page: no error, no warning,
    nothing in the API response to distinguish "this deployment does not
    offer it" from "you spelled the variable wrong". An operator has no
    way to tell those apart from the outside, so this says it at startup
    where they will look.

    Not a readiness warning, deliberately: `main.py` reports the install
    as not production-ready when there are any, and an install that
    simply does not publish to Instagram is fine.
    """
    if publishers:
        logger.info("Publishing enabled for: %s", ", ".join(sorted(publishers)))

    for platform in PLATFORMS:
        if platform in publishers:
            continue
        expected = _CREDENTIALS.get(platform)
        if not expected:
            continue

        misspelled = [
            (wanted, alternate)
            for wanted, alternate in expected
            if alternate and not os.environ.get(wanted) and os.environ.get(alternate)
        ]
        if misspelled:
            logger.warning(
                "%s is not enabled, but %s is set — this deployment reads %s. "
                "Rename it and restart.",
                platform,
                ", ".join(alternate for _, alternate in misspelled),
                ", ".join(wanted for wanted, _ in misspelled),
            )
            continue

        set_names = [wanted for wanted, _ in expected if os.environ.get(wanted)]
        if set_names and len(set_names) != len(expected):
            missing = [wanted for wanted, _ in expected if wanted not in set_names]
            logger.warning(
                "%s is not enabled: %s is set but %s is not — it needs both.",
                platform,
                ", ".join(set_names),
                ", ".join(missing),
            )
