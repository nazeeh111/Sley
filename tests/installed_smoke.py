"""Run from outside the checkout after installing a wheel; Python -I supported."""
import http.client
import csv
import io
import json
from pathlib import Path
import threading
import time
import zipfile
import sys
import subprocess
import os
import sysconfig
from html.parser import HTMLParser

import sley

from sley.engine import example
from sley.server import make_server
from sley.wif import import_wif


class SheetTables(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tables, self.row, self.cell = [], None, None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr":
            self.row = []
        elif tag == "td":
            self.cell = ""

    def handle_data(self, text):
        if self.cell is not None:
            self.cell += text

    def handle_endtag(self, tag):
        if tag == "td":
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row:
            self.tables[-1].append(self.row)
            self.row = None


def main():
    installed_path = Path(sley.__file__).resolve()
    assert installed_path.is_relative_to(Path(sys.prefix).resolve()), installed_path
    assert not (Path.cwd() / "sley" / "__init__.py").exists(), "Run outside the source checkout"
    launcher = Path(sysconfig.get_path("scripts")) / ("sley.exe" if os.name == "nt" else "sley")
    subprocess.run([str(launcher), "--help"], check=True, capture_output=True)
    server = make_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(method, path, payload=None):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        headers = {"Host": server.expected_host}
        if method == "POST":
            headers.update(Origin=server.expected_origin, **{"Content-Type": "application/json"})
        connection.request(method,path,json.dumps(payload).encode() if payload is not None else None,headers)
        response = connection.getresponse()
        code,data=response.status,response.read()
        connection.close()
        return code,data
    try:
        for path in ("/", "/app.js", "/model.mjs", "/style.css", "/favicon.svg"):
            code,data=request("GET",path)
            assert code==200 and data, (path,code)
        code, data = request("GET", "/api/example")
        assert code == 200 and json.loads(data) == example()
        project = {"format": "sley-project", "version": 1, **example()}
        code, data = request("POST", "/api/project", {"project": json.dumps(project)})
        assert code == 200 and json.loads(data)["project"] == project | {"version": 2, "fixed_tie_up": [None] * 8}
        code, data = request("POST", "/api/import", {"wif": example()["wif"]})
        assert code == 200 and json.loads(data)["ends"] == 64
        code,data=request("POST","/api/solve",example());assert code==202
        job=json.loads(data)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            code,data=request("GET",f'/api/jobs/{job["job_id"]}')
            result=json.loads(data)
            if result["state"]!='running':break
            time.sleep(.02)
        assert result["state"]=='complete' and result["result"]["status"]=='feasible'
        assert request("POST","/api/export",job|{"digest":"0"*64})[0]==409
        code,data=request("POST","/api/export",job);assert code==200
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            assert set(archive.namelist())=={'adapted.wif','actions.csv','tie-up.html'}
            source=import_wif(example()['wif']);after=import_wif(archive.read('adapted.wif').decode())
            assert source.liftplan==after.liftplan and source.threading==after.threading
            assert after.sections["WIF"]["SOURCE VERSION"] == sley.__version__
            for name, block in source.blocks.items():
                if name not in {"WIF", "CONTENTS", "WEAVING", "TIEUP", "TREADLING", "LIFTPLAN"}:
                    assert after.blocks[name].rstrip("\n") == block.rstrip("\n"), name
            assert int(after.sections["WEAVING"]["TREADLES"]) == project["slot_count"]
            actions = list(csv.DictReader(io.StringIO(archive.read("actions.csv").decode())))
            assert len(actions) == len(source.liftplan)
            for action, pick in zip(actions, result["result"]["picks"], strict=True):
                assert int(action["pick"]) == pick["pick"]
                assert action["physical_slots"] == " ".join(map(str, pick["physical_slots"]))
                assert action["raised_shafts"] == " ".join(map(str, pick["raised_shafts"]))
                written = after.sections["TREADLING"][str(pick["pick"])]
                assert [int(t) for t in written.split(",") if int(t)] == pick["physical_slots"]
            sheet = archive.read("tie-up.html").decode()
            assert "WIF treadle numbers equal physical pedal positions" in sheet
            tables = SheetTables(sheet).tables
            assert tables == [
                [[str(row["physical_slot"]), ", ".join(map(str, row["raises"])) or "Untied"]
                 for row in result["result"]["tie_up"]],
                [[str(row["pick"]), ", ".join(map(str, row["physical_slots"])) or "No press",
                  ", ".join(map(str, row["raised_shafts"])) or "None"]
                 for row in result["result"]["picks"]],
            ]
        request("POST","/api/cancel",{"job_id":job['job_id']})
        assert request("POST","/api/export",job)[0]==409
        fixed = json.loads((installed_path.parent / "examples" / "fixed-pedals.sley.json").read_text())
        code, data = request("POST", "/api/project", {"project": json.dumps(fixed)})
        assert code == 200 and json.loads(data)["project"] == fixed
        assert request("POST", "/api/project", {"project": json.dumps(fixed | {"slot_count": None})})[0] == 400
        code, data = request("POST", "/api/import", {"wif": fixed["wif"]})
        assert code == 200 and json.loads(data)["source_tie_up"] == [[1], [2], []]
        code, data = request("POST", "/api/solve", {k: v for k, v in fixed.items() if k not in {"format", "version"}})
        assert code == 202
        job = json.loads(data)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            code, data = request("GET", f'/api/jobs/{job["job_id"]}')
            result = json.loads(data)
            if result["state"] != "running":
                break
            time.sleep(.02)
        assert result["state"] == "complete" and result["result"]["status"] == "feasible"
        assert result["result"]["declared_fixed_tie_up"] == [[1], None, []]
        code, data = request("POST", "/api/export", job)
        assert code == 200
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            after = import_wif(archive.read("adapted.wif").decode())
            assert after.sections["TIEUP"] == {"1": "1", "2": "2", "3": "0"}
            assert after.liftplan == [[1], [2], [1, 2], []]
            actions = list(csv.DictReader(io.StringIO(archive.read("actions.csv").decode())))
            assert [row["physical_slots"] for row in actions] == ["1", "2", "1 2", ""]
        print(f"Installed package: {installed_path}")
        print("Installed Sley launcher/assets, v1/v2 reopen, fixed/free import, worker solve, physical ZIP agreement and refusal checks passed")
    finally:
        server.calculator.close();server.shutdown();server.server_close();thread.join(timeout=3)


if __name__ == '__main__':
    main()
