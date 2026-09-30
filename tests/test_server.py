import http.client
import io
import json
import threading
import time
import unittest
import zipfile

from sley.engine import example
from sley.server import make_server


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.calculator.close()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def request(self, method, path, data=None, headers=None, raw=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        defaults = {"Host": self.server.expected_host}
        if method == "POST":
            defaults.update(Origin=self.server.expected_origin, **{"Content-Type": "application/json"})
        defaults.update(headers or {})
        body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
        connection.request(method, path, body=body, headers=defaults)
        response = connection.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return result

    def test_transport_gates_and_fixed_paths(self):
        for method, path, data, headers, status in [
            ("GET", "/api/example", None, {"Host": "localhost:9999"}, 403),
            ("POST", "/api/import", {"wif": example()["wif"]}, {"Origin": "https://example.org"}, 403),
            ("POST", "/api/import", {}, {"Content-Type": "text/plain"}, 415),
            ("GET", "/../engine.py", None, {}, 404),
            ("GET", "/model.test.mjs", None, {}, 404),
            ("GET", "/api/example?file=/etc/passwd", None, {}, 404),
            ("POST", "/api/import", {"wif": example()["wif"], "path": "anything"}, {}, 400),
            ("DELETE", "/api/example", None, {}, 405),
        ]:
            with self.subTest(method=method, path=path, headers=headers):
                self.assertEqual(self.request(method,path,data,headers)[0], status)
        status, body, headers = self.request("GET", "/api/example")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), example())
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_duplicate_json_project_and_raw_import_failures(self):
        self.assertEqual(self.request("POST", "/api/import", raw=b'{"wif":"x","wif":"y"}')[0], 400)
        self.assertEqual(self.request("POST", "/api/project", {"project": '{"version":1,"version":1}'})[0], 400)
        self.assertEqual(self.request("POST", "/api/import", {"wif": "invalid"})[0], 400)

    def test_actual_async_current_result_zip_and_cancel_refusal(self):
        payload = example()
        status, body, _ = self.request("POST", "/api/import", {"wif": payload["wif"]})
        self.assertEqual(status, 200)
        self.assertNotIn("drawdown", json.loads(body))
        status, body, _ = self.request("POST", "/api/solve", payload)
        self.assertEqual(status, 202)
        job = json.loads(body)
        limit = time.monotonic() + 8
        while time.monotonic() < limit:
            status, body, _ = self.request("GET", f'/api/jobs/{job["job_id"]}')
            result = json.loads(body)
            if result["state"] != "running":
                break
            time.sleep(0.02)
        self.assertEqual(result["state"], "complete")
        self.assertEqual(result["result"]["status"], "feasible")
        self.assertEqual(self.request("POST", "/api/export", job | {"digest": "0" * 64})[0], 409)
        status, body, _ = self.request("POST", "/api/export", job)
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertEqual(len(archive.namelist()), 3)
        self.assertEqual(self.request("POST", "/api/cancel", {"job_id": job["job_id"]})[0], 200)
        self.assertEqual(self.request("POST", "/api/export", job)[0], 409)
