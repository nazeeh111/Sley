"""Original finite rising-shed tie-up search with physical pair constraints.

Private mechanism probe. No WIF import, hardware control, or fitness claim.
"""
import argparse
import csv
import io
import itertools
import json
import time
from pathlib import Path


class LimitReached(Exception):
    pass


class Meter:
    def __init__(self, work_limit, seconds):
        if type(work_limit) is not int or not 1 <= work_limit <= 1_000_000:
            raise ValueError("work_limit must be an integer from 1 to 1000000")
        if type(seconds) not in (int, float) or not 0 < seconds <= 10:
            raise ValueError("seconds must be finite and from 0 to 10, excluding 0")
        self.limit = work_limit
        self.work = 0
        self.started = time.monotonic()
        self.deadline = self.started + seconds

    def charge(self):
        self.work += 1
        if self.work > self.limit or time.monotonic() >= self.deadline:
            raise LimitReached


def integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high}")
    return value


def shaft_set(value, shafts, name):
    if type(value) is not list or len(value) > shafts:
        raise ValueError(f"{name} must be a list of distinct shaft numbers")
    numbers = [integer(v, 1, shafts, name) for v in value]
    if len(set(numbers)) != len(numbers):
        raise ValueError(f"{name} repeats a shaft")
    return sum(1 << (v - 1) for v in numbers)


def validate(project):
    keys = {"model", "shafts", "threading", "slots", "allowed_pairs", "liftplan"}
    if type(project) is not dict or set(project) != keys:
        raise ValueError("project must contain exactly model, shafts, threading, slots, allowed_pairs, liftplan")
    if project["model"] != "rising_shed_union":
        raise ValueError("only explicit rising_shed_union semantics are supported")
    shafts = integer(project["shafts"], 1, 8, "shafts")
    threading = project["threading"]
    if type(threading) is not list or not 1 <= len(threading) <= 128:
        raise ValueError("threading must have 1 to 128 warp ends")
    for shaft in threading:
        integer(shaft, 1, shafts, "threading shaft")
    slots = project["slots"]
    if type(slots) is not list or not 1 <= len(slots) <= 10:
        raise ValueError("slots must have 1 to 10 physical pedals")
    for i, slot in enumerate(slots, 1):
        if type(slot) is not dict or set(slot) != {"id", "label"}:
            raise ValueError("each slot must contain exactly id and label")
        if integer(slot["id"], 1, 10, "slot id") != i:
            raise ValueError("slot ids must be consecutive physical positions starting at 1")
        if type(slot["label"]) is not str or not 1 <= len(slot["label"]) <= 32 or any(ord(c) < 32 for c in slot["label"]):
            raise ValueError("slot label must have 1 to 32 printable characters")
    pairs = project["allowed_pairs"]
    if type(pairs) is not list or len(pairs) > 45:
        raise ValueError("allowed_pairs must be a list with at most 45 pairs")
    normalized = set()
    for pair in pairs:
        if type(pair) is not list or len(pair) != 2:
            raise ValueError("each allowed pair must contain two physical slot ids")
        a, b = [integer(v, 1, len(slots), "paired slot") for v in pair]
        key = tuple(sorted((a - 1, b - 1)))
        if a == b or key in normalized:
            raise ValueError("allowed pairs must be distinct unordered pairs of different slots")
        normalized.add(key)
    lifts = project["liftplan"]
    if type(lifts) is not list or not 1 <= len(lifts) <= 128:
        raise ValueError("liftplan must contain 1 to 128 picks")
    masks = [shaft_set(v, shafts, "liftplan row") for v in lifts]
    return masks, tuple(sorted(normalized))


def numbers(mask):
    return [i + 1 for i in range(8) if mask & (1 << i)]


def actions(state, target, pairs):
    if target == 0:
        return ()
    for i, effect in enumerate(state):
        if effect == target:
            return (i,)
    for i, j in pairs:
        a, b = state[i], state[j]
        if a is not None and b is not None and a | b == target:
            return (i, j)
    return None


