"""Run the real schema CLI to verify reproducibility and drift exit codes."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
EXPORT = ROOT / "scripts" / "export-contracts.py"


def run_export(*args, cwd=None):
    return subprocess.run([sys.executable, str(EXPORT), *map(str, args)],
                          cwd=cwd, capture_output=True, text=True, timeout=15)


def test_export_detects_missing_changed_and_matching_schema(tmp_path):
    target = tmp_path / "contracts space" / "rpc.schema.json"
    assert run_export("--output", target, "--check").returncode == 1
    first = run_export("--output", target, cwd=tmp_path)
    assert first.returncode == 0, first.stderr
    schema = json.loads(target.read_text(encoding="utf-8"))
    assert "CommandMeta" in schema["$defs"]
    assert schema["$defs"]["InitializeResult"]["properties"]["protocol_version"]["const"] == 1
    assert run_export("--output", target, "--check").returncode == 0
    target.write_text("{}", encoding="utf-8")
    assert run_export("--output", target, "--check").returncode == 1
    assert target.read_text(encoding="utf-8") == "{}"
