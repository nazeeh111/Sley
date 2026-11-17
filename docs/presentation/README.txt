SLEY: ONE DRAFT, FIXED PHYSICAL PEDALS

This extracted archive contains a self-authored two-shaft, four-pick example.
All local paths below are relative to this directory. No repository download
or figure-manifest link is needed for its member-byte checks.

With Python 3.12 or newer, run:
  python reopen.py

This standard-library checker verifies MANIFEST.json, compares all three native
ZIP members with their extracted copies and independently reconstructs the tiny
fixture's requested shaft lifts and physical pressing sequence. It is not a
replacement general WIF parser or solver. To also run Sley's actual fresh WIF
import, use python reopen.py --native with the full owning source importable.
The complete Sley engine is explicitly external, not included in this archive.

LOCAL ENTRYPOINTS
- reopen.py
- MANIFEST.json
- source.sley.json
- saved.sley.json
- source.wif
- constraints.json
- feasible.json
- infeasible.json
- adapted.zip
- adapted.wif
- actions.csv
- tie-up.html
- reopen-check.json
- cli-optimized.json
- cli-optimized.wif
- browser.json
- fixed-footwork.svg
- fixed-footwork-mobile.svg
- LICENSE.txt

Open tie-up.html locally for the actual printable tie-up and pressing sequence.
To reopen the project in Sley, start the external full source with python -m sley,
then Open project -> saved.sley.json and Find plan again. Projects store the WIF
and constraints, not a calculated result. Importing adapted.wif is a separate
route and resets fixed assignments by design.

Pedal 1 is fixed to shaft 1; pedal 2 is free and gets shaft 2; pedal 3 stays
untied. The four physical actions are 1, 2, pair 1+2, then rest. Removing allowed
pair 1+2 makes these exact fixed constraints infeasible. All eight schematic
cloth cells, original threading and shaft lifts survive native export/reopen.

The CLI comparison declares an already-working existing tie-up [[1],[2],[]].
It proves objective [0,1] in this tiny finite search: zero connection edits,
then one paired pick occurrence. This no-change answer is not an improvement
claim. The browser finds a first feasible plan; it does not run this optimizer.

Actual producer: Sley 0.2.5.dev0, Python 3.12.13, standard-library execution.
The supported model is explicit rising-shed WIF and unions of at most two
permitted physical pedals. Unknown is not Infeasible. No physical loom, textile
quality, ergonomic suitability or arbitrary WIF compatibility was validated.
Stored job IDs/timings identify one execution; fresh exports can differ in metadata.

Original source, complete solver/CLI/workbench and expert format limits:
https://github.com/nazeeh111/Sley/tree/e93ac8fd4e6810658150e8f1f8357973c748ddf1

Preserve LICENSE.txt with the original MIT source and these synthetic artifacts.
MANIFEST.json hashes every included payload except itself; hashes bind bytes,
not authenticity. The repository figure manifest is external to avoid a ZIP
self-hash cycle. All guide-local entrypoints are present in this extraction.
