"""Explicit compare, choose and WIF export for change-aware adaptation."""
import argparse
import json
import os
import tempfile
from pathlib import Path

from .engine import MAX_BODY, MAX_WIF, constraints, parse_json
from .wif import adapt, export_wif, import_wif


def read_bounded(path, limit, name):
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{name} exceeds the {limit}-byte input limit")
    return data


def publish_new(path, text):
    """Close a complete owned sibling before exclusively publishing its inode."""
    descriptor, temporary = tempfile.mkstemp(prefix=".sley-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard-link creation is atomic and refuses an existing destination,
        # including a destination created after staging began.
        os.link(temporary, path)
    finally:
        os.unlink(temporary)


def print_comparison(result, choice):
    print(json.dumps({"selected": choice, "comparison": result,
                      "selected_objective": result.get("initial_objective") if choice == "initial" else result.get("objective")}, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(prog=f"{argparse.ArgumentParser().prog} compare", description=__doc__)
    parser.add_argument("wif", type=Path)
    parser.add_argument("constraints", type=Path, help="JSON: slot_count, allowed_pairs, existing_tie_up; optional fixed_tie_up")
    parser.add_argument("--work-limit", type=int, default=500_000)
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--choose", choices=("initial", "optimized"), default="optimized")
    parser.add_argument("--export", type=Path, help="write selected WIF to a new file")
    args = parser.parse_args(argv)
    try:
        config = parse_json(read_bounded(args.constraints, MAX_BODY, "constraints JSON"))
        required = {"slot_count", "allowed_pairs", "existing_tie_up"}
        if type(config) is not dict or set(config) not in (required, required | {"fixed_tie_up"}):
            raise ValueError("constraints require slot_count, allowed_pairs, existing_tie_up; optional fixed_tie_up")
        slots, pairs = constraints(config["slot_count"], config["allowed_pairs"])
        document = import_wif(read_bounded(args.wif, MAX_WIF, "WIF").decode("utf-8"))
        result = adapt(document, slots, pairs, fixed_tie_up=config.get("fixed_tie_up"),
                       existing_tie_up=config["existing_tie_up"], work_limit=args.work_limit, seconds=args.seconds)
        if result["status"] != "feasible":
            print_comparison(result, args.choose)
            return 2
        selected = result
        if args.choose == "initial":
            if result.get("initial_tie_up") is None:
                raise ValueError("no verified initial incumbent available")
            selected = adapt(document, slots, pairs, fixed_tie_up=result["initial_tie_up"], seconds=5)
        if args.export:
            output = export_wif(document, selected)
            publish_new(args.export, output)
        print_comparison(result, args.choose)
        return 0 if selected["status"] == "feasible" else 2
    except (OSError, ValueError, UnicodeError) as error:
        parser.exit(1, f"sley compare: {error}\n")
