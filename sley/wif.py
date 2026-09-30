"""Bounded WIF preservation and distinct-lift adaptation with physical numbering."""
from dataclasses import dataclass
import hashlib
import re

from .solver import solve
from . import __version__


CONTROL = {"WIF", "CONTENTS", "WEAVING", "TIEUP", "TREADLING", "LIFTPLAN"}
INDEPENDENT = {"TEXT", "NOTES", "THREADING", "WARP", "WEFT", "COLOR PALETTE", "COLOR TABLE",
               "WARP SYMBOL PALETTE", "WEFT SYMBOL PALETTE", "WARP SYMBOL TABLE", "WEFT SYMBOL TABLE"}
for prefix in ("WARP", "WEFT"):
    INDEPENDENT.update(f"{prefix} {suffix}" for suffix in
                       ("COLORS", "SYMBOLS", "THICKNESS", "THICKNESS ZOOM", "SPACING", "SPACING ZOOM"))


@dataclass
class Document:
    sections: dict
    blocks: dict
    preamble: str
    shafts: int
    threading: list
    liftplan: list
    mode: str


def scalar(value, low, high, name):
    token = value.split(";", 1)[0].strip()
    if not re.fullmatch(r"[0-9]{1,6}", token):
        raise ValueError(f"{name}: expected a bounded nonnegative integer")
    number = int(token)
    if not low <= number <= high:
        raise ValueError(f"{name}: outside {low}..{high}")
    return number


def boolean(value, name):
    token = value.split(";", 1)[0].strip().lower()
    if token in {"true", "on", "yes", "1"}:
        return True
    if token in {"false", "off", "no", "0"}:
        return False
    raise ValueError(f"{name}: invalid boolean")


def rows(values, count, maximum, name):
    result = [[] for _ in range(count)]
    seen = set()
    for key, value in values.items():
        index = scalar(key, 1, count, f"{name} index")
        if index in seen:
            raise ValueError(f"{name}: repeated numeric index")
        seen.add(index)
        raw = value.split(";", 1)[0].strip()
        if not raw:
            continue
        tokens = raw.split(",")
        if len(tokens) > maximum + 1:
            raise ValueError(f"{name}: too many entries")
        numbers = [scalar(v, 0, maximum, f"{name} value") for v in tokens]
        # Shaft/treadle zero means no connection, including alongside real ids.
        positive = [v for v in numbers if v]
        if len(set(positive)) != len(positive):
            raise ValueError(f"{name}: repeated nonzero entry")
        result[index - 1] = sorted(positive)
    return result


def parse_sections(text):
    if type(text) is not str or len(text.encode("utf-8")) > 1_048_576:
        raise ValueError("WIF exceeds the 1048576-byte supported-profile limit")
    if text.startswith("\ufeff"):
        text = text[1:]
    sections, blocks, preamble = {}, {}, []
    current = None
    lines = text.splitlines(keepends=True)
    if len(lines) > 32768:
        raise ValueError("WIF exceeds 32768 lines")
    for line in lines:
        if len(line) > 2048 or "\x00" in line:
            raise ValueError("WIF line exceeds 2048 characters or contains NUL")
        stripped = line.strip()
        if stripped.startswith("["):
            match = re.fullmatch(r"\[([^\[\]]{1,64})\]", stripped)
            if match is None:
                raise ValueError("invalid WIF section header")
            current = match[1].strip().upper()
            if current in sections:
                raise ValueError(f"duplicate section: {current}")
            if current not in CONTROL | INDEPENDENT:
                raise ValueError(f"unsupported section with unverified semantics: {current}")
            sections[current], blocks[current] = {}, [line]
            continue
        if current is None:
            if stripped and not stripped.startswith(";"):
                raise ValueError("only comments/whitespace are allowed before the first section")
            preamble.append(line)
            continue
        blocks[current].append(line)
        if not stripped or stripped.startswith(";"):
            continue
        if "=" not in line:
            raise ValueError(f"{current}: expected Key=value")
        key, value = line.split("=", 1)
        key = key.strip().upper()
        if not key or len(key) > 64 or key in sections[current]:
            raise ValueError(f"{current}: empty, oversized or duplicate key")
        sections[current][key] = value.strip()
    return sections, {k: "".join(v) for k, v in blocks.items()}, "".join(preamble)


