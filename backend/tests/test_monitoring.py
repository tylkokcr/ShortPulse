"""Error reporting stays off unless it is asked for.

The failure mode worth guarding is not "reports don't arrive" — it is a
self-hosted install quietly sending crash reports containing someone's
video topics to a third party because a default was left on.
"""

from __future__ import annotations

import pytest

from app.core import monitoring


class Settings:
    def __init__(self, dsn=None):
        self.sentry_dsn = dsn
        self.sentry_environment = "test"


@pytest.fixture(autouse=True)
def _reset():
    monitoring._enabled = False
    yield
    monitoring._enabled = False


def test_no_dsn_means_nothing_is_configured():
    assert monitoring.configure(Settings()) is False
    assert monitoring._enabled is False


def test_reporting_a_failure_without_a_dsn_does_nothing():
    """Called on every pipeline failure, including on installs that never
    configured reporting — it must not raise there."""
    monitoring.report_render_failure(RuntimeError("boom"), project_id="p1", stage="render")


def test_a_dsn_turns_it_on_and_tags_the_project(monkeypatch):
    captured = {}

    class FakeScope:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def set_tag(self, k, v):
            captured.setdefault("tags", {})[k] = v

    import sentry_sdk

    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: captured.update(init=kw))
    monkeypatch.setattr(sentry_sdk, "new_scope", lambda: FakeScope())
    monkeypatch.setattr(sentry_sdk, "capture_exception", lambda e: captured.update(exc=e))

    assert monitoring.configure(Settings(dsn="https://x@sentry.test/1")) is True

    # Personal data must stay off: requests here carry topics, scripts and
    # checkout payloads.
    assert captured["init"]["send_default_pii"] is False

    error = RuntimeError("ffmpeg died")
    monitoring.report_render_failure(error, project_id="p42", stage="upload")

    assert captured["exc"] is error
    assert captured["tags"] == {"stage": "upload", "project_id": "p42"}
