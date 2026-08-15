"""Telling "too fast" apart from "no money", both of which arrive as 429.

A live render failed on `insufficient_quota` and took three round trips to
say so, because the SDK retries a 429 twice by default. That is right for a
rate limit and wrong for an empty account: it will not have money on the
third attempt, and the credits for that render had already been spent.

So the SDK's retries are off and the distinction is made in _call_openai.
What matters is that the two paths cannot merge again — a quota failure
must be immediate and must not reach generate_script's own retry loop,
where it would become three more attempts.
"""

from __future__ import annotations

import pytest

from app.engines.script_engine import (
    ScriptGenerationError,
    ScriptProviderError,
    _is_out_of_quota,
)


class _Err:
    """Stands in for an SDK exception. Duck-typed because openai is an
    optional dependency — these run on an install that never had it."""

    def __init__(self, code=None, body=None):
        if code is not None:
            self.code = code
        if body is not None:
            self.body = body


# --- which 429 is this --------------------------------------------------


def test_the_code_attribute_is_read():
    assert _is_out_of_quota(_Err(code="insufficient_quota")) is True


def test_a_nested_body_is_read():
    """Where older SDKs put it, and where the live failure showed it."""
    assert _is_out_of_quota(_Err(body={"error": {"code": "insufficient_quota"}})) is True


def test_a_flat_body_is_read():
    assert _is_out_of_quota(_Err(body={"code": "insufficient_quota"})) is True


def test_an_ordinary_rate_limit_is_not_quota():
    """The case that must keep its retries. Getting this wrong turns a
    burst of traffic into a hard failure."""
    assert _is_out_of_quota(_Err(code="rate_limit_exceeded")) is False
    assert _is_out_of_quota(_Err(body={"error": {"code": "rate_limit_exceeded"}})) is False


def test_an_exception_carrying_neither_is_not_quota():
    """Absence of evidence is not evidence of an empty account — an
    unknown 429 should be retried, not turned into a billing message."""
    assert _is_out_of_quota(_Err()) is False
    assert _is_out_of_quota(_Err(body=None)) is False
    assert _is_out_of_quota(_Err(body="not a dict")) is False


# --- and what that costs the caller -------------------------------------


def test_a_quota_failure_is_not_a_generation_failure():
    """generate_script retries ScriptGenerationError three times, so the
    quota error must not be one. This is the whole point of the separate
    type and the only thing standing between a fix and the same waste one
    level up."""
    assert not issubclass(ScriptProviderError, ScriptGenerationError)
    assert not issubclass(ScriptGenerationError, ScriptProviderError)


async def test_an_empty_account_fails_on_the_first_call(monkeypatch):
    """One request, not three. Asserted by counting them."""
    openai = pytest.importorskip("openai")

    calls = 0

    class Completions:
        async def create(self, **kwargs):
            nonlocal calls
            calls += 1
            raise openai.RateLimitError(
                "insufficient_quota",
                response=_response(429),
                body={"error": {"code": "insufficient_quota"}},
            )

    _install_fake_client(monkeypatch, openai, Completions())

    from app.engines.script_engine import _call_openai
    from app.schemas.project import LLMConfig, LLMProvider

    with pytest.raises(ScriptProviderError) as caught:
        await _call_openai(
            LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4o-mini", api_key="k"),
            "system",
            "user",
        )

    assert calls == 1
    # The message has to name the fix: nothing in the pipeline can resolve
    # this and the operator is the only one who can.
    assert "platform.openai.com" in str(caught.value)


async def test_a_real_rate_limit_is_retried_and_then_succeeds(monkeypatch):
    """The other half. Turning off the SDK's retries must not mean no
    retries at all — a burst still has to ride out."""
    openai = pytest.importorskip("openai")
    monkeypatch.setattr("app.engines.script_engine._OPENAI_RETRY_BACKOFF_S", (0.0, 0.0))

    calls = 0

    class Completions:
        async def create(self, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise openai.RateLimitError(
                    "slow down", response=_response(429), body={"error": {"code": "rate_limit_exceeded"}}
                )
            return _completion('{"scenes": []}')

    _install_fake_client(monkeypatch, openai, Completions())

    from app.engines.script_engine import _call_openai
    from app.schemas.project import LLMConfig, LLMProvider

    result = await _call_openai(
        LLMConfig(provider=LLMProvider.OPENAI, model="gpt-4o-mini", api_key="k"), "s", "u"
    )

    assert calls == 2
    assert result == '{"scenes": []}'


# --- helpers ------------------------------------------------------------


def _response(status: int):
    import httpx

    return httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/x"))


def _completion(content: str):
    class Message:
        def __init__(self, c):
            self.content = c

    class Choice:
        def __init__(self, c):
            self.message = Message(c)

    class Completion:
        def __init__(self, c):
            self.choices = [Choice(c)]

    return Completion(content)


def _install_fake_client(monkeypatch, openai, completions):
    """Replace AsyncOpenAI, and record that retries were disabled on it."""

    class Chat:
        def __init__(self, c):
            self.completions = c

    class FakeClient:
        def __init__(self, **kwargs):
            # The fix itself: leaving the SDK's default of 2 here would
            # restore the three round trips this file exists to remove.
            assert kwargs.get("max_retries") == 0, "the SDK's own retries must stay off"
            self.chat = Chat(completions)

    monkeypatch.setattr(openai, "AsyncOpenAI", FakeClient)