def import_wif(text):
    sections, blocks, preamble = parse_sections(text)
    for required in ("WIF", "CONTENTS", "WEAVING", "WARP", "WEFT", "THREADING"):
        if required not in sections:
            raise ValueError(f"missing required supported-profile section: {required}")
    header = sections["WIF"]
    if header.get("VERSION") != "1.1" or any(k not in header for k in ("DATE", "DEVELOPERS", "SOURCE PROGRAM")):
        raise ValueError("WIF identity requires Version=1.1, Date, Developers and Source Program")
    contents = sections["CONTENTS"]
    for name, value in contents.items():
        present = name in sections
        if boolean(value, f"CONTENTS {name}") != present:
            raise ValueError(f"CONTENTS disagrees with section presence: {name}")
    for name in sections.keys() - {"WIF", "CONTENTS"}:
        if name not in contents:
            raise ValueError(f"section not declared in CONTENTS: {name}")
    weaving = sections["WEAVING"]
    if set(weaving) - {"SHAFTS", "TREADLES", "RISING SHED"}:
        raise ValueError("unsupported WEAVING key")
    try:
        shafts = scalar(weaving["SHAFTS"], 1, 8, "Shafts")
        treadles = scalar(weaving["TREADLES"], 0, 64, "Treadles")
        if not boolean(weaving["RISING SHED"], "Rising Shed"):
            raise ValueError("sinking-shed input is unsupported; no automatic complement")
        ends = scalar(sections["WARP"]["THREADS"], 1, 4096, "Warp Threads")
        picks = scalar(sections["WEFT"]["THREADS"], 1, 4096, "Weft Threads")
    except KeyError as error:
        raise ValueError(f"missing explicit structure key: {error.args[0]}") from error
    warp_keys = {"THREADS", "COLOR", "SYMBOL NUMBER", "SYMBOL NUMBER ZOOM", "UNITS", "SPACING",
                 "SPACING ZOOM", "THICKNESS", "THICKNESS ZOOM"}
    for name in ("WARP", "WEFT"):
        if set(sections[name]) - warp_keys:
            raise ValueError(f"unsupported {name} key")
    threaded = rows(sections["THREADING"], ends, shafts, "THREADING")
    if any(len(v) > 1 for v in threaded):
        raise ValueError("multiple-shaft threading is outside this adapter's supported profile")
    threading = [v[0] if v else 0 for v in threaded]
    if not any(threading):
        raise ValueError("at least one threaded warp end is required by the adapter")
    if "LIFTPLAN" in sections:
        if "TIEUP" in sections or "TREADLING" in sections:
            raise ValueError("ambiguous control paths: liftplan and tie-up/treadling both present")
        liftplan = rows(sections["LIFTPLAN"], picks, shafts, "LIFTPLAN")
        mode = "liftplan"
    else:
        if not treadles or not {"TIEUP", "TREADLING"} <= sections.keys():
            raise ValueError("provide either liftplan or both tie-up and treadling")
        tie_up = rows(sections["TIEUP"], treadles, shafts, "TIEUP")
        treadling = rows(sections["TREADLING"], picks, treadles, "TREADLING")
        liftplan = [sorted(set().union(*(set(tie_up[t - 1]) for t in action))) for action in treadling]
        mode = "tieup_treadling"
    if not any(liftplan):
        raise ValueError("at least one nonempty lift is required by this export profile")
    validate_colors(sections, ends, picks)
    document = Document(sections, blocks, preamble, shafts, threading, liftplan, mode)
    reserve_export_room(document)
    return document


