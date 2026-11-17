"""Browser-bound admission and worker ownership use the existing exact optimizer."""
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

from sley.engine import export_bundle, prepare, public_result, solve_request, validate_project
from sley.runtime import Calculator
from sley.wif import import_wif
from test_fixed import request
from test_runtime import completed


def comparison():
    return json.loads((Path(__file__).parents[1] / 'sley/examples/change-aware.sley.json').read_text())


def payload(project):
    return {k: v for k, v in project.items() if k not in {'format', 'version'}}


class BrowserOptimizationTests(unittest.TestCase):
    def test_first_feasible_best_objective_and_full_export_preserve_source(self):
        source = comparison()
        result = solve_request(payload(source))
        visible = public_result(result)
        self.assertEqual(visible['initial_objective'], [4, 0])
        self.assertEqual(visible['objective'], [3, 1])
        self.assertEqual(visible['optimality'], 'proven')
        self.assertNotIn('initial_tie_up', visible)
        with zipfile.ZipFile(io.BytesIO(export_bundle(payload(source), result))) as archive:
            after = import_wif(archive.read('adapted.wif').decode())
        before = import_wif(source['wif'])
        self.assertEqual((after.threading, after.liftplan), (before.threading, before.liftplan))
        self.assertEqual(len(visible['picks']), 11)

    def test_project_v3_roundtrip_null_and_complete_setup_without_mutating_inputs(self):
        project = comparison()
        original = copy.deepcopy(project)
        self.assertEqual(validate_project(json.dumps(project)), original)
        self.assertEqual(project, original)
        project['existing_tie_up'] = None
        self.assertEqual(validate_project(json.dumps(project)), project)
        for existing in ([[], None, []], [[], []], [[False], [], []], [[4], [], []]):
            with self.subTest(existing=existing), self.assertRaises(ValueError):
                validate_project(json.dumps(project | {'existing_tie_up': existing}))

    def test_digest_includes_comparison_and_fixed_requirements(self):
        p = payload(comparison())
        _, _, first = prepare(**p)
        _, _, other = prepare(**(p | {'existing_tie_up': [[], [], []]}))
        plain = p.copy(); plain.pop('existing_tie_up')
        self.assertEqual(len({first, other, prepare(**plain)[2]}), 3)
        fixed = request() | {'existing_tie_up': [[], [], []]}
        result = solve_request(fixed)
        self.assertEqual([r['raises'] for r in result['tie_up']], [[1], [2], []])
        export_bundle(fixed, result)

    def test_budget_unknown_and_complete_infeasible_remain_distinct(self):
        p = request() | {'existing_tie_up': [[1], [2], []]}
        with patch('sley.engine.CHECK_WORK', 1):
            visible = public_result(solve_request(p))
        self.assertEqual(visible['status'], 'feasible')
        self.assertIn('not proven', visible['optimality'])
        p['existing_tie_up'] = [[], [], []]
        with patch('sley.engine.CHECK_WORK', 1):
            visible = public_result(solve_request(p))
        self.assertEqual(visible['status'], 'unknown')
        self.assertNotIn('tie_up', visible)
        p['fixed_tie_up'] = [[], [], []]
        visible = public_result(solve_request(p))
        self.assertEqual(visible['status'], 'infeasible')
        self.assertEqual(visible['optimality'], 'infeasible')

    def test_real_worker_compares_exports_and_invalidates_old_comparison(self):
        calculator = Calculator()
        try:
            p = payload(comparison())
            first = calculator.start(p)
            result = completed(calculator, first['job_id'])
            self.assertEqual(result['result']['objective'], [3, 1])
            self.assertTrue(calculator.export(first['job_id'], first['digest']).startswith(b'PK'))
            calculator.cancel(first['job_id'])
            with self.assertRaises(ValueError):
                calculator.export(first['job_id'], first['digest'])
            newer = calculator.start(p | {'existing_tie_up': [[], [], []]})
            completed(calculator, newer['job_id'])
            self.assertNotEqual(first['digest'], newer['digest'])
            with self.assertRaises(ValueError):
                calculator.export(first['job_id'], first['digest'])
        finally:
            calculator.close()
