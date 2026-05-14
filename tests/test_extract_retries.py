"""Retry/backoff behavior for the OpenRouter call in `pipeline.extract`.

`_call_with_retries` retries transient OpenAI errors (timeout, connection,
429, 5xx) with bounded exponential backoff. Non-retryable errors propagate
immediately so the caller sees them on the first attempt.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import openai
import pytest

import pipeline.extract as extract_module
from pipeline.extract import _MAX_RETRIES, _call_with_retries


@pytest.fixture
def fast_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace `time.sleep` in pipeline.extract with a no-op recorder."""
    sleeps: list[float] = []
    monkeypatch.setattr(extract_module.time, "sleep", lambda s: sleeps.append(s))
    return sleeps


def _timeout_error() -> openai.APITimeoutError:
    return openai.APITimeoutError(httpx.Request("POST", "http://test"))


def _rate_limit_error() -> openai.RateLimitError:
    request = httpx.Request("POST", "http://test")
    response = httpx.Response(429, request=request)
    return openai.RateLimitError(message="rate limited", response=response, body=None)


def _bad_request_error() -> openai.BadRequestError:
    request = httpx.Request("POST", "http://test")
    response = httpx.Response(400, request=request)
    return openai.BadRequestError(message="bad request", response=response, body=None)


def test_returns_immediately_when_call_succeeds(fast_sleep: list[float]) -> None:
    call = MagicMock(return_value="ok")

    assert _call_with_retries(call) == "ok"
    assert call.call_count == 1
    assert fast_sleep == []


def test_retries_on_rate_limit_then_succeeds(fast_sleep: list[float]) -> None:
    call = MagicMock(side_effect=[_rate_limit_error(), _rate_limit_error(), "ok"])

    assert _call_with_retries(call) == "ok"
    assert call.call_count == 3
    # Two retries → two sleeps. Backoff base is 1s; jitter adds up to 25%.
    assert len(fast_sleep) == 2
    for actual, base in zip(fast_sleep, [1.0, 2.0]):
        assert base <= actual <= base * 1.25


def test_gives_up_after_max_retries(fast_sleep: list[float]) -> None:
    # _MAX_RETRIES retries → _MAX_RETRIES + 1 total attempts before re-raise.
    call = MagicMock(side_effect=[_timeout_error()] * (_MAX_RETRIES + 1))

    with pytest.raises(openai.APITimeoutError):
        _call_with_retries(call)

    assert call.call_count == _MAX_RETRIES + 1
    # Sleeps only happen between attempts → _MAX_RETRIES sleeps total.
    assert len(fast_sleep) == _MAX_RETRIES


def test_does_not_retry_on_bad_request(fast_sleep: list[float]) -> None:
    call = MagicMock(side_effect=_bad_request_error())

    with pytest.raises(openai.BadRequestError):
        _call_with_retries(call)

    assert call.call_count == 1
    assert fast_sleep == []


def test_does_not_retry_on_arbitrary_exception(fast_sleep: list[float]) -> None:
    call = MagicMock(side_effect=ValueError("local bug"))

    with pytest.raises(ValueError, match="local bug"):
        _call_with_retries(call)

    assert call.call_count == 1
    assert fast_sleep == []
