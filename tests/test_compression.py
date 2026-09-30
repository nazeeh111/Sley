import hashlib
from pathlib import Path
import unittest

from sley.wif import import_wif, adapt, export_wif
from sley.engine import imported, prepare


def long_fixture(ends=1024, picks=2048, changed_final=False):
    source = (Path(__file__).parents[1] / "sley/examples/eight-shaft.wif").read_text()
    from sley.wif import parse_sections
    sections, blocks, preamble = parse_sections(source)
    text = preamble
    for name, block in blocks.items():
        if name == "WARP":
            block = block.replace("Threads=64", f"Threads={ends}")
        elif name == "WEFT":
            block = block.replace("Threads=64", f"Threads={picks}")
        elif name == "THREADING":
            block = "[THREADING]\n" + "".join(f"{i}={(i - 1) % 8 + 1}\n" for i in range(1, ends + 1) if i != ends)
        elif name == "LIFTPLAN":
            original = sections[name]
            block = "[LIFTPLAN]\n"
            for i in range(1, picks + 1):
                lift = original.get(str((i - 1) % 64 + 1), "0")
                if changed_final and i == picks:
                    lift = "1,3,5,7"
                block += f"{i}={lift}\n"
        text += block
    return text


class CompressionTests(unittest.TestCase):
    def test_long_indices_and_changed_final_pick(self):
        text = long_fixture(changed_final=True)
        document = import_wif(text)
        result = adapt(document, [{"id": i, "label": str(i)} for i in range(1, 9)],
                       [[i, j] for i in range(1, 5) for j in range(5, 9)])
        self.assertEqual(result["status"], "feasible")
        self.assertEqual(len(result["picks"]), 2048)
        self.assertEqual(result["picks"][-1]["pick"], 2048)
        self.assertEqual(result["picks"][-1]["raised_shafts"], [1, 3, 5, 7])
        self.assertEqual(document.threading[-1], 0)
        self.assertNotIn("drawdown", result)
        self.assertNotIn("full_wif_drawdown", result)
        reopened = import_wif(export_wif(document, result))
        self.assertEqual(reopened.threading, document.threading)
        self.assertEqual(reopened.liftplan, document.liftplan)
        self.assertEqual(reopened.blocks["THREADING"], document.blocks["THREADING"])

    def test_full_dimension_bound_and_search_repetition_cost(self):
        text = long_fixture(4096, 4096, changed_final=True)
        document = import_wif(text)
        slots = [{"id": i, "label": str(i)} for i in range(1, 9)]
        pairs = [[i, j] for i in range(1, 5) for j in range(5, 9)]
        result = adapt(document, slots, pairs)
        small = adapt(import_wif(long_fixture(128, 128, changed_final=True)), slots, pairs)
        self.assertEqual(result["status"], "feasible")
        self.assertEqual(result["work"], small["work"])
        self.assertEqual(len(result["picks"]), 4096)
        self.assertEqual(result["picks"][-1]["raised_shafts"], [1, 3, 5, 7])
        before = hashlib.sha256()
        for lift in document.liftplan:
            before.update(bytes(int(shaft > 0 and shaft in lift) for shaft in document.threading))
        self.assertEqual(result["drawdown_sha256"], before.hexdigest())
        reopened = import_wif(export_wif(document, result))
        self.assertEqual(reopened.threading, document.threading)
        self.assertEqual(reopened.liftplan, document.liftplan)

    def test_limits_refuse_not_trim(self):
        with self.assertRaisesRegex(ValueError, "4096"):
            import_wif(long_fixture(4097, 64))
        with self.assertRaisesRegex(ValueError, "4096"):
            import_wif(long_fixture(64, 4097))
        source = long_fixture(64, 129)
        prefix = source[:source.index("[LIFTPLAN]")]
        lifts = "[LIFTPLAN]\n" + "".join(f"{i}=" + ",".join(str(s + 1) for s in range(8) if i & (1 << s)) + "\n" for i in range(1, 130))
        with self.assertRaisesRegex(ValueError, "128 distinct"):
            prepare(prefix + lifts)

    def test_unknown_has_no_expanded_actions(self):
        document = import_wif(long_fixture())
        result = adapt(document, [{"id": i, "label": str(i)} for i in range(1, 9)],
                       [[i, j] for i in range(1, 5) for j in range(5, 9)], work_limit=1)
        self.assertEqual(result["status"], "unknown")
        self.assertNotIn("picks", result)
        with self.assertRaises(ValueError):
            export_wif(document, result)


if __name__ == "__main__":
    unittest.main()
