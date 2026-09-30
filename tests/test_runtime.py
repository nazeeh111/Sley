import io
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
