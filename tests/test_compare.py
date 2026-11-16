import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sley.compare import main, publish_new, read_bounded
from sley.engine import MAX_BODY, MAX_WIF
from test_fixed import FIXTURE


class CompareDeliveryTests(unittest.TestCase):
    def test_bounded_read_exact_and_over_both_format_caps(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            for cap in (MAX_BODY, MAX_WIF):
                with path.open("wb") as stream:
                    stream.truncate(cap)
                self.assertEqual(len(read_bounded(path, cap, "test")), cap)
                with path.open("ab") as stream:
                    stream.write(b"x")
                with self.assertRaisesRegex(ValueError, "input limit"):
                    read_bounded(path, cap, "test")
            # Prove the read itself is bounded, not merely the parsed result.
            with patch.object(Path, "open") as opened:
                opened.return_value.__enter__.return_value.read.return_value = b""
                read_bounded(path, MAX_WIF, "WIF")
                opened.return_value.__enter__.return_value.read.assert_called_once_with(MAX_WIF + 1)

    def test_nonfeasible_export_retains_structured_outcome_for_both_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source, config, output = [directory / name for name in ("input.wif", "constraints.json", "plan.wif")]
            source.write_text(FIXTURE)
            config.write_text(json.dumps({"slot_count": 3, "allowed_pairs": [[1, 2]], "existing_tie_up": [[], [], []]}))
            for status in ("unknown", "infeasible"):
                for choice in ("initial", "optimized"):
                    with patch("sley.compare.adapt", return_value={"status": status}), contextlib.redirect_stdout(io.StringIO()) as stdout:
                        code = main([str(source), str(config), "--choose", choice, "--export", str(output)])
                    self.assertEqual(code, 2)
                    self.assertEqual(json.loads(stdout.getvalue())["comparison"]["status"], status)
                    self.assertFalse(output.exists())

    def test_staging_failure_then_retry_and_existing_file_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            output = directory / "plan.wif"
            with patch("sley.compare.os.fsync", side_effect=OSError("injected late failure")):
                with self.assertRaisesRegex(OSError, "late failure"):
                    publish_new(output, "complete WIF")
            self.assertFalse(output.exists())
            self.assertEqual(list(directory.iterdir()), [])
            publish_new(output, "complete WIF")
            with self.assertRaises(FileExistsError):
                publish_new(output, "replacement")
            self.assertEqual(output.read_text(), "complete WIF")
            self.assertEqual(list(directory.iterdir()), [output])

    def test_concurrent_creation_survives_publication_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            output = directory / "plan.wif"
            import os
            link = os.link
            def competing_link(staged, final):
                Path(final).write_text("other writer")
                return link(staged, final)
            with patch("sley.compare.os.link", side_effect=competing_link):
                with self.assertRaises(FileExistsError):
                    publish_new(output, "our completed plan")
            self.assertEqual(output.read_text(), "other writer")
            self.assertEqual(list(directory.iterdir()), [output])

    def test_close_failure_leaves_no_final_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "plan.wif"
            import os
            fdopen = os.fdopen
            class FailClose:
                def __init__(self, *args, **kwargs):
                    self.stream = fdopen(*args, **kwargs)
                def __enter__(self):
                    return self.stream
                def __exit__(self, *args):
                    self.stream.close()
                    raise OSError("injected close failure")
            with patch("sley.compare.os.fdopen", side_effect=FailClose):
                with self.assertRaisesRegex(OSError, "close failure"):
                    publish_new(output, "complete")
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])