def validate_colors(sections, ends, picks):
    has_palette, has_table = "COLOR PALETTE" in sections, "COLOR TABLE" in sections
    if has_palette != has_table:
        raise ValueError("COLOR PALETTE and COLOR TABLE must occur together")
    if not has_palette:
        if any("COLOR" in sections[s] for s in ("WARP", "WEFT")) or any(s in sections for s in ("WARP COLORS", "WEFT COLORS")):
            raise ValueError("colors require a palette and color table")
        return
    palette = sections["COLOR PALETTE"]
    try:
        entries = scalar(palette["ENTRIES"], 1, 256, "Palette Entries")
        limits = palette["RANGE"].split(",")
    except KeyError as error:
        raise ValueError("palette requires Entries and Range") from error
    if len(limits) != 2:
        raise ValueError("palette Range needs two values")
    low, high = [scalar(v, 0, 65535, "Palette Range") for v in limits]
    if low >= high:
        raise ValueError("palette range minimum must be smaller than maximum")
    table = sections["COLOR TABLE"]
    indices = [scalar(k, 1, entries, "Color Table index") for k in table]
    if set(indices) != set(range(1, entries + 1)) or len(indices) != entries:
        raise ValueError("color table must contain each declared index exactly once")
    for raw in table.values():
        channels = raw.split(",")
        if len(channels) != 3:
            raise ValueError("color table entries require three channels")
        for channel in channels:
            scalar(channel, low, high, "color channel")
    for name, count in (("WARP", ends), ("WEFT", picks)):
        if "COLOR" in sections[name]:
            default = sections[name]["COLOR"].split(",")
            if len(default) not in (1, 4):
                raise ValueError(f"{name} Color requires index or index,R,G,B")
            scalar(default[0], 1, entries, f"{name} default color")
            for channel in default[1:]:
                scalar(channel, low, high, f"{name} default color channel")
        overrides = sections.get(f"{name} COLORS", {})
        seen = set()
        for key, value in overrides.items():
            index = scalar(key, 1, count, f"{name} color index")
            if index in seen:
                raise ValueError(f"{name} repeated numeric color index")
            seen.add(index)
            scalar(value, 1, entries, f"{name} color")
        if "COLOR" not in sections[name] and len(overrides) != count:
            raise ValueError(f"{name} requires default color or complete overrides")


def drawdown_digest(threading, lifts):
    """Hash every original cloth cell, caching at most 128 distinct rows."""
    digest, rows_by_lift = hashlib.sha256(), {}
    for lift in lifts:
        key = tuple(lift)
        if key not in rows_by_lift:
            raised = set(lift)
            rows_by_lift[key] = bytes(int(bool(shaft) and shaft in raised) for shaft in threading)
        digest.update(rows_by_lift[key])
    return digest.hexdigest()


def adapt(document, slots, allowed_pairs, fixed_tie_up=None, **limits):
    # Search depends on distinct lifts, not repetitions or warp positions.
    # Solve the entire family together; never combine independent tie-ups.
    unique_lifts = list(dict.fromkeys(tuple(lift) for lift in document.liftplan))
    if len(unique_lifts) > 128:
        raise ValueError("supported limit: at most 128 distinct lift sets per draft")
    project = {"model": "rising_shed_union", "shafts": document.shafts,
               "threading": sorted(set(document.threading) - {0}),
               "slots": slots, "allowed_pairs": allowed_pairs,
               "liftplan": [list(lift) for lift in unique_lifts],
               "fixed_tie_up": [None] * len(slots) if fixed_tie_up is None else fixed_tie_up}
    result = solve(project, **limits)
    result.pop("drawdown", None)
    result.pop("threading", None)
    result["input_mode"] = document.mode
    result["declared_allowed_pairs"] = [list(pair) for pair in allowed_pairs]
    result["source_picks"] = len(document.liftplan)
    result["source_ends"] = len(document.threading)
    if result["status"] != "feasible":
        return result
    action_by_lift = {tuple(row["raised_shafts"]): row for row in result["picks"]}
    result["picks"] = [{"pick": index, "physical_slots": action_by_lift[tuple(lift)]["physical_slots"].copy(),
                        "logical_treadles": action_by_lift[tuple(lift)]["logical_treadles"].copy(),
                        "raised_shafts": lift.copy()}
                       for index, lift in enumerate(document.liftplan, 1)]
    result["wif_to_physical"] = {str(slot["id"]): slot["id"] for slot in slots}
    result["wif_treadles_by_pick"] = [row["physical_slots"].copy() for row in result["picks"]]
    result["drawdown_sha256"] = drawdown_digest(document.threading, document.liftplan)
    return result


