# A fixed pedal makes the allowed pair matter

This self-authored two-shaft fixture is bundled with current Sley source `e93ac8fd4e6810658150e8f1f8357973c748ddf1`. It has two threaded ends and four picks. It is a small model example, not a recorded physical weaving trial.

## Use the actual workbench

From this source checkout with Python 3.12 or newer:

```sh
python -m sley --no-browser
```

Open the printed local URL, then **Open project** → `sley/examples/fixed-pedals.sley.json`.

1. The saved constraints fix pedal 1 to shaft 1, leave pedal 2 free and keep pedal 3 untied. Only pair 1+2 is allowed.
2. Choose **Single only**, then **Find plan**. The result is Infeasible: no one pedal can produce the combined lift without violating a fixed assignment. No partial result can export.
3. Allow physical pedals **1 and 2 together**, then **Find plan** again. The checked tie-up assigns pedal 2 to shaft 2. Select pick 3 to inspect the paired press.
4. **Save project** and **Export result ZIP**. The actual outputs are [saved.sley.json](saved.sley.json) and [adapted.zip](adapted.zip).
5. Open the saved project in a fresh browser session. Projects retain original WIF and constraints, not a calculated result, so **Find plan** again before export. Importing the exported [adapted.wif](adapted.wif) separately retains the same threading and shaft lifts; a fresh WIF import resets fixed assignments by design.

The original and saved project bytes match exactly. Malformed WIF/project imports retain the current feasible draft. Cancelling an actual starting request retains the draft, disables export and requires a fresh solve. This tiny search was not a long-running cancellation benchmark. Editing any constraint invalidates the old plan. [Actual browser record](browser.json).

## What the artifact proves

| Pick | Required shafts | Physical press |
| --- | --- | --- |
| 1 | 1 | 1 |
| 2 | 2 | 2 |
| 3 | 1,2 | 1+2 |
| 4 | None | Rest |

Pedal positions remain 1,2,3, including unused untied pedal 3. The native ZIP contains [adapted.wif](adapted.wif), [actions.csv](actions.csv) and [tie-up.html](tie-up.html). A fresh native import and an independent section/union readback match all eight drawdown bits, original threading, warp/weft sections and physical actions. [Complete readback](reopen-check.json) · [feasible record](feasible.json) · [infeasible record](infeasible.json).

The mechanism figure is a categorical draft schematic, not a spatial textile model. Filled cloth cells mean warp above weft. E1 threads shaft 1 and E2 threads shaft 2. Every pick and every physical pedal is included; original loopback job identities/timing in the raw record identify this execution, not bitwise future exports.

## Compare a declared existing setup

The current-main CLI optimizer is separate from the browser's first-feasible solver. This case deliberately declares an existing setup that already works: `[[1],[2],[]]`.

```sh
python -m sley compare docs/presentation/source.wif docs/presentation/constraints.json --choose optimized --export /tmp/sley-worked.wif > /tmp/sley-comparison.json
```

Choose fresh output paths. The actual [comparison](cli-optimized.json) exhausts this tiny finite search and proves objective `[0,1]`: zero shaft-pedal connection edits, then one paired pick occurrence. The [initial selection](cli-initial.json) has the same objective. This is a useful no-change answer, not a claimed improvement. Both exported WIFs reimport with every original lift intact. Existing output refusal preserves every byte. [Exact commands and statuses](cli-journey.json).

## Reopen the download

Extract [worked-example.zip](worked-example.zip) and read its archive-specific README.txt. Run `python reopen.py` with Python 3.12+ for complete member hashes and independent CSV/WIF union checks. Add `--native` when running from a full source checkout with Sley importable to also perform fresh native WIF import; the full engine is explicitly external. All guide-local paths are included. Keep the MIT LICENSE.txt with the synthetic source and artifacts.

Supported rising-shed WIF profile and bounded finite search only. Unknown is not Infeasible; a budget stop cannot export partial actions. User-defined allowed pairs are constraints, not an ergonomic assessment. No real loom, arbitrary WIF compliance, optimum pedal count or physical fabric quality was validated.
