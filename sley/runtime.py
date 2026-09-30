"""One isolated operation at a time, with cancellable jobs and real deadlines."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import threading
import uuid

from .engine import prepare, public_result


class Busy(ValueError):
    pass


class Calculator:
    def __init__(self, *, deadline=15, command=None):
        self.deadline = deadline
        self.command = command or [sys.executable, "-I", str(Path(__file__).with_name("worker.py"))]
        self.lock = threading.RLock()
        self.active = None
        self.job = None
        self.closed = False
        self.exporting = False
        self.monitor = None

    def _spawn(self, request):
        child = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.active = child
        return child, json.dumps(request, separators=(",", ":"), ensure_ascii=False).encode()

    def _communicate(self, child, payload):
        try:
            output, _ = child.communicate(payload, timeout=self.deadline)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
            raise ValueError("Calculation exceeded the 15-second process deadline")
        if child.returncode or len(output) > 8 * 1024 * 1024:
            raise ValueError("Calculation process could not complete")
        result = json.loads(output)
        if "worker_error" in result:
            raise ValueError(result["worker_error"])
        return result

    def start(self, payload):
        _, payload, digest = prepare(**payload)
        with self.lock:
            if self.closed:
                raise ValueError("Local server is closing")
            if self.active is not None or self.exporting:
                raise Busy("A calculation is already running")
            job = {"job_id": uuid.uuid4().hex, "digest": digest, "state": "running", "payload": payload}
            child, raw = self._spawn({"operation": "solve", "payload": payload})
            self.job = job
            def monitor():
                try:
                    result = self._communicate(child, raw)
                    with self.lock:
                        if job["state"] == "running":
                            if self.active is child:
                                self.active = None
                            job.update(state="complete", result=result)
                except (OSError, ValueError) as error:
                    with self.lock:
                        if job["state"] == "running":
                            job.update(state="failed", error=str(error))
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.communicate()
                    with self.lock:
                        if self.active is child:
                            self.active = None
            self.monitor = threading.Thread(target=monitor, daemon=True)
            self.monitor.start()
            return {"job_id": job["job_id"], "digest": digest}

    def status(self, job_id):
        with self.lock:
            if self.job is None or self.job["job_id"] != job_id:
                raise ValueError("Unknown or expired calculation")
            response = {k: self.job[k] for k in ("state", "digest")}
            if "result" in self.job:
                response["result"] = public_result(self.job["result"])
            if "error" in self.job:
                response["error"] = self.job["error"]
            return response

    def cancel(self, job_id):
        with self.lock:
            if self.job is None or self.job["job_id"] != job_id:
                raise ValueError("Unknown or expired calculation")
            self.job["state"] = "cancelled"
            if self.active is not None and self.active.poll() is None:
                self.active.kill()
            self.job.pop("result", None)
            return {"state": self.job["state"]}

    def export(self, job_id, digest):
        with self.lock:
            job = self.job
            if self.closed:
                raise ValueError("Local server is closing")
            if self.active is not None or self.exporting:
                raise Busy("A calculation is already running")
            if job is None or job["job_id"] != job_id or job["digest"] != digest or job["state"] != "complete" or job["result"]["status"] != "feasible":
                raise ValueError("Export requires the current completed feasible result")
            self.exporting = True
            try:
                witness = {k: job["result"][k] for k in ("status", "declared_allowed_pairs", "tie_up", "picks")}
                child, payload = self._spawn({"operation": "export", "payload": job["payload"], "result": witness})
            except OSError:
                self.exporting = False
                raise
        try:
            result = self._communicate(child, payload)
            with self.lock:
                if job["state"] == "cancelled":
                    raise ValueError("Export was cancelled")
            return base64.b64decode(result["zip_base64"], validate=True)
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate()
            with self.lock:
                self.active = None
                self.exporting = False

    def close(self):
        with self.lock:
            self.closed = True
            child = self.active
            if child is not None and child.poll() is None:
                child.kill()
            if self.job and self.job["state"] == "running":
                self.job["state"] = "cancelled"
        if self.monitor:
            self.monitor.join(timeout=3)
        if child is not None:
            child.wait(timeout=3)