def solve(project, *, work_limit=500_000, seconds=5):
    masks, pairs = validate(project)
    meter = Meter(work_limit, seconds)
    target_masks = sorted(set(masks) - {0})
    candidates = set(target_masks)
    state_count = 0
    candidate_pairs = {}
    failed = set()
    try:
        # Closing under intersections is complete for this union model: enlarge
        # each used effect to the intersection of all lifts using that pedal.
        # Every old effect is contained in its replacement; each replacement
        # stays inside every lift using it. Actions and physical pairs stay fixed.
        pending = list(target_masks)
        while pending:
            a = pending.pop()
            for b in tuple(candidates):
                meter.charge()
                intersection = a & b
                if intersection and intersection not in candidates:
                    candidates.add(intersection)
                    pending.append(intersection)
        for target in target_masks:
            subset = sorted(c for c in candidates if c & target == c)
            unions = []
            for index, a in enumerate(subset):
                for b in subset[index:]:
                    meter.charge()
                    if a | b == target:
                        unions.append((a, b))
            candidate_pairs[target] = unions

        def extensions(state, target):
            options = set()
            for i, effect in enumerate(state):
                meter.charge()
                if effect is None:
                    updated = list(state)
                    updated[i] = target
                    options.add(tuple(updated))
            for i, j in pairs:
                for a, b in candidate_pairs[target]:
                    for x, y in ((a, b), (b, a)) if a != b else ((a, b),):
                        meter.charge()
                        if (state[i] is None or state[i] == x) and (state[j] is None or state[j] == y):
                            updated = list(state)
                            updated[i], updated[j] = x, y
                            options.add(tuple(updated))
            # Prefer small reusable effects, then avoid consuming spare slots.
            return sorted(options, key=lambda s: (
                sum(v.bit_count() ** 2 for v in s if v is not None),
                sum(v is not None for v in s), tuple(-1 if v is None else v for v in s)))

        def search(state):
            nonlocal state_count
            meter.charge()
            state_count += 1
            if state in failed:
                return None
            best = None
            for target in target_masks:
                meter.charge()
                if actions(state, target, pairs) is not None:
                    continue
                options = extensions(state, target)
                if not options:
                    failed.add(state)
                    return None
                if best is None or len(options) < len(best):
                    best = options
            if best is None:
                return state
            for updated in best:
                result = search(updated)
                if result is not None:
                    return result
            failed.add(state)
            return None

        found = search((None,) * len(project["slots"]))
        status = "feasible" if found is not None else "infeasible"
    except LimitReached:
        found, status = None, "unknown"
    report = {"status": status, "work": meter.work, "work_limit": meter.limit,
              "elapsed_seconds": time.monotonic() - meter.started,
              "unique_lifts": len(set(masks)), "candidate_effects": len(candidates),
              "search_states": state_count,
              "optimality": "not requested; fixed physical slot count",
              "semantics": "rising_shed_union"}
    if status != "feasible":
        return report
    state = tuple(0 if v is None else v for v in found)
    mapping = {physical + 1: logical for logical, physical in enumerate(
        (i for i, v in enumerate(state) if v), 1)}
    picks = []
    for pick, target in enumerate(masks, 1):
        pressed = actions(state, target, pairs)
        if pressed is None:
            raise AssertionError("internal solution omitted a lift")
        lifted = 0
        for i in pressed:
            lifted |= state[i]
        if lifted != target:
            raise AssertionError("internal solution changed a lift")
        picks.append({"pick": pick, "raised_shafts": numbers(target),
                      "physical_slots": [i + 1 for i in pressed],
                      "logical_treadles": [mapping[i + 1] for i in pressed]})
    original_drawdown = [[bool(mask & (1 << (shaft - 1))) for shaft in project["threading"]] for mask in masks]
    report.update({"tie_up": [{"physical_slot": i + 1, "label": slot["label"],
                              "logical_treadle": mapping.get(i + 1), "raises": numbers(state[i])}
                             for i, slot in enumerate(project["slots"])],
                   "logical_to_physical": {str(v): k for k, v in mapping.items()},
                   "picks": picks, "threading": project["threading"].copy(),
                   "drawdown": original_drawdown,
                   "preserves_all_lifts": True})
    return report


def duplicate_guard(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_project(path):
    with Path(path).open("rb") as stream:
        data = stream.read(32_769)
    if len(data) > 32_768:
        raise ValueError("project JSON exceeds 32768 bytes")
    def reject_float(value):
        raise ValueError("project numbers must be integers")
    def bounded_int(value):
        if len(value) > 3:
            raise ValueError("project integer lexeme exceeds 3 characters")
        return int(value)
    try:
        project = json.loads(data, object_pairs_hook=duplicate_guard,
                             parse_int=bounded_int, parse_float=reject_float,
                             parse_constant=reject_float)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError("project must be bounded valid UTF-8 JSON") from error
    validate(project)
    return project


def csv_actions(result):
    if result["status"] != "feasible":
        raise ValueError("only feasible plans have executable actions")
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["pick", "raised_shafts", "logical_treadles", "physical_slots"])
    for row in result["picks"]:
        writer.writerow([row["pick"], *[" ".join(map(str, row[k])) for k in
                                       ("raised_shafts", "logical_treadles", "physical_slots")]])
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--work-limit", type=int, default=500_000)
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--csv", type=Path, help="new output file; refused for Unknown/Infeasible")
    arguments = parser.parse_args()
    try:
        result = solve(load_project(arguments.project), work_limit=arguments.work_limit, seconds=arguments.seconds)
        if arguments.csv and result["status"] == "feasible":
            with arguments.csv.open("x", newline="") as stream:
                stream.write(csv_actions(result))
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "feasible" else 2
    except (ValueError, OSError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
