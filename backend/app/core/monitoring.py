"""Error reporting, off unless a DSN is configured.

A render that fails is caught, written to the project row and reported to
the user — which means the exception never propagates, so nothing outside
the process ever hears about it. On a machine you own that is fine, you
read the log. On a deployment it means the first you learn of a broken
pipeline is a user telling you, and by then it has failed for everyone.

Absent SENTRY_DSN every function here is a no-op, so a self-hosted install
sends nothing anywhere.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_enabled = False


def configure(settings) -> bool:
    """Start reporting, if this deployment asked for it."""
    global _enabled
    if not settings.sentry_dsn:
        return False

    try:
        import sentry_sdk
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed; not reporting")
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        # Off by design. Requests to this API carry project topics, scripts
        # and — on the checkout route — things that should not leave the
        # machine in a crash report.
        send_default_pii=False,
        # Errors are the point; tracing every render would be noise and
        # quota. Raise deliberately if latency ever needs investigating.
        traces_sample_rate=0.0,
    )
    _enabled = True
    logger.info("Error reporting enabled (%s)", settings.sentry_environment)
    return True


def report_render_failure(exc: BaseException, *, project_id: str, stage: str) -> None:
    """Report a pipeline failure that the pipeline itself handled.

    Needed explicitly: the pipeline catches everything so one bad render
    can't take the worker down, and a caught exception is invisible to the
    framework integrations.
    """
    if not _enabled:
        return
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("stage", stage)
        scope.set_tag("project_id", project_id)
        sentry_sdk.capture_exception(exc)
