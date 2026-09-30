import csv
import io
import json
import unittest
import zipfile

from sley.engine import example, imported, solve_request, export_bundle, public_result, validate_project, parse_json, MAX_BODY, MAX_PROJECT
from sley.wif import import_wif


class EngineTests(unittest.TestCase):
    def test_original_to_complete_zip_and_metadata_escaping(self):
        request = example()
        request["wif"] = request["wif"].replace("Self-authored eight-shaft bank adaptation", "<script>alert(1)</script>")
        result = solve_request(request)
        public = public_result(result)
        self.assertNotIn("logical_to_physical", public)
        self.assertNotIn("drawdown", public)
        self.assertTrue(all(set(row) == {"pick", "physical_slots", "raised_shafts"} for row in public["picks"]))
        with zipfile.ZipFile(io.BytesIO(export_bundle(request, result))) as archive:
            self.assertEqual(set(archive.namelist()), {"adapted.wif", "actions.csv", "tie-up.html"})
            before, after = import_wif(request["wif"]), import_wif(archive.read("adapted.wif").decode())
            self.assertEqual(after.threading, before.threading)
            self.assertEqual(after.liftplan, before.liftplan)
            self.assertEqual(after.blocks["NOTES"], before.blocks["NOTES"])
            html = archive.read("tie-up.html").decode()
            self.assertNotIn("<script>", html)
            self.assertIn("&lt;script&gt;", html)
            rows = list(csv.DictReader(io.StringIO(archive.read("actions.csv").decode())))
            self.assertEqual(len(rows), len(before.liftplan))
            for row, pick in zip(rows, public["picks"], strict=True):
                self.assertEqual(row["physical_slots"], " ".join(map(str,pick["physical_slots"])))

    def test_project_roundtrip_and_duplicate_version_rejection(self):
        project = {"format": "sley-project", "version": 1, **example()}
        self.assertEqual(validate_project(json.dumps(project)), project)
        raw = json.dumps(project).replace('"version": 1', '"version": 1, "version": 1')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_project(raw)
        for change in ({"version": True}, {"version": 2}, {"slot_count": False}, {"allowed_pairs": [[1, 2], [2, 1]]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_project(json.dumps(project | change))

    def test_safe_expanded_colors_and_sparse_positions(self):
        source = example()["wif"]
        data = imported(source)
        self.assertEqual(len(data["warp_colors"]), 64)
        self.assertEqual(data["warp_colors"][0], "#e1daca")
        self.assertEqual(data["threading"][4], 0)
        self.assertEqual(data["liftplan"][6], [])
        alternate = imported(source.replace("5=3\n", "05=3\n"))
        self.assertEqual(alternate["warp_colors"], data["warp_colors"])

    def test_largest_wif_saved_project_escaped_envelope(self):
        request = example()
        remaining = 1024 * 1024 - 65536 - len(request["wif"].encode())
        comment = ";" + "\\" * 1000 + "\n"
        repetitions, final = divmod(remaining, len(comment))
        padding = comment * repetitions + (";" + "\\" * (final - 2) + "\n" if final >= 2 else "\n" * final)
        request["wif"] = padding + request["wif"]
        self.assertEqual(len(request["wif"].encode()), 1024 * 1024 - 65536)
        project = {"format": "sley-project", "version": 1, **request}
        raw_project = json.dumps(project)
        envelope = json.dumps({"project": raw_project}).encode()
        self.assertLess(len(envelope), MAX_BODY)
        decoded = parse_json(envelope)
        self.assertEqual(validate_project(decoded["project"]), project)
        with zipfile.ZipFile(io.BytesIO(export_bundle(request, solve_request(request)))) as archive:
            output = archive.read("adapted.wif").decode()
        self.assertLessEqual(len(output.encode()), 1024 * 1024)
        self.assertEqual(import_wif(output).liftplan, import_wif(request["wif"]).liftplan)

    def test_import_reserves_export_room_before_search(self):
        request = example()
        remaining = 1024 * 1024 - len(request["wif"].encode())
        line = ";" + "x" * 1000 + "\n"
        repeats, tail = divmod(remaining, len(line))
        padding = line * repeats + (";" + "x" * (tail - 2) + "\n" if tail >= 2 else "\n" * tail)
        request["wif"] = padding + request["wif"]
        from unittest.mock import patch
        with patch("sley.wif.solve", side_effect=AssertionError("solver called")):
            with self.assertRaisesRegex(ValueError, "insufficient room.*export"):
                solve_request(request)

    def test_maximum_raw_project_nested_envelope(self):
        project = {"format": "sley-project", "version": 1, **example()}
        raw = json.dumps(project)
        raw += "\t" * (MAX_PROJECT - len(raw.encode()))
        envelope = json.dumps({"project": raw}).encode()
        self.assertLess(len(envelope), MAX_BODY)
        self.assertGreater(len(envelope), 8 * 1024 * 1024)
        self.assertEqual(validate_project(parse_json(envelope)["project"]), project)
        with self.assertRaisesRegex(ValueError, "7 MiB"):
            validate_project(raw + " ")

    def test_export_refuses_changed_graph_and_physical_plan(self):
        request = example()
        result = solve_request(request)
        with self.assertRaises(ValueError):
            export_bundle(request | {"allowed_pairs": []}, result)
        result["picks"][0]["physical_slots"] = [1, 2]
        with self.assertRaises(ValueError):
            export_bundle(request, result)
