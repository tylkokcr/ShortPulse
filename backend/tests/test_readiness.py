"""Deployment settings that are wrong without anything reporting it.

Each of these produces a working app. Requests succeed, renders finish,
nothing logs an error — and the damage lands later: renders given away,
video links that die on the next deploy, purchases that never credit
anyone. That is exactly the class of problem a checklist is bad at and a
startup check is good at.
"""

from __future__ import annotations

from app.core import readiness


class Settings:
    """A hosted deployment with everything set correctly."""

    def __init__(self, **overrides):
        self.supabase_url = "https://project.supabase.co"
        self.require_auth = True
        self.media_url_secret = "a-real-secret"
        self.database_url = "postgresql://user:pw@db/app"
        self.stripe_secret_key = None
        self.stripe_webhook_secret = None
        self.checkout_success_url = "https://app.example/credits"
        self.stripe_automatic_tax = False
        self.llm_provider = "ollama"
        self.openai_api_key = None
        self.__dict__.update(overrides)


def _settings_for(**overrides) -> list[str]:
    return [w.setting for w in readiness.check(Settings(**overrides))]


def test_a_correctly_configured_deployment_reports_nothing():
    assert _settings_for() == []


def test_a_self_hosted_install_is_not_nagged():
    """No Supabase means no accounts, and open access is the whole point
    there. Warning about it would train people to ignore the output."""
    assert _settings_for(supabase_url=None, require_auth=False, media_url_secret=None) == []


def test_accounts_without_required_auth_is_flagged():
    """The expensive one: anonymous callers look like self-hosters to the
    code, so every render they start is free."""
    assert "REQUIRE_AUTH" in _settings_for(require_auth=False)


def test_a_missing_media_secret_is_flagged():
    """Each process invents its own, so links break on restart and fail
    outright behind more than one instance."""
    assert "MEDIA_URL_SECRET" in _settings_for(media_url_secret=None)


def test_checkout_without_webhook_verification_is_flagged():
    """Purchases would take money and never grant credits — and the
    unverified endpoint would grant them to anyone who found it."""
    assert "STRIPE_WEBHOOK_SECRET" in _settings_for(stripe_secret_key="sk_test_x")


def test_test_keys_with_a_localhost_return_url_are_fine():
    """That is exactly how local development is meant to look."""
    flagged = _settings_for(
        stripe_secret_key="sk_test_x",
        stripe_webhook_secret="whsec_x",
        checkout_success_url="http://localhost:3000/credits",
    )
    assert "CHECKOUT_SUCCESS_URL" not in flagged


def test_live_keys_returning_to_localhost_are_flagged():
    """Paying customers sent to a page that only exists on the developer's
    laptop."""
    flagged = _settings_for(
        stripe_secret_key="sk_live_x",
        stripe_webhook_secret="whsec_x",
        checkout_success_url="http://localhost:3000/credits",
    )
    assert "CHECKOUT_SUCCESS_URL" in flagged


def test_openai_without_a_key_is_flagged():
    assert "OPENAI_API_KEY" in _settings_for(llm_provider="openai")


def test_accounts_without_a_database_is_flagged():
    """Projects and balances would live in memory and vanish on restart."""
    assert "DATABASE_URL" in _settings_for(database_url=None)


def test_every_warning_says_what_goes_wrong_not_just_what_is_unset():
    """A warning that only names a setting gets skimmed past."""
    for w in readiness.check(Settings(require_auth=False, media_url_secret=None)):
        assert len(w.problem) > 40, w


def test_live_keys_without_tax_collection_are_flagged():
    """VAT on digital sales to EU consumers is owed whether or not it was
    charged — uncollected, it comes out of revenue rather than being
    avoided."""
    flagged = _settings_for(
        stripe_secret_key="sk_live_x",
        stripe_webhook_secret="whsec_x",
        checkout_success_url="https://app.example/credits",
        stripe_automatic_tax=False,
    )
    assert "STRIPE_AUTOMATIC_TAX" in flagged


def test_test_keys_without_tax_collection_are_not_flagged():
    """Nobody is being charged anything, so there is no tax to collect."""
    flagged = _settings_for(stripe_secret_key="sk_test_x", stripe_webhook_secret="whsec_x")
    assert "STRIPE_AUTOMATIC_TAX" not in flagged
