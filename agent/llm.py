"""One small interface over different LLM providers.

Every provider formats tool calling differently. Each class below hides that,
so the agent loop only ever does:

    chat.add_user(text)
    reply = chat.complete(tools)          # -> Reply(text, tool_calls)
    chat.add_tool_results(results)

Providers (set LLM_PROVIDER in .env):
    anthropic : Claude, via the anthropic SDK
    openai    : OpenAI models, via the openai SDK
    gemini    : Google Gemini, via its OpenAI-compatible endpoint (has a free tier)
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
import time
from collections import deque
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-3.8-flash",
}
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MAX_TOKENS = 1500
MAX_RETRIES = 4
# Each LLM request gives up after this many seconds. The SDK default is 10 minutes,
# which would leave the user staring at a spinner when the provider is slow.
REQUEST_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "45"))


# ------------------------------------------------------- rate limits + retries
class RateLimiter:
    """Client-side pacing: never send more than `rpm` requests in any 60 s window.
    Set LLM_RPM in .env to your plan's limit (e.g. 5 for Gemini free tier).
    0 or unset = no pacing."""

    def __init__(self, rpm: int):
        self.rpm = rpm
        self.sent: deque[float] = deque()

    def wait(self) -> None:
        if self.rpm <= 0:
            return
        now = time.monotonic()
        while self.sent and now - self.sent[0] > 60:
            self.sent.popleft()
        if len(self.sent) >= self.rpm:
            delay = 60 - (now - self.sent[0]) + 0.5
            print(f"  ⏳ pacing requests ({self.rpm}/min limit), waiting {delay:.0f}s...",
                  file=sys.stderr)
            time.sleep(delay)
        self.sent.append(time.monotonic())


_limiter = RateLimiter(int(os.getenv("LLM_RPM", "0") or 0))


def _retry_delay(exc: Exception, attempt: int) -> float:
    """Use the provider's suggested wait if it gives one, else exponential backoff."""
    m = re.search(r"retry in ([\d.]+)\s*s", str(exc), re.I)
    return float(m.group(1)) + 1 if m else min(60, 5 * 2 ** attempt)


def _is_rate_limit(exc: Exception) -> bool:
    return type(exc).__name__ == "RateLimitError" or getattr(exc, "status_code", None) == 429


TRANSIENT_ERRORS = {"InternalServerError", "APITimeoutError", "APIConnectionError",
                    "ServiceUnavailableError", "OverloadedError"}


def _is_transient(exc: Exception) -> bool:
    """Temporary provider-side problems worth a quick retry (5xx, timeouts, network)."""
    status = getattr(exc, "status_code", None)
    return type(exc).__name__ in TRANSIENT_ERRORS or (isinstance(status, int) and status >= 500)


def call_with_retry(fn):
    """Run one LLM request with pacing, retrying on rate-limit errors."""
    for attempt in range(MAX_RETRIES + 1):
        _limiter.wait()
        try:
            return fn()
        except Exception as exc:
            if _is_rate_limit(exc) and attempt < MAX_RETRIES:
                delay = _retry_delay(exc, attempt)
                reason = "rate limited"
            elif _is_transient(exc) and attempt < 2:   # at most 2 quick retries
                delay = 3 * (attempt + 1)
                reason = f"provider error ({type(exc).__name__})"
            else:
                raise
            print(f"  ⏳ {reason}, retrying in {delay:.0f}s "
                  f"(attempt {attempt + 1})...", file=sys.stderr)
            time.sleep(delay)


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Reply:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)


# ---------------------------------------------------------------- Anthropic
class AnthropicChat:
    def __init__(self, system: str, model: str, api_key: str):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key, timeout=REQUEST_TIMEOUT, max_retries=0)
        self.model, self.system = model, system
        self.messages: list[dict] = []

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def complete(self, tools: list[dict]) -> Reply:
        resp = call_with_retry(lambda: self.client.messages.create(
            model=self.model, max_tokens=MAX_TOKENS, system=self.system,
            tools=[{"name": t["name"], "description": t["description"],
                    "input_schema": t["input_schema"]} for t in tools],
            messages=self.messages,
        ))
        self.messages.append({"role": "assistant", "content": resp.content})
        text = "".join(b.text for b in resp.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in resp.content if b.type == "tool_use"]
        usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
        return Reply(text, calls, usage)

    def add_tool_results(self, results: list[tuple[ToolCall, str, bool]]) -> None:
        self.messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": call.id, "content": text, "is_error": is_err}
            for call, text, is_err in results
        ]})


# ------------------------------------------------- OpenAI / Gemini (compatible)
def _simplify_schema(schema: dict) -> dict:
    """Make JSON schemas portable: drop 'title' keys and turn
    anyOf[X, null] (how Python Optional[...] is written) into plain X."""
    s = copy.deepcopy(schema)

    def walk(node):
        if isinstance(node, dict):
            node.pop("title", None)
            any_of = node.get("anyOf")
            if isinstance(any_of, list):
                non_null = [o for o in any_of if o.get("type") != "null"]
                if len(non_null) == 1:
                    node.pop("anyOf")
                    node.update(non_null[0])
            if node.get("default", "x") is None:
                node.pop("default")
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(s)
    return s


class OpenAICompatChat:
    def __init__(self, system: str, model: str, api_key: str, base_url: str | None = None):
        import openai
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url,
                                    timeout=REQUEST_TIMEOUT, max_retries=0)
        self.model = model
        self.messages: list[dict] = [{"role": "system", "content": system}]

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def complete(self, tools: list[dict]) -> Reply:
        resp = call_with_retry(lambda: self.client.chat.completions.create(
            model=self.model, max_tokens=MAX_TOKENS, messages=self.messages,
            tools=[{"type": "function", "function": {
                "name": t["name"], "description": t["description"],
                "parameters": _simplify_schema(t["input_schema"])}} for t in tools],
        ))
        if isinstance(resp, str):
            # The SDK returns raw text when the server's reply isn't JSON, which almost
            # always means LLM_BASE_URL points at a web page rather than the API.
            raise RuntimeError(
                f"The LLM endpoint did not return JSON. Check LLM_BASE_URL "
                f"(now {self.client.base_url}). Reply started: {resp[:200]!r}")
        msg = resp.choices[0].message
        self.messages.append(msg.model_dump(exclude_none=True))
        calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(tc.id, tc.function.name, args))
        usage = {}
        if resp.usage:
            usage = {"input_tokens": resp.usage.prompt_tokens,
                     "output_tokens": resp.usage.completion_tokens}
        return Reply(msg.content or "", calls, usage)

    def add_tool_results(self, results: list[tuple[ToolCall, str, bool]]) -> None:
        for call, text, _ in results:
            self.messages.append({"role": "tool", "tool_call_id": call.id, "content": text})


# ------------------------------------------------------------------ factory
def make_chat(system: str):
    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip() or DEFAULT_MODELS.get(provider, "")
    if not api_key:
        raise SystemExit("LLM_API_KEY is empty. Add your key to .env (never commit it).")

    if provider == "anthropic":
        return AnthropicChat(system, model, api_key)
    if provider == "openai":
        return OpenAICompatChat(system, model, api_key, os.getenv("LLM_BASE_URL") or None)
    if provider == "gemini":
        return OpenAICompatChat(system, model, api_key, GEMINI_BASE_URL)
    raise SystemExit(f"Unknown LLM_PROVIDER '{provider}'. Use anthropic, openai or gemini.")
