"""Independent finite oracle: enumerate assignments and all legal actions."""
import itertools
import random
import unittest

from sley.optimize import optimize
from sley.wif import adapt, export_wif, import_wif
from test_fixed import FIXTURE


def oracle(project, old, weights):
    count, shafts = len(old), project["shafts"]
    best = None
    for state in itertools.product(range(1 << shafts), repeat=count):
        fixed = project.get("fixed_tie_up", [None] * count)
        if any(row is not None and set(row) != {s + 1 for s in range(shafts) if state[i] & (1 << s)} for i, row in enumerate(fixed)):
            continue
        paired = 0
        for lift, weight in zip(project["liftplan"], weights):
            target = set(lift)
            effects = [{s + 1 for s in range(shafts) if value & (1 << s)} for value in state]
            sizes = [0] if not target else []
            sizes += [1 for effect in effects if effect == target]
            sizes += [2 for a, b in project["allowed_pairs"] if effects[a - 1] | effects[b - 1] == target]
            if not sizes:
                break
            paired += weight * (min(sizes) == 2)
        else:
            changes = sum(len(set(row) ^ effect) for row, effect in zip(old, effects))
            score = changes, paired
            best = score if best is None else min(best, score)
    return best


def project(lifts, fixed=None):
    result = {"model": "rising_shed_union", "shafts": 2, "threading": [1, 2],
              "slots": [{"id": i, "label": str(i)} for i in range(1, 4)],
              "allowed_pairs": [[1, 2], [2, 3]], "liftplan": lifts}
    if fixed is not None:
        result["fixed_tie_up"] = fixed
    return result


class OptimizationTests(unittest.TestCase):
    def test_exhaustive_oracle_random_constraints_and_occurrences(self):
        rng = random.Random(501)
        for _ in range(80):
            old = [rng.choice([[], [1], [2], [1, 2]]) for _ in range(3)]
            p = project(rng.choices([[], [1], [2], [1, 2]], k=4),
                        [rng.choice([None, [], [1], [2], [1, 2]]) for _ in range(3)])
            weights = [rng.randint(1, 9) for _ in range(4)]
            expected = oracle(p, old, weights)
            result = optimize(p, old, pick_weights=weights)
            if expected is None:
                self.assertEqual(result["status"], "infeasible")
            else:
                self.assertEqual(result["optimality"], "proven")
                self.assertEqual(tuple(result["objective"]), expected)

    def test_budget_keeps_existing_verified_incumbent(self):
        p = project([[1], [2], [1, 2]])
        result = optimize(p, [[1], [2], []], work_limit=1)
        self.assertEqual(result["status"], "feasible")
        self.assertIn("not proven", result["optimality"])
        self.assertEqual(result["objective"], [0, 1])
        self.assertTrue(result["preserves_all_lifts"])
        unknown = optimize(p, [[], [], []], work_limit=1)
        self.assertEqual(unknown["status"], "unknown")
        self.assertNotIn("tie_up", unknown)

    def test_full_wif_occurrences_and_roundtrip(self):
        doc = import_wif(FIXTURE.replace('Threads=4', 'Threads=6').replace('4=0', '4=1,2\n5=1,2\n6=0'))
        slots = project([[1]])["slots"]
        result = adapt(doc, slots, [[1, 2]], existing_tie_up=[[1], [2], []])
        self.assertEqual(result["objective"], [0, 3])
        self.assertEqual(result["source_pick_occurrences"], 6)
        reopened = import_wif(export_wif(doc, result))
        self.assertEqual(reopened.liftplan, doc.liftplan)
        self.assertEqual(reopened.threading, doc.threading)

    def test_unused_existing_effect_not_replaced_by_intersection(self):
        result = optimize(project([[1]]), [[1], [1, 2], []])
        self.assertEqual(result["objective"], [0, 0])
        self.assertEqual(result["tie_up"][1]["raises"], [1, 2])

    def test_repetitions_choose_different_equal_change_optima(self):
        p = project([[1], [1, 2], [1, 3]])
        p["shafts"] = 3
        p["allowed_pairs"] = [[1, 2], [1, 3], [2, 3]]
        old = [[], [1, 2, 3], []]
        a = optimize(p, old, pick_weights=[9, 1, 1])
        b = optimize(p, old, pick_weights=[1, 1, 9])
        self.assertEqual(tuple(a["objective"]), oracle(p, old, [9, 1, 1]))
        self.assertEqual(tuple(b["objective"]), oracle(p, old, [1, 1, 9]))
        self.assertNotEqual(a["tie_up"], b["tie_up"])
        self.assertEqual(len(a["picks"][-1]["physical_slots"]), 2)
        self.assertEqual(len(b["picks"][-1]["physical_slots"]), 1)

    def test_invalid_existing_and_weights(self):
        for existing in ([[1], None, []], [[1], [2]]):
            with self.assertRaises(ValueError):
                optimize(project([[1]]), existing)
        with self.assertRaises(ValueError):
            optimize(project([[1]]), [[], [], []], pick_weights=[True])
