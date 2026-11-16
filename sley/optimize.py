"""Bounded exact lexicographic search over physical shaft-pedal connections."""
import time

from .solver import (LimitReached, Meter, actions, attach_plan, fixed_assignments,
                     shaft_set, solve, validate)


def optimize(project, existing_tie_up, *, pick_weights=None, work_limit=500_000, seconds=5):
    """Minimize connection edits first, then pair presses over all occurrences.

    Unlike feasibility intersection closure, all shaft subsets must be retained:
    an unused connection can save an edit from the declared existing tie-up.
    """
    masks, pairs = validate(project)
    count, shafts = len(project["slots"]), project["shafts"]
    existing = fixed_assignments(existing_tie_up, count, shafts)
    if any(row is None for row in existing):
        raise ValueError("existing_tie_up must declare every pedal; use [] for untied")
    old = tuple(shaft_set(row, shafts, "existing pedal") for row in existing)
    fixed = fixed_assignments(project.get("fixed_tie_up", [None] * count), count, shafts)
    locks = tuple(None if row is None else shaft_set(row, shafts, "fixed pedal") for row in fixed)
    weights = [1] * len(masks) if pick_weights is None else pick_weights
    if type(weights) is not list or len(weights) != len(masks) or any(type(w) is not int or not 1 <= w <= 4096 for w in weights) or sum(weights) > 4096:
        raise ValueError("pick_weights must contain positive occurrence counts totaling at most 4096")
    meter = Meter(work_limit, seconds)
    weights_by_mask = {}
    for mask, weight in zip(masks, weights):
        weights_by_mask[mask] = weights_by_mask.get(mask, 0) + weight

    def score(state):
        pair_count = 0
        for target, weight in weights_by_mask.items():
            pressed = actions(state, target, pairs)
            if pressed is None:
                return None
            pair_count += weight * (len(pressed) == 2)
        return sum((a ^ b).bit_count() for a, b in zip(state, old)), pair_count

    incumbent = old if all(v is None or v == old[i] for i, v in enumerate(locks)) and score(old) is not None else None
    best = score(incumbent) if incumbent is not None else None
    # Seed with the existing fast feasibility solver. Its complete search remains
    # authoritative for infeasibility; an interrupted optimization never is.
    seed = None
    if incumbent is None:
        seed = solve(project, work_limit=work_limit, seconds=seconds)
        meter.work = seed["work"]
        if seed["status"] == "feasible":
            incumbent = tuple(shaft_set(row["raises"], shafts, "solution") for row in seed["tie_up"])
            best = score(incumbent)
        elif seed["status"] == "infeasible":
            seed.update(optimality="infeasible", objective=None)
            return seed
    baseline = best
    initial_state = incumbent
    states = 0
    complete = False
    domains = [([lock] if lock is not None else sorted(range(1 << shafts), key=lambda v: ((v ^ old[i]).bit_count(), v))) for i, lock in enumerate(locks)]
    minimum_tail = [0] * (count + 1)
    for i in range(count - 1, -1, -1):
        minimum_tail[i] = minimum_tail[i + 1] + min((v ^ old[i]).bit_count() for v in domains[i])

    def visit(prefix, edits):
        nonlocal incumbent, best, states
        meter.charge()
        states += 1
        lower = edits + minimum_tail[len(prefix)]
        if best is not None and (lower > best[0] or (lower == best[0] and best[1] == 0)):
            return
        if len(prefix) == count:
            candidate = score(prefix)
            if candidate is not None and (best is None or candidate < best):
                incumbent, best = tuple(prefix), candidate
            return
        for value in domains[len(prefix)]:
            visit((*prefix, value), edits + (value ^ old[len(prefix)]).bit_count())

    try:
        visit((), 0)
        complete = True
    except LimitReached:
        pass
    report = {"status": "feasible" if incumbent is not None else "unknown", "work": meter.work,
              "work_limit": meter.limit, "elapsed_seconds": time.monotonic() - meter.started,
              "search_states": states, "unique_lifts": len(set(masks)),
              "candidate_effects": 1 << shafts, "semantics": "rising_shed_union",
              "declared_fixed_tie_up": fixed, "declared_existing_tie_up": existing,
              "optimality": "proven" if complete else "not proven; budget exhausted",
              "objective_order": ["connection_changes", "paired_pick_occurrences"],
              "objective": list(best) if best is not None else None,
              "initial_objective": list(baseline) if baseline is not None else None,
              "objective_lower_bound": [minimum_tail[0], 0],
              "source_pick_occurrences": sum(weights)}
    if incumbent is None:
        return report
    report["initial_tie_up"] = [list(row) for row in existing] if initial_state == old else ([row["raises"] for row in seed["tie_up"]] if seed else None)
    return attach_plan(project, report, incumbent, masks, pairs)
