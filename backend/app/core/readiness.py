"""What is missing before this deployment should take real users.

Every item here is something that produces no error at all when it is
wrong. The app starts, requests succeed, and the damage shows up later:
renders given away free, video links that break on the next deploy, a
webhook endpoint that mints credits for anyone who finds it.

So they are checked once at startup and reported on /api/health, which
means a deploy script can refuse to promote a build rather than relying on
someone remembering the list.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Warning_:
    setting: str
    problem: str


def _hosted(settings) -> bool:
    """Whether this install has accounts at all.

    Keyed off Supabase being configured rather than a separate flag, the
    same way the rest of the codebase decides — a self-hosted install is
    supposed to be open, and warning it about anonymous access would be
    noise that teaches people to ignore the output.
    """
    return bool(settings.supabase_url)


def check(settings) -> list[Warning_]:
    """Production problems that are silent by construction."""
    warnings: list[Warning_] = []

    if _hosted(settings) and not settings.require_auth:
        warnings.append(
            Warning_(
                "REQUIRE_AUTH",
                "accounts are configured but unauthenticated callers are still served — "
                "they look like self-hosters to the code, so they render for free",
            )
        )

    if _hosted(settings) and not settings.media_url_secret:
        warnings.append(
            Warning_(
                "MEDIA_URL_SECRET",
                "unset, so each process invents one: video links break on restart and "
                "fail outright across more than one instance",
            )
        )

    if settings.stripe_secret_key and not settings.stripe_webhook_secret:
        warnings.append(
            Warning_(
                "STRIPE_WEBHOOK_SECRET",
                "checkout is live but webhooks cannot be verified, so purchases never "
                "grant credits — and an unverified endpoint would grant them to anyone",
            )
        )

    if settings.stripe_secret_key and settings.stripe_secret_key.startswith("sk_live_"):
        if "localhost" in settings.checkout_success_url:
            warnings.append(
                Warning_(
                    "CHECKOUT_SUCCESS_URL",
                    "live Stripe keys with a localhost return URL: real customers would "
                    "be sent to a page that does not exist for them",
                )
            )

    if settings.stripe_secret_key and settings.stripe_secret_key.startswith("sk_live_"):
        if not getattr(settings, "stripe_automatic_tax", False):
            warnings.append(
                Warning_(
                    "STRIPE_AUTOMATIC_TAX",
                    "selling for real money with no tax collection: VAT on digital sales to "
                    "EU consumers is owed at the buyer's local rate whether or not it was "
                    "charged, so it comes out of revenue instead",
                )
            )

    # Not gated on _hosted: a self-hosted install with no ffmpeg is just as
    # broken, and this is the single most likely thing to be wrong after
    # moving a .env from a dev machine into a container, where the paths it
    # names do not exist. Left unchecked it surfaces as [Errno 2] from a
    # subprocess three stages into a render, with the binary that could not
    # be found nowhere in the traceback.
    for setting, binary in (
        ("FFMPEG_BINARY", settings.ffmpeg_binary),
        ("FFPROBE_BINARY", settings.ffprobe_binary),
    ):
        if not shutil.which(binary):
            warnings.append(
                Warning_(
                    setting,
                    f"{binary!r} is not on PATH and is not an executable file: every "
                    "render will fail partway through, not at startup",
                )
            )

    if settings.llm_provider == "openai" and not settings.openai_api_key:
        warnings.append(
            Warning_("OPENAI_API_KEY", "provider is openai but no key is set; every render will fail")
        )

    if _hosted(settings) and not settings.database_url:
        warnings.append(
            Warning_(
                "DATABASE_URL",
                "accounts are configured but projects are held in memory: every render, "
                "and every credit balance, is lost on restart",
            )
        )

    # Supabase hands you the connection string with the password still
    # written as [YOUR-PASSWORD], and it is easy to paste as-is: it looks
    # complete, names the right host, and the brackets read as punctuation.
    # Unset is already reported above; half-set was not, and its failure is
    # a ValueError about an IPv6 address from inside the URL parser —
    # nothing that names the password or points at this file.
    if settings.database_url and re.search(r"\[[A-Z-]+\]", settings.database_url):
        warnings.append(
            Warning_(
                "DATABASE_URL",
                "still contains a bracketed placeholder from the connection string it "
                "was copied from: nothing can connect, and the error names an IP address "
                "rather than the password that was never filled in",
            )
        )

    return warnings


def log_at_startup(settings) -> list[Warning_]:
    warnings = check(settings)
    for w in warnings:
        logger.warning("NOT PRODUCTION READY — %s: %s", w.setting, w.problem)
    if not warnings and _hosted(settings):
        logger.info("Deployment checks passed")
    return warnings
