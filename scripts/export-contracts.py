"""Export Python DTOs deterministically; --check never rewrites the target."""
import argparse
import json
from pathlib import Path
import sys

from workbench.contracts import WorkbenchRpcContract

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Export workbench JSON Schema")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "contracts" / "rpc.schema.json")
    args = parser.parse_args()
    schema = WorkbenchRpcContract.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    exported = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + chr(10)
    if args.check:
        existing = args.output.read_text(encoding="utf-8") if args.output.is_file() else ""
        if existing != exported:
            print("Contract schema drift detected; run scripts/export-contracts.py", file=sys.stderr)
            return 1
        print("Contract schema matches")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(exported, encoding="utf-8", newline=chr(10))
    print("Contract schema exported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