def section(name, values):
    return "[" + name + "]\n" + "".join(f"{k}={v}\n" for k, v in values.items()) + "\n"


def output_prefix(document, slot_count):
    rewritten = CONTROL
    kept = {k: v for k, v in document.blocks.items() if k not in rewritten}
    header = dict(document.sections["WIF"])
    header.update({"SOURCE PROGRAM": "Sley", "SOURCE VERSION": __version__})
    weaving = {"SHAFTS": str(document.shafts), "TREADLES": str(slot_count), "RISING SHED": "true"}
    flags = {k: v for k, v in document.sections["CONTENTS"].items() if k not in rewritten}
    flags.update({k: "true" for k in [*kept, "WEAVING", "TIEUP", "TREADLING"]})
    flags["LIFTPLAN"] = "false"
    output = document.preamble + section("WIF", header) + section("CONTENTS", flags) + section("WEAVING", weaving)
    output += "".join(v + ("\n" if not v.endswith("\n") else "") for v in kept.values())
    return output, kept


def reserve_export_room(document):
    """Admit only drafts whose retained text fits every supported pedal plan.

    Control sections are replaced, so this same bound holds on reopening our
    output. Ten effects of all shafts and every pick pressing 9,10 maximize
    serialized control size for the fixed source dimensions.
    """
    prefix, _ = output_prefix(document, 10)
    worst = prefix + section("TIEUP", {str(t): ",".join(map(str, range(1, document.shafts + 1))) for t in range(1, 11)})
    worst += section("TREADLING", {str(p): "9,10" for p in range(1, len(document.liftplan) + 1)})
    try:
        parse_sections(worst)
    except ValueError as error:
        raise ValueError("retained text leaves insufficient room for bounded WIF export: " + str(error)) from error


def export_wif(document, result):
    if result["status"] != "feasible":
        raise ValueError("only feasible plans can export WIF")
    # Verify supplied plan, rather than trusting mutable report flags.
    expected_picks = len(document.liftplan)
    if len(result["picks"]) != expected_picks:
        raise ValueError("plan pick count disagrees with source")
    effects = {row["physical_slot"]: row["raises"] for row in result["tie_up"]}
    slot_count = len(effects)
    if not 1 <= slot_count <= 10 or set(effects) != set(range(1, slot_count + 1)):
        raise ValueError("plan must retain consecutive declared physical slots")
    mapping = {row["logical_treadle"]: row["physical_slot"] for row in result["tie_up"] if row["logical_treadle"] is not None}
    allowed = {frozenset(pair) for pair in result["declared_allowed_pairs"]}
    lifted = []
    for pick in result["picks"]:
        pressed = pick["physical_slots"]
        if len(pressed) > 2 or len(set(pressed)) != len(pressed) or any(slot not in effects for slot in pressed):
            raise ValueError("invalid physical pressing action")
        if len(pressed) == 2 and frozenset(pressed) not in allowed:
            raise ValueError("physical pressing action violates declared pair graph")
        if [mapping.get(t) for t in pick["logical_treadles"]] != pressed:
            raise ValueError("internal logical mapping disagrees with physical action")
        lifted.append(sorted(set().union(*(set(effects[t]) for t in pressed))))
    if lifted != document.liftplan:
        raise ValueError("plan changes the requested source liftplan")
    output, kept = output_prefix(document, slot_count)
    output += section("TIEUP", {str(t): ",".join(map(str, shafts)) or "0" for t, shafts in effects.items()})
    output += section("TREADLING", {str(row["pick"]): ",".join(map(str, row["physical_slots"])) or "0" for row in result["picks"]})
    reopened = import_wif(output)
    if reopened.threading != document.threading or reopened.liftplan != document.liftplan:
        raise ValueError("export failed semantic roundtrip")
    for name, block in kept.items():
        if reopened.blocks[name].rstrip("\n") != block.rstrip("\n"):
            raise ValueError(f"export altered independent section: {name}")
    return output
