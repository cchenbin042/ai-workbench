"""Validated public DTOs and deliberately safe RPC errors."""
from typing import Annotated, Literal

from pydantic import (BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictFloat,
                      StrictInt, field_validator, model_validator)

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
    model: NonEmptyStr = "unknown"


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
WorkspaceName = Annotated[str, Field(min_length=1, max_length=100)]
WorkspaceTag = Annotated[str, Field(min_length=1, max_length=32)]
RelativePath = Annotated[str, Field(min_length=1, max_length=512)]


class CreateWorkspaceCommand(Contract):
    operation_id: ShortId
    name: WorkspaceName
    role_tags: Annotated[list[WorkspaceTag], Field(max_length=8)] = Field(default_factory=list)


class WorkspaceResult(Contract):
    workspace_id: ShortId
    name: NonEmptyStr
    role_tags: list[WorkspaceTag]
    revision: Annotated[StrictInt, Field(gt=0)]
    archived_at: str | None
    created_at: NonEmptyStr
    updated_at: NonEmptyStr


class WorkspaceListResult(Contract):
    items: list[WorkspaceResult]


class LinkDirectoryCommand(Contract):
    operation_id: ShortId
    workspace_id: ShortId
    grant_id: ShortId


class UnlinkDirectoryCommand(Contract):
    operation_id: ShortId
    workspace_id: ShortId
    link_id: ShortId


class ListDirectoryLinksCommand(Contract):
    workspace_id: ShortId


class DirectoryLinkResult(Contract):
    link_id: ShortId
    workspace_id: ShortId
    canonical_root: NonEmptyStr
    linked_at: NonEmptyStr
    removed_at: str | None


class ListDirectoryCommand(Contract):
    workspace_id: ShortId
    link_id: ShortId


class DirectoryEntry(Contract):
    relative_path: NonEmptyStr
    size_bytes: NonNegativeInt
    modified_at: NonEmptyStr


class DirectoryListingResult(Contract):
    link_id: ShortId
    canonical_root: NonEmptyStr
    entries: list[DirectoryEntry]
    truncated: StrictBool


class ImportEntry(Contract):
    relative_path: RelativePath
    encoding: str | None = None


class ImportFilesCommand(Contract):
    operation_id: ShortId
    workspace_id: ShortId
    grant_id: ShortId | None = None
    link_id: ShortId | None = None
    entries: Annotated[list[ImportEntry], Field(max_length=64)] = Field(default_factory=list)

    @model_validator(mode="after")
    def single_authorization(self):
        if (self.grant_id is None) == (self.link_id is None):
            raise ValueError("Provide exactly one of grant_id or link_id")
        return self


class ImportTextCommand(Contract):
    operation_id: ShortId
    workspace_id: ShortId | None = None
    display_name: Annotated[str, Field(min_length=1, max_length=200)]
    content_text: str


class MaterialVersionSummary(Contract):
    version_no: Annotated[StrictInt, Field(gt=0)]
    sha256: NonEmptyStr
    byte_size: NonNegativeInt
    encoding: NonEmptyStr
    line_count: NonNegativeInt
    read_at: NonEmptyStr


class MaterialSummary(Contract):
    material_id: ShortId
    workspace_id: ShortId | None
    kind: Literal["file", "text"]
    display_name: NonEmptyStr
    current_version: MaterialVersionSummary
    source_path: str | None


class MaterialDetail(MaterialSummary):
    content_text: str
    sha256: NonEmptyStr
    byte_size: NonNegativeInt
    encoding: NonEmptyStr
    line_count: NonNegativeInt
    version_no: Annotated[StrictInt, Field(gt=0)]
    read_at: NonEmptyStr
    source: dict[str, JsonValue]


class MaterialListResult(Contract):
    items: list[MaterialSummary]


class ListMaterialsCommand(Contract):
    workspace_id: ShortId


class GetMaterialCommand(Contract):
    workspace_id: ShortId | None = None
    material_id: ShortId


class ImportResult(Contract):
    materials: list[MaterialDetail]
    total_bytes: NonNegativeInt


class CheckFreshnessCommand(Contract):
    workspace_id: ShortId


