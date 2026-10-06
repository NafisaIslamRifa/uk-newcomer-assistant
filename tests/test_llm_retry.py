"""Rate-limit pacing and retry logic (no network, time is faked)."""

import pytest

import agent.llm as llm


@pytest.fixture(autouse=True)
def no_pacing(monkeypatch):
    # LLM_RPM in .env would make the shared rate limiter sleep between these fake
    # calls and add extra entries to `sleeps`. Test the retry logic on its own.
    monkeypatch.setattr(llm, "_limiter", llm.RateLimiter(0))


class RateLimitError(Exception):  # same name the SDKs use
    status_code = 429


def test_retry_uses_suggested_delay(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RateLimitError("Quota exceeded. Please retry in 3.2s.")
        return "ok"

    assert llm.call_with_retry(flaky) == "ok"
    assert calls["n"] == 3
    assert sleeps == [4.2, 4.2]


def test_other_errors_are_not_retried(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def broken():
        calls["n"] += 1
        raise ValueError("bad request")

    try:
        llm.call_with_retry(broken)
    except ValueError:
        pass
    assert calls["n"] == 1


def test_rate_limiter_waits_when_window_full(monkeypatch):
    clock = {"t": 0.0}
    sleeps = []
    monkeypatch.setattr(llm.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(llm.time, "sleep", lambda s: (sleeps.append(s), clock.__setitem__("t", clock["t"] + s)))
    rl = llm.RateLimiter(rpm=2)
    rl.wait(); rl.wait()           # two requests at t=0: fine
    assert sleeps == []
    rl.wait()                      # third must wait ~60s
    assert sleeps and 59 < sleeps[0] <= 61


class InternalServerError(Exception):  # same name the SDKs use for HTTP 500
    status_code = 500


def test_server_errors_get_two_quick_retries(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    calls = {"n": 0}

    def always_500():
        calls["n"] += 1
        raise InternalServerError("boom")

    try:
        llm.call_with_retry(always_500)
    except InternalServerError:
        pass
    assert calls["n"] == 3 and sleeps == [3, 6]


def test_server_error_then_success(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    replies = iter([InternalServerError("x"), "ok"])

    def flaky():
        r = next(replies)
        if isinstance(r, Exception):
            raise r
        return r

    assert llm.call_with_retry(flaky) == "ok"
