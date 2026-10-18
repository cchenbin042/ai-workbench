"""LF-framed JSON-RPC; stdout is owned exclusively by the service writer."""
import asyncio
from collections.abc import Callable
import inspect
import json
import logging
import math
import threading

from pydantic import ValidationError

from .contracts import DomainError, RpcRequest

MAX_FRAME_BYTES = 8 * 1024 * 1024
logger = logging.getLogger("workbench")


def error_response(code: int, message: str, request_id=None) -> dict:
    response = {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": code, "message": message}}
    try:
        encode_frame(response)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        response["id"] = None
    return response


def encode_frame(message: dict) -> bytes:
    wire = json.dumps(message, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(wire) > MAX_FRAME_BYTES:
        raise ValueError("FRAME_TOO_LARGE")
    return wire + b"\n"


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number")
    return number


def _invalid_constant(value: str):
    raise ValueError("Non-finite JSON number")


class JsonLineDecoder:
    def __init__(self):
        self._buffer = bytearray()
        self._discarding = False

    def feed(self, data: bytes) -> list[dict]:
        frames = []
        offset = 0
        while offset < len(data):
            newline = data.find(b"\n", offset)
            end = len(data) if newline < 0 else newline
            if self._discarding:
                if newline < 0:
                    return frames
                self._discarding = False
            elif len(self._buffer) + end - offset > MAX_FRAME_BYTES:
                self._buffer.clear()
                self._discarding = newline < 0
                raise DomainError(-32600, "FRAME_TOO_LARGE")
            else:
                self._buffer.extend(data[offset:end])
                if newline >= 0:
                    wire = bytes(self._buffer)
                    self._buffer.clear()
                    try:
                        value = json.loads(wire.decode("utf-8"), parse_float=_finite_float,
                                           parse_constant=_invalid_constant)
                        # Escaped lone surrogates also cannot travel on UTF-8 stdout.
                        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
                    except (ValueError, UnicodeError, RecursionError):
                        raise DomainError(-32700, "Parse error") from None
                    if not isinstance(value, dict):
                        raise DomainError(-32600, "Invalid Request")
                    frames.append(value)
            if newline < 0:
                break
            offset = newline + 1
        return frames

    def finish(self) -> None:
        partial = bool(self._buffer)
        self._buffer.clear()
        if partial:
            raise DomainError(-32700, "Parse error")


async def run_sync(function: Callable, *args, **kwargs):
    """Daemon workers let shutdown finish even if synchronous work cannot cancel."""
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def deliver(result, error):
        if not future.done():
            if error is None:
                future.set_result(result)
            else:
                future.set_exception(error)

    def invoke():
        result, error = None, None
        try:
            result = function(*args, **kwargs)
        except Exception as caught:
            error = caught
        try:
            loop.call_soon_threadsafe(deliver, result, error)
        except RuntimeError:
            pass  # The owning service has already stopped its event loop.

    threading.Thread(target=invoke, daemon=True, name="workbench-worker").start()
    return await future


class RpcRouter:
    def __init__(self):
        self._handlers = {}
        self._sync_slots = asyncio.Semaphore(16)

    def register(self, method: str, handler: Callable, *, internal: bool = False) -> None:
        if not method or method in self._handlers or not callable(handler):
            raise ValueError("Invalid or duplicate RPC registration")
        self._handlers[method] = (handler, internal, inspect.signature(handler))

    async def dispatch(self, request: dict, *, source: str = "bridge") -> dict | None:
        if not isinstance(request, dict):
            return error_response(-32600, "Invalid Request")
        notification = "id" not in request
        try:
            parsed = RpcRequest.model_validate(request)
        except ValidationError as error:
            if all(item["loc"] and item["loc"][0] == "params" for item in error.errors()):
                return None if notification else error_response(-32602, "Invalid params", request.get("id"))
            return error_response(-32600, "Invalid Request")
        if isinstance(parsed.id, str):
            try:
                parsed.id.encode("utf-8")
            except UnicodeError:
                return error_response(-32600, "Invalid Request")

        registration = self._handlers.get(parsed.method)
        if registration is None or (registration[1] and source != "internal"):
            return None if notification else error_response(-32601, "Method not found", parsed.id)
        handler, _, signature = registration
        args = parsed.params if isinstance(parsed.params, list) else []
        kwargs = parsed.params if isinstance(parsed.params, dict) else {}
        try:
            signature.bind(*args, **kwargs)
        except TypeError:
            return None if notification else error_response(-32602, "Invalid params", parsed.id)
        try:
            if inspect.iscoroutinefunction(handler):
                result = await handler(*args, **kwargs)
            else:
                # Bound sync workers; none are joined at interpreter shutdown.
                async with self._sync_slots:
                    result = await run_sync(handler, *args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            response = {"jsonrpc": "2.0", "id": parsed.id, "result": result}
            encode_frame(response)
        except DomainError as error:
            response = {"jsonrpc": "2.0", "id": parsed.id,
                        "error": error.error.model_dump(exclude_none=True)}
            try:
                encode_frame(response)
            except (TypeError, ValueError, UnicodeError, RecursionError):
                response = error_response(-32603, "Internal error", parsed.id)
        except Exception:
            logger.warning("RPC handler failed")
            response = error_response(-32603, "Internal error", parsed.id)
        return None if notification else response