class FreshnessItem(Contract):
    material_id: ShortId
    status: Literal["current", "changed", "missing", "snapshot_only"]
    source_path: str | None
    link_id: ShortId | None
    link_removed: StrictBool
    stored_size: NonNegativeInt | None
    observed_size: NonNegativeInt | None


class CheckFreshnessResult(Contract):
    items: list[FreshnessItem]


class PreviewFileCommand(Contract):
    workspace_id: ShortId
    link_id: ShortId
    relative_path: RelativePath


class PreviewResult(Contract):
    content_text: str
    sha256: NonEmptyStr
    encoding: NonEmptyStr
    byte_size: NonNegativeInt
    line_count: NonNegativeInt


class RegisterGrantCommand(Contract):
    kind: Literal["directory", "files"]
    path: str | None = None
    paths: Annotated[list[str], Field(max_length=64)] = Field(default_factory=list)


class GrantResult(Contract):
    grant_id: ShortId
    kind: Literal["directory", "files"]
    expires_at: NonEmptyStr
    root: str | None = None
    files: list[NonEmptyStr] = Field(default_factory=list)


ProviderKind = Literal["text"]


class GetProviderCommand(Contract):
    kind: ProviderKind


class UpdateProviderCommand(Contract):
    operation_id: ShortId
    kind: ProviderKind
    endpoint: Annotated[str, Field(min_length=1, max_length=2048)]
    model_id: Annotated[str, Field(min_length=1, max_length=128)]
    parameters: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def bounded_parameters(cls, value):
        import json
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 8192:
            raise ValueError("Provider parameters are too large")
        return value


class ProviderVersionResult(Contract):
    provider_id: ShortId
    kind: ProviderKind
    version_no: Annotated[StrictInt, Field(gt=0)]
    endpoint: NonEmptyStr
    model_id: NonEmptyStr
    parameters: dict[str, JsonValue]
    secret_ref: str | None
    has_secret: StrictBool
    created_at: NonEmptyStr


class ProviderListResult(Contract):
    items: list[ProviderVersionResult]


class SetProviderSecretCommand(Contract):
    operation_id: ShortId
    kind: ProviderKind
    secret: Annotated[str, Field(min_length=1, max_length=4096)]


class DeleteProviderSecretCommand(Contract):
    operation_id: ShortId
    kind: ProviderKind


class TestProviderCommand(Contract):
    operation_id: ShortId
    kind: ProviderKind


class ProviderTestResult(Contract):
    ok: StrictBool
    error_code: str | None
    latency_ms: NonNegativeInt | None
    model_id: str | None
    request_id: str | None
    usage: dict[str, NonNegativeInt]




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
    create_workspace_command: CreateWorkspaceCommand
    workspace: WorkspaceResult
    workspace_list: WorkspaceListResult
    link_directory_command: LinkDirectoryCommand
    unlink_directory_command: UnlinkDirectoryCommand
    list_directory_links_command: ListDirectoryLinksCommand
    directory_link: DirectoryLinkResult
    list_directory_command: ListDirectoryCommand
    directory_entry: DirectoryEntry
    directory_listing: DirectoryListingResult
    import_entry: ImportEntry
    import_files_command: ImportFilesCommand
    import_text_command: ImportTextCommand
    material_version_summary: MaterialVersionSummary
    material_summary: MaterialSummary
    material_detail: MaterialDetail
    material_list: MaterialListResult
    list_materials_command: ListMaterialsCommand
    get_material_command: GetMaterialCommand
    import_result: ImportResult
    check_freshness_command: CheckFreshnessCommand
    freshness_item: FreshnessItem
    check_freshness_result: CheckFreshnessResult
    preview_file_command: PreviewFileCommand
    preview_result: PreviewResult
    register_grant_command: RegisterGrantCommand
    grant_result: GrantResult
    get_provider_command: GetProviderCommand
    update_provider_command: UpdateProviderCommand
    provider_version_result: ProviderVersionResult
    provider_list: ProviderListResult
    set_provider_secret_command: SetProviderSecretCommand
    delete_provider_secret_command: DeleteProviderSecretCommand
    test_provider_command: TestProviderCommand
    provider_test_result: ProviderTestResult
