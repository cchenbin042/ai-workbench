"""Public DTOs reject ambiguous types before persistence or model calls."""
import pytest
from pydantic import ValidationError
from workbench.contracts import CommandMeta, ModelRequest, ModelResult

@pytest.mark.parametrize("patch", [
    {"expected_revision": True}, {"expected_revision": "2"},
    {"expected_revision": -1}, {"operation_id": ""}, {"source": "internal"},
])
def test_command_meta_rejects_unsafe_input(patch):
    values = {"operation_id": "op-1", "method": "drafts.save", "scope_id": "ws-1"}
    with pytest.raises(ValidationError):
        CommandMeta(**(values | patch))

@pytest.mark.parametrize("patch", [
    {"max_tokens": True}, {"max_tokens": "10"}, {"max_tokens": 0},
    {"messages": []}, {"messages": [{"role": "unknown", "content": "x"}]},
    {"model_id": ""},
])
def test_model_request_rejects_unsafe_input(patch):
    values = {"messages": [{"role": "user", "content": "hello"}], "model_id": "test-model"}
    with pytest.raises(ValidationError):
        ModelRequest(**(values | patch))

@pytest.mark.parametrize("usage", [{"tokens": True}, {"tokens": "1"}, {"tokens": -1}])
def test_model_result_rejects_invalid_usage(usage):
    with pytest.raises(ValidationError):
        ModelResult(content="ok", finish_reason="stop", request_id="req-1", usage=usage)
