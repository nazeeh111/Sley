"""Independent existing-reader comparison; does not import the new adapter."""
import hashlib
import json
import sys

from dtx_to_wif import read_pattern_file, make_liftplan


def snapshot(path):
    draft = read_pattern_file(path)
    ends, picks = draft.warp.threads, draft.weft.threads
    liftplan = make_liftplan(draft)
    threading = [sorted(draft.threading.get(i, set()) - {0}) for i in range(1, ends + 1)]
    lifts = [sorted(liftplan.get(i, set())) for i in range(1, picks + 1)]
    warp_colors = [draft.warp_colors.get(i, draft.warp.color) for i in range(1, ends + 1)]
    weft_colors = [draft.weft_colors.get(i, draft.weft.color) for i in range(1, picks + 1)]
    grid = [[bool(set(shafts) & set(lift)) for shafts in threading] for lift in lifts]
    colored = [[draft.color_table[warp_colors[i] if cell else weft_colors[j]]
                for i, cell in enumerate(row)] for j, row in enumerate(grid)]
    return {"shafts": draft.num_shafts, "ends": ends, "picks": picks,
            "threading": threading, "lifts": lifts, "rising_shed": draft.is_rising_shed,
            "color_table": draft.color_table, "color_range": draft.color_range,
            "warp_colors": warp_colors, "weft_colors": weft_colors,
            "warp_spacing": [draft.warp_spacing.get(i, draft.warp.spacing) for i in range(1, ends + 1)],
            "weft_spacing": [draft.weft_spacing.get(i, draft.weft.spacing) for i in range(1, picks + 1)],
            "warp_thickness": [draft.warp_thickness.get(i, draft.warp.thickness) for i in range(1, ends + 1)],
            "weft_thickness": [draft.weft_thickness.get(i, draft.weft.thickness) for i in range(1, picks + 1)],
            "units": [draft.warp.units, draft.weft.units], "notes": draft.notes,
            "title": draft.name,
            "drawdown_sha256": hashlib.sha256(json.dumps(grid).encode()).hexdigest(),
            "colored_drawdown_sha256": hashlib.sha256(json.dumps(colored).encode()).hexdigest()}


def main():
    before, after = (snapshot(path) for path in sys.argv[1:3])
    unequal = [key for key in before if before[key] != after[key]]
    physical = None
    if len(sys.argv) > 3:
        plan = json.loads(open(sys.argv[3]).read())
        loaded = read_pattern_file(sys.argv[2])
        expected = plan["wif_treadles_by_pick"]
        actual = [sorted(loaded.treadling.get(i, set()) - {0}) for i in range(1, loaded.weft.threads + 1)]
        effects_equal = all(loaded.tieup.get(row["physical_slot"], set()) - {0} == set(row["raises"]) for row in plan["tie_up"])
        physical = {"equal": actual == expected and effects_equal and loaded.num_treadles == len(plan["tie_up"]),
                    "declared_slots": loaded.num_treadles,
                    "unused_slots": [row["physical_slot"] for row in plan["tie_up"] if not row["raises"]],
                    "physical_treadling": actual}
        if not physical["equal"]:
            unequal.append("physical_slot_ids")
    print(json.dumps({"reader": "dtx_to_wif 4.7.1", "equal": not unequal,
                      "differences": unequal, "input": before, "output": after,
                      "physical_ids": physical}, indent=2))
    return bool(unequal)


if __name__ == "__main__":
    raise SystemExit(main())
