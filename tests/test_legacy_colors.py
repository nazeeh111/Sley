import io
from pathlib import Path
import unittest
import zipfile

from sley.engine import export_bundle, imported, solve_request
from sley.wif import import_wif


SOURCE = Path(__file__).with_name("adacad-shaft-tabby.wif").read_text()


class LegacyColorsTests(unittest.TestCase):
    def test_editor_export_preserves_colors_and_physical_pedal_gap(self):
        before = imported(SOURCE)
        self.assertEqual(before["warp_colors"], ["#333333"] * 2)
        # AdaCAD writes Colors=1 here, but every weft uses palette entry 2.
        self.assertEqual(before["weft_colors"], ["#f9f8f3"] * 2)
        payload = {"wif": SOURCE, "slot_count": 3, "allowed_pairs": [[1, 3]],
                   "fixed_tie_up": [[1], [], None]}
        result = solve_request(payload)
        self.assertEqual(result["status"], "feasible")
        self.assertEqual([row["physical_slots"] for row in result["picks"]], [[1], [3]])
        with zipfile.ZipFile(io.BytesIO(export_bundle(payload, result))) as archive:
            output = archive.read("adapted.wif").decode()
        after = imported(output)
        for key in ("threading", "liftplan", "warp_colors", "weft_colors"):
            self.assertEqual(after[key], before[key], key)
        original, reopened = import_wif(SOURCE), import_wif(output)
        for name in ("WARP", "WEFT", "COLOR TABLE", "WARP COLORS", "WEFT COLORS"):
            self.assertEqual(reopened.blocks[name], original.blocks[name], name)
        self.assertEqual(reopened.sections["TIEUP"], {"1": "1", "2": "0", "3": "2"})

    def test_legacy_metadata_does_not_relax_other_import_checks(self):
        for source, error in (
            (SOURCE.replace("Colors=1", "ColorMix=1"), "unsupported WARP key"),
            (SOURCE.replace("[TIEUP]\n1=1\n2=2\n", ""), "CONTENTS disagrees"),
            (SOURCE.replace("2=249,248,243", "2=999,248,243"), "color channel"),
            (SOURCE.replace("Rising Shed=yes", "Rising Shed=no"), "sinking-shed"),
        ):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                imported(source)


if __name__ == "__main__":
    unittest.main()
