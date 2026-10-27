import io
import os
import sys
import time
import unittest
import zipfile

from sley.engine import example
from sley.runtime import Calculator, Busy


def completed(calculator, identity, timeout=10):
    limit = time.monotonic() + timeout
    while time.monotonic() < limit:
        status = calculator.status(identity)
        if status["state"] != "running":
            return status
        time.sleep(0.02)
    raise AssertionError("job did not finish")


class RuntimeTests(unittest.TestCase):
    def test_deadline_and_cancel_interrupt_blocked_stdin(self):
        class BlockedInputCalculator(Calculator):
            def _spawn(self, request):
                child, payload = super()._spawn(request)
                communicate = child.communicate
                def blocked_input(input=None, timeout=None):
                    if input is not None:
                        # Reproduce the observed non-interruptible pipe write
                        # without depending on a platform's selector behavior.
                        try:
                            os.write(child.stdin.fileno(), b"x" * (2 * 1024 * 1024))
                        except BrokenPipeError:
                            pass
                    return communicate()
                child.communicate = blocked_input
                return child, payload

        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                calculator = BlockedInputCalculator(
                    deadline=0.15, command=[sys.executable, "-c", "import time;time.sleep(3)"])
                try:
                    started_at = time.monotonic()
                    started = calculator.start(example())
                    child = calculator.active
                    if cancel:
                        calculator.cancel(started["job_id"])
                    status = completed(calculator, started["job_id"], timeout=2)
                    self.assertEqual(status["state"], "cancelled" if cancel else "failed")
                    if not cancel:
                        self.assertIn("process deadline", status["error"])
                    calculator.monitor.join(timeout=1)
                    self.assertFalse(calculator.monitor.is_alive())
                    self.assertIsNotNone(child.poll())
                    self.assertIsNone(calculator.active)
                    self.assertLess(time.monotonic() - started_at, 2)
                finally:
                    calculator.close()

    def test_large_valid_input_and_process_error(self):
        payload = example()
        payload["wif"] = (";" + "\\" * 1000 + "\n") * 400 + payload["wif"]
        calculator = Calculator()
        try:
            started = calculator.start(payload)
            self.assertEqual(completed(calculator, started["job_id"])["state"], "complete")
            with zipfile.ZipFile(io.BytesIO(calculator.export(started["job_id"], started["digest"]))) as archive:
                self.assertIn("adapted.wif", archive.namelist())
            calculator.command = [sys.executable, "-c", "raise SystemExit(7)"]
            failed = calculator.start(example())
            status = completed(calculator, failed["job_id"])
            self.assertEqual(status["state"], "failed")
            self.assertIn("could not complete", status["error"])
            with self.assertRaises(ValueError):
                calculator.export(failed["job_id"], failed["digest"])
        finally:
            calculator.close()

    def test_real_worker_complete_export_and_digest_refusal(self):
        calculator = Calculator()
        try:
            started = calculator.start(example())
            result = completed(calculator, started["job_id"])
            self.assertEqual(result["state"], "complete")
            self.assertEqual(result["result"]["status"], "feasible")
            with self.assertRaises(ValueError):
                calculator.export(started["job_id"], "0" * 64)
            with zipfile.ZipFile(io.BytesIO(calculator.export(started["job_id"], started["digest"]))) as archive:
                self.assertIn("adapted.wif", archive.namelist())
            calculator.cancel(started["job_id"])
            with self.assertRaises(ValueError):
                calculator.export(started["job_id"], started["digest"])
        finally:
            calculator.close()

    def test_actual_timeout_and_cancel_reap_process(self):
        sleeping = [sys.executable, "-c", "import time;time.sleep(30)"]
        for cancel in (True, False):
            calculator = Calculator(deadline=0.15, command=sleeping)
            try:
                started = calculator.start(example())
                child = calculator.active
                with self.assertRaises(Busy):
                    calculator.start(example())
                if cancel:
                    self.assertEqual(calculator.cancel(started["job_id"])["state"], "cancelled")
                status = completed(calculator, started["job_id"])
                self.assertEqual(status["state"], "cancelled" if cancel else "failed")
                calculator.monitor.join(timeout=2)
                self.assertIsNotNone(child.poll())
                self.assertIsNone(calculator.active)
            finally:
                calculator.close()
