"""Validated public DTOs and deliberately safe RPC errors."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictFloat, StrictInt

NonEmptyStr = Annotated[str, Field(min_length=1)]
NonNegativeInt = Annotated[StrictInt, Field(ge=0)]
RpcId = StrictInt | StrictFloat | str | None


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class CommandMeta(Contract):
    operation_id: NonEmptyStr
    method: NonEmptyStr
    scope_id: NonEmptyStr
    expected_revision: NonNegativeInt | None = None


class ModelMessage(Contract):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ModelRequest(Contract):
    messages: Annotated[list[ModelMessage], Field(min_length=1)]
    model_id: NonEmptyStr
    response_format: dict[str, JsonValue] | None = None
    max_tokens: Annotated[StrictInt, Field(gt=0)] = 8000


class ModelResult(Contract):
    content: str
    finish_reason: NonEmptyStr
    request_id: NonEmptyStr
    usage: dict[str, NonNegativeInt]


class DomainErrorData(Contract):
    code: NonEmptyStr
    user_message: NonEmptyStr
    committed: StrictBool = False
    retryable: StrictBool = False


class RpcError(Contract):
    code: StrictInt
    message: NonEmptyStr
    data: DomainErrorData | None = None


class DomainError(Exception):
    """Only explicit user-facing messages may be exposed by business handlers."""

    def __init__(self, code: int | str, message: str, committed: bool = False):
        if type(code) is int:
            self.error = RpcError(code=code, message=message)
        else:
            data = DomainErrorData(code=code, user_message=message, committed=committed)
            self.error = RpcError(code=-32000, message="Application error", data=data)
        self.code = code
        self.message = message
        self.committed = committed
        super().__init__(message)


class RpcRequest(Contract):
    jsonrpc: Literal["2.0"]
    method: NonEmptyStr
    id: RpcId = None
    params: dict[str, JsonValue] | list[JsonValue] = Field(default_factory=dict)


class RpcSuccess(Contract):
    jsonrpc: Literal["2.0"] = "2.0"
    id: RpcId
    result: JsonValue


class RpcFailure(Contract):
    jsonrpc: Literal["2.0"] = "2.0"
    id: RpcId = None
    error: RpcError


class InitializeResult(Contract):
    protocol_version: Literal[1] = 1
    schema_version: Literal[0] = 0
    service_instance_id: NonEmptyStr
    capabilities: list[str]


class PingResult(Contract):
    ok: Literal[True] = True
    status: Literal["ok"] = "ok"
    service_instance_id: NonEmptyStr


class ShutdownResult(Contract):
    status: Literal["shutting_down"] = "shutting_down"


class WorkbenchRpcContract(Contract):
    command_meta: CommandMeta
    model_request: ModelRequest
    model_result: ModelResult
    request: RpcRequest
    response: RpcSuccess | RpcFailure
    initialize: InitializeResult
    ping: PingResult
    shutdown: ShutdownResult
