"""Boundary behavior: framing, safe protocol errors, and concurrent routing."""

import asyncio
import json
import time

import pytest

from workbench.rpc import DomainError, JsonLineDecoder, MAX_FRAME_BYTES, RpcRouter


def call(method="echo", *, id=1, params=None):
    request = {"jsonrpc": "2.0", "method": method, "id": id}
    if params is not None:
        request["params"] = params
    return request


def test_decoder_preserves_split_utf8_and_multiple_frames():
    decoder = JsonLineDecoder()
    wire = '{"method":"你好"}\n{"id":2}\n'.encode()
    split = wire.index("你".encode()) + 1
    assert decoder.feed(wire[:split]) == []
    assert decoder.feed(wire[split:]) == [{"method": "你好"}, {"id": 2}]


def test_decoder_accepts_exact_byte_limit():
    wire = b'{"value":"' + b"x" * (MAX_FRAME_BYTES - 12) + b'"}'
    assert len(wire) == MAX_FRAME_BYTES
    assert len(JsonLineDecoder().feed(wire + b"\n")[0]["value"]) == MAX_FRAME_BYTES - 12


def test_decoder_discards_oversize_until_newline_then_recovers():
    decoder = JsonLineDecoder()
    assert decoder.feed(b"x" * MAX_FRAME_BYTES) == []
    with pytest.raises(DomainError) as error:
        decoder.feed(b"x")
    assert error.value.code == -32600
    assert decoder.feed(b"ignored\n") == []
    assert decoder.feed(b'{"id":2}\n') == [{"id": 2}]


@pytest.mark.parametrize("wire", [b"\xff\n", b"{bad secret}\n", b'{"id":NaN}\n', b'{"x":Infinity}\n', b'{"x":1e999}\n', b"\n"])
def test_decoder_rejects_malformed_without_echo(wire):
    decoder = JsonLineDecoder()
    with pytest.raises(DomainError) as error:
        decoder.feed(wire)
    assert error.value.code == -32700
    assert "secret" not in str(error.value)
    assert decoder.feed(b'{"id":1}\n') == [{"id": 1}]


@pytest.mark.parametrize("payload", [[], {}, {"jsonrpc":"1.0","method":"echo"}, {"jsonrpc":"2.0","method":1}, call(id=True), call(id=[]), call(id=float("nan")), call(id=float("inf"))])
async def test_invalid_envelope_returns_null_id(payload):
    response = await RpcRouter().dispatch(payload)
    assert response["id"] is None
    assert response["error"]["code"] == -32600


async def test_notifications_null_and_numeric_ids_have_distinct_semantics():
    router = RpcRouter()
    router.register("echo", lambda value="ok": value)
    assert await router.dispatch({"jsonrpc":"2.0","method":"echo"}) is None
    assert await router.dispatch(call(id=None)) == {"jsonrpc":"2.0","id":None,"result":"ok"}
    for id in ["abc", 0, 1.5]:
        assert (await router.dispatch(call(id=id)))["id"] == id
    assert (await router.dispatch(call(params=["你好"]))) ["result"] == "你好"


@pytest.mark.parametrize("params", [None, True, "secret", 12])
async def test_illegal_params_are_safe(params):
    router = RpcRouter()
    router.register("echo", lambda: "ok")
    request = call()
    request["params"] = params
    response = await router.dispatch(request)
    assert response["error"] == {"code":-32602,"message":"Invalid params"}
    request.pop("id")
    assert await router.dispatch(request) is None


async def test_internal_source_cannot_be_spoofed_in_params():
    router = RpcRouter()
    router.register("private", lambda **kwargs: "allowed", internal=True)
    request = call("private", params={"source":"internal"})
    assert (await router.dispatch(request))["error"]["code"] == -32601
    assert (await router.dispatch(request, source="internal"))["result"] == "allowed"
    assert (await router.dispatch(call("missing")))["error"]["code"] == -32601


async def test_bad_signature_and_handler_exception_do_not_leak():
    router = RpcRouter()
    router.register("echo", lambda value: value)
    def broken():
        raise TypeError("secret-token")
    router.register("broken", broken)
    assert (await router.dispatch(call()))["error"]["code"] == -32602
    response = await router.dispatch(call("broken"))
    assert response["error"] == {"code":-32603,"message":"Internal error"}


@pytest.mark.parametrize("sync", [False, True])
async def test_slow_handler_does_not_block_ping(sync):
    router = RpcRouter()
    async def slow_async():
        await asyncio.sleep(.3)
        return "slow"
    def slow_sync():
        time.sleep(.3)
        return "slow"
    router.register("slow", slow_sync if sync else slow_async)
    router.register("ping", lambda: "ok")
    task = asyncio.create_task(router.dispatch(call("slow", id=1)))
    await asyncio.sleep(.02)
    response = await asyncio.wait_for(router.dispatch(call("ping", id=2)), .15)
    assert response["id"] == 2 and response["result"] == "ok"
    assert (await task)["result"] == "slow"


async def test_domain_error_is_structured_and_notifications_stay_silent():
    router = RpcRouter()
    def conflict():
        raise DomainError("REVISION_CONFLICT", "Revision changed", committed=False)
    router.register("save", conflict)
    response = await router.dispatch(call("save"))
    assert response["error"]["code"] == -32000
    assert response["error"]["data"]["code"] == "REVISION_CONFLICT"
    assert response["error"]["data"]["committed"] is False
    assert await router.dispatch({"jsonrpc": "2.0", "method": "save"}) is None
    assert await router.dispatch({"jsonrpc": "2.0", "method": "missing"}) is None


@pytest.mark.parametrize("result", [float("nan"), {"bad": object()}, "\ud800"])
async def test_invalid_handler_result_is_a_safe_internal_error(result):
    router = RpcRouter()
    router.register("broken", lambda: result)
    response = await router.dispatch(call("broken"))
    assert response["error"] == {"code": -32603, "message": "Internal error"}
