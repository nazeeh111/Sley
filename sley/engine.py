"""Bounded request validation, physical results and complete in-memory exports."""
import csv
import hashlib
import html
import io
import json
from pathlib import Path
import zipfile

from .solver import duplicate_guard, validate, fixed_assignments
from .wif import import_wif, adapt, export_wif, scalar, rows

MAX_BODY = 16 * 1024 * 1024  # Includes a 7 MiB project string escaped inside JSON.
MAX_PROJECT = 7 * 1024 * 1024
MAX_WIF = 1024 * 1024
CHECK_WORK = 500_000
_UNSET = object()


def exact_keys(value, expected, name="request"):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError(f"{name} requires exactly: {', '.join(sorted(expected))}")


def parse_json(raw):
    if type(raw) not in (str, bytes) or len(raw.encode() if isinstance(raw, str) else raw) > MAX_BODY:
        raise ValueError("JSON exceeds the 16 MiB envelope limit")
    def integer(token):
        if len(token) > 6:
            raise ValueError("JSON integer exceeds six characters")
        return int(token)
    def reject(token):
        raise ValueError("JSON numbers must be integers")
    try:
        return json.loads(raw, object_pairs_hook=duplicate_guard, parse_int=integer,
                          parse_float=reject, parse_constant=reject)
    except (RecursionError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid bounded JSON") from error


def constraints(count, pairs):
    if type(count) is not int or not 1 <= count <= 10:
        raise ValueError("physical pedal count must be from 1 to 10")
    slots = [{"id": i, "label": f"Pedal {i}"} for i in range(1, count + 1)]
    validate({"model": "rising_shed_union", "shafts": 1, "threading": [1],
              "slots": slots, "allowed_pairs": pairs, "liftplan": [[1]]})
    return slots, sorted([sorted(pair) for pair in pairs])


def prepare(wif, slot_count=_UNSET, allowed_pairs=None, fixed_tie_up=_UNSET):
    document = import_wif(wif)
    if len({tuple(lift) for lift in document.liftplan}) > 128:
        raise ValueError("supported limit: at most 128 distinct lift sets per draft")
    payload = {"wif": wif}
    if slot_count is not _UNSET:
        _, normalized = constraints(slot_count, allowed_pairs)
        fixed = fixed_assignments([None] * slot_count if fixed_tie_up is _UNSET else fixed_tie_up,
                                  slot_count, document.shafts)
        payload.update(slot_count=slot_count, allowed_pairs=normalized, fixed_tie_up=fixed)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    return document, payload, digest


def imported(wif):
    document, _, digest = prepare(wif)
    sections = document.sections
    table = sections.get("COLOR TABLE", {})
    if table:
        low, high = [scalar(v, 0, 65535, "Palette Range") for v in sections["COLOR PALETTE"]["RANGE"].split(",")]
        colors = {}
        for index, raw in table.items():
            channels = [scalar(v, low, high, "color channel") for v in raw.split(",")]
            colors[int(index)] = "#" + "".join(f"{((v - low) * 510 + high - low) // (2 * (high - low)):02x}" for v in channels)
    else:
        colors = {}
    def expanded(prefix, count, fallback):
        default = scalar(sections[prefix].get("COLOR", "0").split(",")[0], 0, 256, "default color")
        overrides = {scalar(k, 1, count, "color index"): scalar(v, 1, 256, "color override") for k, v in sections.get(f"{prefix} COLORS", {}).items()}
        return [colors.get(overrides.get(i, default), fallback) for i in range(1, count + 1)]
    return {"digest": digest, "title": sections.get("TEXT", {}).get("TITLE", "Untitled draft"),
            "shafts": document.shafts, "ends": len(document.threading), "picks": len(document.liftplan),
            "threading": document.threading, "liftplan": document.liftplan,
            "source_tie_up": (rows(sections["TIEUP"],
                                    scalar(sections["WEAVING"]["TREADLES"], 1, 64, "source treadles"),
                                    document.shafts, "TIEUP")
                               if document.mode == "tieup_treadling" else None),
            "warp_colors": expanded("WARP", len(document.threading), "#ddd9cf"),
            "weft_colors": expanded("WEFT", len(document.liftplan), "#394348")}


def validate_project(raw):
    if type(raw) is not str or len(raw.encode("utf-8")) > MAX_PROJECT:
        raise ValueError("project exceeds the 7 MiB UTF-8 file limit")
    project = parse_json(raw)
    if type(project) is not dict or project.get("format") != "sley-project" or type(project.get("version")) is not int or project["version"] not in (1, 2):
        raise ValueError("project requires format sley-project and version 1 or 2")
    keys = {"format", "version", "wif", "slot_count", "allowed_pairs"}
    exact_keys(project, keys if project["version"] == 1 else keys | {"fixed_tie_up"}, "project")
    fields = {k: v for k, v in project.items() if k not in {"format", "version"}}
    _, normalized, _ = prepare(**fields)
    return {"format": "sley-project", "version": 2, **normalized}


def solve_request(payload):
    document, normalized, _ = prepare(**payload)
    slots, pairs = constraints(normalized["slot_count"], normalized["allowed_pairs"])
    return adapt(document, slots, pairs, fixed_tie_up=normalized["fixed_tie_up"], work_limit=CHECK_WORK, seconds=5)


def public_result(result):
    response = {k: result[k] for k in ("status", "work", "work_limit", "elapsed_seconds")}
    response["declared_fixed_tie_up"] = result["declared_fixed_tie_up"]
    if result["status"] == "feasible":
        response["tie_up"] = [{"physical_slot": row["physical_slot"], "raises": row["raises"]} for row in result["tie_up"]]
        response["picks"] = [{k: row[k] for k in ("pick", "physical_slots", "raised_shafts")} for row in result["picks"]]
    return response


def export_bundle(payload, result):
    document, normalized, _ = prepare(**payload)
    if result["status"] != "feasible" or result["declared_allowed_pairs"] != normalized["allowed_pairs"]:
        raise ValueError("export requires the completed current feasible plan")
    if result.get("declared_fixed_tie_up") != normalized["fixed_tie_up"]:
        raise ValueError("fixed pedal assignments changed")
    count = normalized["slot_count"]
    rows_by_slot = {}
    for row in result["tie_up"]:
        slot = row["physical_slot"]
        if type(slot) is not int or not 1 <= slot <= count or slot in rows_by_slot:
            raise ValueError("plan must retain unique declared physical pedal positions")
        rows_by_slot[slot] = row
    if set(rows_by_slot) != set(range(1, count + 1)):
        raise ValueError("physical slot count changed")
    for slot, fixed in enumerate(normalized["fixed_tie_up"], 1):
        if fixed is not None and rows_by_slot[slot]["raises"] != fixed:
            raise ValueError("plan changed an exact fixed pedal assignment")
    wif = export_wif(document, result)
    actions = io.StringIO(newline="")
    writer = csv.writer(actions)
    writer.writerow(["pick", "raised_shafts", "physical_slots"])
    for row in result["picks"]:
        writer.writerow([row["pick"], " ".join(map(str, row["raised_shafts"])), " ".join(map(str, row["physical_slots"]))])
    title = html.escape(document.sections.get("TEXT", {}).get("TITLE", "Untitled draft"))
    sheet = f'<!doctype html><html lang="en"><meta charset="utf-8"><title>{title}</title><style>body{{font:14px system-ui;margin:2rem;color:#222}}table{{border-collapse:collapse;margin-bottom:2rem}}td,th{{border:1px solid #bbb;padding:.3rem .6rem;text-align:left}}@media print{{tr{{break-inside:avoid}}}}</style><h1>{title}</h1><p>WIF treadle numbers equal physical pedal positions. Fixed assignments remain exact, including pedals that are never pressed.</p><h2>Tie-up</h2><table><tr><th>Physical pedal</th><th>Raised shafts</th></tr>'
    for row in result["tie_up"]:
        sheet += f'<tr><td>{row["physical_slot"]}</td><td>{", ".join(map(str,row["raises"])) or "Untied"}</td></tr>'
    sheet += '</table><h2>Pressing sequence</h2><table><tr><th>Pick</th><th>Physical pedals</th><th>Raised shafts</th></tr>'
    for row in result["picks"]:
        sheet += f'<tr><td>{row["pick"]}</td><td>{", ".join(map(str,row["physical_slots"])) or "No press"}</td><td>{", ".join(map(str,row["raised_shafts"])) or "None"}</td></tr>'
    sheet += '</table></html>'
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("adapted.wif", wif)
        archive.writestr("actions.csv", actions.getvalue())
        archive.writestr("tie-up.html", sheet)
    return output.getvalue()


def example():
    return {"wif": (Path(__file__).with_name("examples") / "eight-shaft.wif").read_text(),
            "slot_count": 8, "allowed_pairs": [[i, j] for i in range(1, 5) for j in range(5, 9)]}
