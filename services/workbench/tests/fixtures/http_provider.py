"""Controllable chat-completions HTTP stub for provider tests.

The stub never persists secrets: it only records request metadata in memory.
"""
import json

import httpx


class ScriptedProvider:
    """A scripted transport: each call consumes the next entry.

    Entries are either (status, body_dict) tuples or Exception instances to
    raise. The handler records method, path and whether an Authorization
    header was present, plus the parsed JSON body, without keeping secrets.
    """

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.requests = []
        self._auth_present = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self._auth_present.append("authorization" in request.headers)
        try:
            self.requests.append(json.loads(request.content.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.requests.append(None)
        self.calls += 1
        if not self.script:
            raise AssertionError("ScriptedProvider ran out of scripted responses")
        entry = self.script.pop(0)
        if isinstance(entry, Exception):
            raise entry
        status, body = entry
        return httpx.Response(status, json=body)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def auth_present(self) -> list[bool]:
        return list(self._auth_present)


def completion_body(content: str, *, finish_reason: str = "stop", model: str = "stub-model",
                    request_id: str = "stub-req-1", usage: dict | None = None) -> dict:
    return {
        "id": request_id,
        "object": "chat.completion",
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                     "finish_reason": finish_reason}],
        "usage": usage or {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
    }
