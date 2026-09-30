"""Isolated calculation entry point, usable from source or an installed wheel."""
import base64
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sley.engine import parse_json, solve_request, export_bundle, MAX_BODY


def main():
    raw = sys.stdin.buffer.read(MAX_BODY + 1)
    try:
        request = parse_json(raw)
        if request["operation"] == "solve":
            result = solve_request(request["payload"])
        elif request["operation"] == "export":
            result = {"zip_base64": base64.b64encode(export_bundle(request["payload"], request["result"])).decode()}
        else:
            raise ValueError("unknown calculation operation")
        sys.stdout.write(json.dumps(result, separators=(",", ":"), allow_nan=False))
        return 0
    except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
        sys.stdout.write(json.dumps({"worker_error": "The calculation input or export failed validation"}))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
