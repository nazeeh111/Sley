import * as model from "./model.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import {
  validateProject,
  pairPreset,
  boundedWindow,
  Revision,
  fabricColor,
  decodeText,
} from "./model.mjs";
const valid = {
  format: "sley-project",
  version: 1,
  wif: "[WIF]\nVersion=1.1",
  slot_count: 4,
  allowed_pairs: [
    [1, 3],
    [2, 4],
  ],
};
test("portable project preserves original text and constraints without result state", () => {
  assert.deepEqual(validateProject(JSON.parse(JSON.stringify(valid))), {
    ...valid,
    version: 2,
    fixed_tie_up: [null, null, null, null],
  });
  for (const change of [
    { version: 2 },
    { result: {} },
    { slot_count: 11 },
    { wif: 4 },
    { allowed_pairs: [[1, 1]] },
    { allowed_pairs: [[0, 2]] },
    { allowed_pairs: [[2, 1]] },
    {
      allowed_pairs: [
        [1, 3],
        [1, 3],
      ],
    },
  ])
    assert.throws(() => validateProject({ ...valid, ...change }));
});
test("two-bank preset uses only cross-bank physical pairs", () => {
  assert.equal(pairPreset(4, "all").length, 6);
  assert.deepEqual(pairPreset(4, "single"), []);
  assert.deepEqual(pairPreset(4, "banks"), [
    [1, 3],
    [1, 4],
    [2, 3],
    [2, 4],
  ]);
  assert.deepEqual(pairPreset(5, "banks"), [
    [1, 4],
    [1, 5],
    [2, 4],
    [2, 5],
    [3, 4],
    [3, 5],
  ]);
});
test("large draft viewport stays bounded and clamps both edges", () => {
  assert.deepEqual(boundedWindow(4096, 4096, 4090, 4095, 48, 32), {
    end: 4048,
    pick: 4064,
    ends: 48,
    picks: 32,
  });
  assert.deepEqual(boundedWindow(8, 4, -1, -1, 48, 32), {
    end: 0,
    pick: 0,
    ends: 8,
    picks: 4,
  });
});
test("late asynchronous state cannot match a newer revision", () => {
  const revision = new Revision();
  const old = revision.token();
  revision.change();
  assert.equal(revision.current(old), false);
  assert.equal(revision.current(revision.token()), true);
});
test("fabric honors unthreaded ends, lifted shafts and source colors", () => {
  const draft = {
    threading: [1, 0, 2],
    liftplan: [[1]],
    warp_colors: ["#ff0000", "#00ff00", "#0000ff"],
    weft_colors: ["#ffffff"],
  };
  assert.equal(fabricColor(draft, 0, 0), "#ff0000");
  assert.equal(fabricColor(draft, 1, 0), "#ffffff");
  assert.equal(fabricColor(draft, 2, 0), "#ffffff");
});

test("invalid UTF-8 input is refused instead of silently replacing source bytes", () => {
  assert.equal(decodeText(new Uint8Array([65, 10])), "A\n");
  assert.throws(() => decodeText(new Uint8Array([0xc3, 0x28])));
});

test("UTF-8 BOM stays in the original text rather than being silently removed", () => {
  assert.equal(decodeText(new Uint8Array([0xef, 0xbb, 0xbf, 65])), "\ufeffA");
});

const fixedProject = {
  ...valid,
  version: 2,
  fixed_tie_up: [[1], null, [], [2, 4]],
};
test("version 2 preserves fixed empty and free pedals as different constraints", () => {
  const opened = validateProject(JSON.parse(JSON.stringify(fixedProject)));
  assert.deepEqual(opened.fixed_tie_up, [[1], null, [], [2, 4]]);
  opened.fixed_tie_up[0].push(2);
  assert.deepEqual(fixedProject.fixed_tie_up, [[1], null, [], [2, 4]]);
  for (const fixed_tie_up of [
    [null],
    [[1], null, [], [4, 2]],
    [[1], null, [], [2, 2]],
    [[0], null, [], null],
    [[9], null, [], null],
    [false, null, [], null],
  ])
    assert.throws(() => validateProject({ ...fixedProject, fixed_tie_up }));
});
test("pedal resizing refuses removal of fixed empty or raised pedals", () => {
  assert.throws(() => model.resizeFixedTieUp([[1], null, []], 2));
  assert.throws(() => model.resizeFixedTieUp([null, [2]], 1));
  assert.deepEqual(model.resizeFixedTieUp([[1], null, null], 2), [[1], null]);
  assert.deepEqual(model.resizeFixedTieUp([[1], null, []], 5), [
    [1],
    null,
    [],
    null,
    null,
  ]);
});
