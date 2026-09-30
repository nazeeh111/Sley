import copy
import io
import json
from pathlib import Path
import unittest
import zipfile

from sley.engine import prepare, solve_request, export_bundle, imported, validate_project
from sley.solver import solve
from sley.wif import import_wif


FIXTURE = '''[WIF]
Version=1.1
Date=April 20, 1997
Developers=Self-authored test
Source Program=Self-authored fixture
[CONTENTS]
WEAVING=true
WARP=true
WEFT=true
THREADING=true
TIEUP=true
TREADLING=true
[WEAVING]
Shafts=2
Treadles=3
Rising Shed=true
[WARP]
Threads=2
[WEFT]
Threads=4
[THREADING]
1=1
2=2
[TIEUP]
1=1
2=2
3=0
[TREADLING]
1=1
2=2
3=1,2
4=0
'''


def request():
    return {"wif": FIXTURE, "slot_count": 3, "allowed_pairs": [[1, 2]],
            "fixed_tie_up": [[1], None, []]}


class FixedTests(unittest.TestCase):
    def test_partial_setup_preserved_through_complete_export(self):
        payload = request()
        result = solve_request(payload)
        self.assertEqual(result['status'], 'feasible')
        self.assertEqual([row['raises'] for row in result['tie_up']], [[1], [2], []])
        self.assertEqual(result['declared_fixed_tie_up'], payload['fixed_tie_up'])
        self.assertEqual(imported(FIXTURE)['source_tie_up'], [[1], [2], []])
        with zipfile.ZipFile(io.BytesIO(export_bundle(payload, result))) as archive:
            output = import_wif(archive.read('adapted.wif').decode())
            self.assertEqual(output.sections['WIF']['SOURCE VERSION'], '0.2.0')
            self.assertEqual(output.liftplan, import_wif(FIXTURE).liftplan)
            self.assertEqual(output.sections['TIEUP']['1'], '1')
            self.assertEqual(output.sections['TIEUP']['3'], '0')
        result['tie_up'][2]['raises'] = [1]
        with self.assertRaisesRegex(ValueError, 'exact fixed'):
            export_bundle(payload, result)
        result['tie_up'][2]['raises'] = []
        # Same lifts do not license replacing an exact fixed column.
        changed = request() | {'fixed_tie_up': [None, None, [1]]}
        with self.assertRaises(ValueError):
            export_bundle(changed, result)

    def test_source_copy_uses_validated_numeric_rows(self):
        for source in (FIXTURE.replace('3=0', '3=0 ; no connection'),
                       FIXTURE.replace('[TIEUP]\n1=1', '[TIEUP]\n01=1')):
            self.assertEqual(imported(source)['source_tie_up'], [[1], [2], []])

    def test_export_checks_fixed_physical_id_not_row_order(self):
        payload = request()
        result = solve_request(payload)
        swapped = copy.deepcopy(result)
        for row in swapped['tie_up']:
            if row['physical_slot'] in (1, 2):
                row['physical_slot'] = 3 - row['physical_slot']
        for row in swapped['picks']:
            row['physical_slots'] = [3-s if s in (1, 2) else s for s in row['physical_slots']]
        with self.assertRaisesRegex(ValueError, 'exact fixed'):
            export_bundle(payload, swapped)
        duplicate = copy.deepcopy(result)
        duplicate['tie_up'][1]['physical_slot'] = 1
        with self.assertRaises(ValueError):
            export_bundle(payload, duplicate)

    def test_arbitrary_fixed_operands_and_budget(self):
        project = {'model': 'rising_shed_union', 'shafts': 3, 'threading': [1, 2, 3],
                   'slots': [{'id': i, 'label': str(i)} for i in range(1, 4)],
                   'allowed_pairs': [[1, 3], [2, 3]], 'liftplan': [[1, 2], [2, 3]],
                   'fixed_tie_up': [[1], [3], None]}
        result = solve(project)
        self.assertEqual(result['status'], 'feasible')
        self.assertEqual([r['raises'] for r in result['tie_up']], [[1], [3], [2]])
        self.assertEqual([r['physical_slots'] for r in result['picks']], [[1, 3], [2, 3]])
        impossible = project | {'fixed_tie_up': [[1], [3], []]}
        self.assertEqual(solve(impossible)['status'], 'infeasible')
        unknown = solve(project, work_limit=1)
        self.assertEqual(unknown['status'], 'unknown')
        self.assertNotIn('picks', unknown)

    def test_v1_migration_v2_roundtrip_and_strict_locks(self):
        legacy = {'format': 'sley-project', 'version': 1,
                  **{k: v for k, v in request().items() if k != 'fixed_tie_up'}}
        migrated = validate_project(json.dumps(legacy))
        self.assertEqual(migrated, legacy | {'version': 2, 'fixed_tie_up': [None] * 3})
        project = {'format': 'sley-project', 'version': 2, **request()}
        self.assertEqual(validate_project(json.dumps(project)), project)
        for locks in (None, [], [None]*4, [True, None, None], [[True], None, None],
                      [[1, 1], None, None], [[3], None, None], ['1', None, None]):
            with self.subTest(locks=locks), self.assertRaises(ValueError):
                prepare(**(request() | {'fixed_tie_up': locks}))
        original = prepare(**request())[2]
        free = prepare(**(request() | {'fixed_tie_up': [None]*3}))[2]
        fixed_empty = prepare(**(request() | {'fixed_tie_up': [[], None, []]}))[2]
        self.assertEqual(len({original, free, fixed_empty}), 3)
        self.assertEqual(prepare(**(request() | {'fixed_tie_up': [[2, 1], None, []]}))[2],
                         prepare(**(request() | {'fixed_tie_up': [[1, 2], None, []]}))[2])

    def test_explicit_null_pedal_count_refuses_projects_and_requests(self):
        for version in (1, 2):
            project = {"format": "sley-project", "version": version,
                       **request(), "slot_count": None}
            if version == 1:
                project.pop("fixed_tie_up")
            with self.subTest(version=version), self.assertRaises(ValueError):
                validate_project(json.dumps(project))
        with self.assertRaises(ValueError):
            prepare(**(request() | {"slot_count": None}))

    def test_unused_fixed_nonzero_pedal_survives_export(self):
        source = FIXTURE.replace("Shafts=2", "Shafts=3")
        payload = request() | {"wif": source, "fixed_tie_up": [[1], None, [3]]}
        result = solve_request(payload)
        self.assertEqual(result["status"], "feasible")
        self.assertTrue(all(3 not in row["physical_slots"] for row in result["picks"]))
        with zipfile.ZipFile(io.BytesIO(export_bundle(payload, result))) as archive:
            output = import_wif(archive.read("adapted.wif").decode())
            self.assertEqual(output.sections["TIEUP"]["3"], "3")
            self.assertNotIn("Unused positions remain untied", archive.read("tie-up.html").decode())
        result["tie_up"][2]["raises"] = []
        with self.assertRaisesRegex(ValueError, "exact fixed"):
            export_bundle(payload, result)
