"""DeepSeek chat-completions client with bounded retries and redacted logging.

Only explicit 429/5xx responses with no received content are retried once.
Unknown disconnects and timeouts surface to the user for a manual decision;
the API key never enters logs, error messages, or result payloads.
"""
import asyncio
import json
import logging
import time

import httpx

from ..contracts import DomainError, ModelRequest, ModelResult

logger = logging.getLogger("workbench")

_sleep = asyncio.sleep  # Module-level seam so tests can fast-forward backoff.

RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRY_AFTER_SECONDS = 30.0


class _RetryableStatus(Exception):
    def __init__(self, error: DomainError, delay: float):
        self.error = error
        self.delay = delay


class DeepSeekClient:
    def __init__(self, endpoint: str, api_key: str, *, connect_timeout: float = 10.0,
                 idle_timeout: float = 60.0, total_timeout: float = 180.0, transport=None):
        if not api_key:
            raise DomainError("PROVIDER_NOT_CONFIGURED", "No API key is configured")
        self.endpoint = endpoint
        self.api_key = api_key
        self.connect_timeout = connect_timeout
        self.idle_timeout = idle_timeout
        self.total_timeout = total_timeout
        self._transport = transport

    def _build_body(self, request: ModelRequest) -> dict:
        body: dict = {"model": request.model_id, "stream": False,
                      "thinking": {"type": "disabled"},
                      "messages": [message.model_dump() for message in request.messages],
                      "max_tokens": request.max_tokens}
        if request.response_format is not None:
            body["response_format"] = request.response_format
        return body

    async def complete(self, request: ModelRequest, cancel: asyncio.Event) -> ModelResult:
        attempt = 0
        while True:
            attempt += 1
            try:
                return await asyncio.wait_for(self._attempt(request, cancel), self.total_timeout)
            except _RetryableStatus as retry:
                if attempt >= 2:
                    raise retry.error from None
                await _sleep(retry.delay)
            except TimeoutError:
                raise DomainError("PROVIDER_TIMEOUT",
                                  "The provider request timed out; retry manually if needed") from None
            except httpx.HTTPError:
                raise DomainError("PROVIDER_NETWORK",
                                  "The provider connection failed; retry manually if needed") from None

    async def _attempt(self, request: ModelRequest, cancel: asyncio.Event) -> ModelResult:
        started = time.monotonic()
        body = self._build_body(request)
        timeout = httpx.Timeout(self.idle_timeout, connect=self.connect_timeout,
                                write=30.0, pool=self.connect_timeout)
        async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
            post = asyncio.create_task(client.post(
                self.endpoint, json=body,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"}))
            cancelled = asyncio.create_task(cancel.wait())
            try:
                done, _ = await asyncio.wait({post, cancelled},
                                             return_when=asyncio.FIRST_COMPLETED)
                if cancelled in done and post not in done:
                    post.cancel()
                    await asyncio.gather(post, return_exceptions=True)
                    raise asyncio.CancelledError
                response = post.result()
            finally:
                cancelled.cancel()
                await asyncio.gather(cancelled, return_exceptions=True)

        if response.status_code in RETRYABLE_STATUSES:
            code = "RATE_LIMITED" if response.status_code == 429 else "PROVIDER_UNAVAILABLE"
            delay = _retry_delay(response)
            raise _RetryableStatus(DomainError(code, self._status_message(response.status_code)), delay)
        if response.status_code in (401, 403):
            raise DomainError("AUTH_FAILED",
                              "The provider rejected the configured key; check the API key settings")
        if response.status_code != 200:
            raise DomainError("PROVIDER_REQUEST_INVALID",
                              "The provider rejected the request configuration")

        try:
            payload = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise DomainError("PROVIDER_RESPONSE_INVALID",
                              "The provider returned a response that is not valid JSON") from None
        if not isinstance(payload, dict):
            raise DomainError("PROVIDER_RESPONSE_INVALID",
                              "The provider returned an unexpected response shape")
        choices = payload.get("choices") or []
        message = choices[0].get("message", {}) if choices else {}
        content = message.get("content") or ""
        finish_reason = choices[0].get("finish_reason") if choices else None
        if not isinstance(content, str) or content.strip() == "":
            raise DomainError("MODEL_EMPTY",
                              "The model returned no content; your input is preserved")
        if finish_reason == "length":
            raise DomainError("MODEL_TRUNCATED",
                              "The model output was cut off by the length limit")
        usage: dict[str, int] = {}
        for key, value in (payload.get("usage") or {}).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if value >= 0 and float(value).is_integer():
                usage[key] = int(value)
        request_id = payload.get("id") or response.headers.get("x-request-id") or "unknown"
        latency_ms = int((time.monotonic() - started) * 1000)
        logger.info("provider request completed: request_id=%s finish=%s latency_ms=%d usage=%s",
                    request_id, finish_reason, latency_ms, usage)
        return ModelResult(content=content, finish_reason=finish_reason or "stop",
                           request_id=str(request_id), usage=usage,
                           model=str(payload.get("model") or "unknown"))

    @staticmethod
    def _status_message(status: int) -> str:
        if status == 429:
            return "The provider is rate limiting; retry shortly"
        return "The provider is temporarily unavailable; retry manually if needed"


def _retry_delay(response: httpx.Response) -> float:
    raw = response.headers.get("retry-after")
    if raw is None:
        return 0.0
    try:
        return min(float(raw), MAX_RETRY_AFTER_SECONDS)
    except ValueError:
        return 0.0
