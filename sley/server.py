"""Loopback-only HTTP boundary with fixed assets and bounded JSON requests."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import socket

from .engine import MAX_BODY, exact_keys, parse_json, imported, prepare, example, validate_project
from .runtime import Calculator, Busy

PACKAGE = Path(__file__).parent
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/index.html": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/model.mjs": ("model.mjs", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}
POST_KEYS = {"/api/import": {"wif"}, "/api/project": {"project"},
             "/api/solve": {"wif", "slot_count", "allowed_pairs"}, "/api/cancel": {"job_id"},
             "/api/export": {"job_id", "digest"}}


class Handler(BaseHTTPRequestHandler):
    server_version = "Sley"

    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def log_message(self, format, *arguments):
        pass

    def send_bytes(self, status, data, content_type, headers=None):
        self.send_response(status)
        for key, value in {"Content-Type": content_type, "Content-Length": str(len(data)),
                           "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                           "Referrer-Policy": "no-referrer",
                           "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
                           **(headers or {})}.items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass

    def json(self, status, value):
        self.send_bytes(status, json.dumps(value, separators=(",", ":"), allow_nan=False).encode(), "application/json")

    def error(self, status, message):
        self.json(status, {"error": message})

    def trusted(self, require_origin=False):
        if self.headers.get_all("Host", []) != [self.server.expected_host]:
            self.error(403, "Use the printed local Sley URL")
            return False
        origins = self.headers.get_all("Origin", [])
        if (require_origin or origins) and origins != [self.server.expected_origin]:
            self.error(403, "Same-origin requests are required")
            return False
        return True

    def do_GET(self):
        if not self.trusted():
            return
        try:
            if self.path == "/api/example":
                self.json(200, example())
            elif match := re.fullmatch(r"/api/jobs/([a-f0-9]{32})", self.path):
                self.json(200, self.server.calculator.status(match[1]))
            elif self.path in STATIC:
                filename, content_type = STATIC[self.path]
                self.send_bytes(200, (PACKAGE / "static" / filename).read_bytes(), content_type)
            else:
                self.error(404, "Unknown endpoint")
        except ValueError as error:
            self.error(404, str(error))
        except OSError:
            self.error(503, "Packaged application asset is unavailable")

    def do_POST(self):
        if not self.trusted(require_origin=True):
            return
        if self.path not in POST_KEYS:
            self.error(404, "Unknown endpoint")
            return
        if self.headers.get_all("Content-Type", []) != ["application/json"]:
            self.error(415, "Use application/json")
            return
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get_all("Transfer-Encoding", []) or len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,8}", lengths[0]):
            self.error(400, "A single bounded Content-Length is required")
            return
        length = int(lengths[0])
        if length > MAX_BODY:
            self.error(413, "JSON request exceeds 16 MiB; source WIF limit is 1 MiB")
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Incomplete request body")
            request = parse_json(raw)
            expected = POST_KEYS[self.path]
            if self.path == "/api/solve" and type(request) is dict and "fixed_tie_up" in request:
                expected = expected | {"fixed_tie_up"}
            exact_keys(request, expected)
            if self.path == "/api/import":
                self.json(200, imported(request["wif"]))
            elif self.path == "/api/project":
                if type(request["project"]) is not str:
                    raise ValueError("project must be raw JSON text")
                self.json(200, {"project": validate_project(request["project"])})
            elif self.path == "/api/solve":
                self.json(202, self.server.calculator.start(request))
            else:
                if type(request["job_id"]) is not str or not re.fullmatch(r"[a-f0-9]{32}", request["job_id"]):
                    raise ValueError("Invalid calculation identifier")
                if self.path == "/api/cancel":
                    self.json(200, self.server.calculator.cancel(request["job_id"]))
                else:
                    if type(request["digest"]) is not str or not re.fullmatch(r"[a-f0-9]{64}", request["digest"]):
                        raise ValueError("Invalid input digest")
                    output = self.server.calculator.export(request["job_id"], request["digest"])
                    self.send_bytes(200, output, "application/zip", {"Content-Disposition": 'attachment; filename="sley-draft.zip"'})
        except Busy as error:
            self.error(429, str(error))
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as error:
            self.error(409 if self.path == "/api/export" else 400, str(error))
        except (socket.timeout, ConnectionResetError):
            self.error(408, "Request body was not received in time")
        except OSError:
            self.error(503, "Local calculation process could not start")

    def do_OPTIONS(self):
        self.error(405, "Use the documented GET and JSON POST endpoints")

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS


def make_server(port=0):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.expected_host = f"127.0.0.1:{server.server_address[1]}"
    server.expected_origin = f"http://{server.expected_host}"
    server.calculator = Calculator()
    return server
