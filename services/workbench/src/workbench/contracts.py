"""Validated public DTOs and deliberately safe RPC errors."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictFloat, StrictInt, field_validator

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
    schema_version: NonNegativeInt = 0
    service_instance_id: NonEmptyStr
    capabilities: list[str]


class PingResult(Contract):
    ok: Literal[True] = True
    status: Literal["ok"] = "ok"
    service_instance_id: NonEmptyStr


class ShutdownResult(Contract):
    status: Literal["shutting_down"] = "shutting_down"


class GetDraftCommand(Contract):
    scope_id: Literal["local"]
    owner_type: Literal["local"]
    owner_id: Annotated[str, Field(min_length=1, max_length=128)]


class SaveDraftCommand(GetDraftCommand):
    operation_id: Annotated[str, Field(min_length=1, max_length=128)]
    expected_revision: NonNegativeInt | None = None
    content_json: dict[str, JsonValue]

    @field_validator("content_json")
    @classmethod
    def bounded_content(cls, value):
        import json
        content = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(content.encode("utf-8")) > 200000:
            raise ValueError("Draft content is too large")
        return value


class SaveDraftResult(Contract):
    draft_id: NonEmptyStr
    revision: Annotated[StrictInt, Field(gt=0)]
    saved_at: NonEmptyStr


class DraftResult(SaveDraftResult):
    scope_id: Literal["local"]
    owner_type: Literal["local"]
    owner_id: NonEmptyStr
    content_json: dict[str, JsonValue]


TaskStatus = Literal["draft", "queued", "running", "waiting_user", "cancelling",
                     "completed", "failed", "interrupted", "cancelled"]
WaitingReason = Literal["review_candidates", "answer_question", "verify_transcript",
                        "approve_tool", "review_artifact"]
TaskType = Literal["generic", "question_generation", "interview"]
ShortId = Annotated[str, Field(min_length=1, max_length=128)]


class CreateTaskCommand(Contract):
    operation_id: ShortId
    task_type: TaskType
    workspace_id: None = None
    agent_config_version_id: None = None
    material_version_ids: Annotated[list[str], Field(max_length=0)] = Field(default_factory=list)
    input: dict[str, JsonValue]

    @field_validator("input")
    @classmethod
    def bounded_input(cls, value):
        return SaveDraftCommand.bounded_content(value)


class GetTaskCommand(Contract):
    task_id: ShortId
    scope_id: Literal["local"] = "local"


class ChangeTaskCommand(GetTaskCommand):
    operation_id: ShortId
    expected_revision: NonNegativeInt | None = None


class TaskWriteCommand(ChangeTaskCommand):
    expected_revision: NonNegativeInt


class ContinueTaskCommand(TaskWriteCommand):
    action: WaitingReason
    input: dict[str, JsonValue]

    @field_validator("input")
    @classmethod
    def bounded_input(cls, value):
        return SaveDraftCommand.bounded_content(value)


class ListTasksCommand(Contract):
    scope_id: Literal["local"] = "local"
    status: TaskStatus | None = None
    limit: Annotated[StrictInt, Field(ge=1, le=200)] = 50
    offset: NonNegativeInt = 0


class ListEventsCommand(GetTaskCommand):
    after_seq: NonNegativeInt = 0
    limit: Annotated[StrictInt, Field(ge=1, le=200)] = 50


class GetOperationCommand(Contract):
    operation_id: ShortId
    scope_id: Literal["local"] = "local"


class TaskSnapshot(Contract):
    task_id: ShortId
    task_type: TaskType
    workspace_id: None
    agent_config_version_id: None
    input: dict[str, JsonValue]
    scope: dict[str, JsonValue]
    checkpoint: dict[str, JsonValue]
    status: TaskStatus
    waiting_reason: WaitingReason | None
    active_run_id: ShortId | None
    revision: Annotated[StrictInt, Field(gt=0)]
    last_seq: NonNegativeInt
    created_at: NonEmptyStr
    updated_at: NonEmptyStr


class TaskEvent(Contract):
    event_id: ShortId
    task_id: ShortId
    seq: Annotated[StrictInt, Field(gt=0)]
    run_id: ShortId | None
    service_instance_id: ShortId
    task_revision: Annotated[StrictInt, Field(gt=0)]
    type: NonEmptyStr
    payload: dict[str, JsonValue]
    created_at: NonEmptyStr


class WorkbenchRpcContract(Contract):
    create_task_command: CreateTaskCommand
    get_task_command: GetTaskCommand
    task_write_command: TaskWriteCommand
    continue_task_command: ContinueTaskCommand
    list_tasks_command: ListTasksCommand
    list_events_command: ListEventsCommand
    get_operation_command: GetOperationCommand
    task: TaskSnapshot
    task_event: TaskEvent
    save_draft_command: SaveDraftCommand
    get_draft_command: GetDraftCommand
    save_draft_result: SaveDraftResult
    draft: DraftResult
    command_meta: CommandMeta
    model_request: ModelRequest
    model_result: ModelResult
    request: RpcRequest
    response: RpcSuccess | RpcFailure
    initialize: InitializeResult
    ping: PingResult
    shutdown: ShutdownResult
