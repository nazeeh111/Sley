export const MAX_WIF_BYTES = 1024 * 1024;
export function validateProject(value) {
  const keys =
    value?.version === 2
      ? [
          "allowed_pairs",
          "fixed_tie_up",
          "format",
          "slot_count",
          "version",
          "wif",
        ]
      : ["allowed_pairs", "format", "slot_count", "version", "wif"];
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.keys(value).sort().join("|") !== keys.join("|")
  )
    throw new Error(
      "Project must contain only format, version, WIF and pedal constraints.",
    );
  if (value.format !== "sley-project" || ![1, 2].includes(value.version))
    throw new Error("Unsupported project format or version.");
  if (
    typeof value.wif !== "string" ||
    !value.wif.trim() ||
    new TextEncoder().encode(value.wif).length > MAX_WIF_BYTES
  )
    throw new Error("WIF text must be nonempty and at most 1 MiB.");
  if (
    !Number.isInteger(value.slot_count) ||
    value.slot_count < 1 ||
    value.slot_count > 10
  )
    throw new Error("Physical pedal count must be between 1 and 10.");
  if (!Array.isArray(value.allowed_pairs) || value.allowed_pairs.length > 45)
    throw new Error("Invalid allowed pairs.");
  const seen = new Set();
  for (const pair of value.allowed_pairs) {
    if (
      !Array.isArray(pair) ||
      pair.length !== 2 ||
      !pair.every(Number.isInteger) ||
      pair[0] < 1 ||
      pair[0] >= pair[1] ||
      pair[1] > value.slot_count
    )
      throw new Error(
        "Pairs must be distinct ascending physical pedal numbers.",
      );
    const key = pair.join(",");
    if (seen.has(key)) throw new Error("Duplicate allowed pair.");
    seen.add(key);
  }
  return {
    format: value.format,
    version: 2,
    wif: value.wif,
    slot_count: value.slot_count,
    allowed_pairs: value.allowed_pairs.map((pair) => [...pair]),
    fixed_tie_up: validateFixedTieUp(
      value.version === 1
        ? Array(value.slot_count).fill(null)
        : value.fixed_tie_up,
      value.slot_count,
    ),
  };
}
export function pairPreset(slots, mode) {
  const pairs = [];
  const split = Math.ceil(slots / 2);
  for (let a = 1; a <= slots; a++)
    for (let b = a + 1; b <= slots; b++)
      if (mode === "all" || (mode === "banks" && a <= split !== b <= split))
        pairs.push([a, b]);
  return pairs;
}
export function boundedWindow(ends, picks, end, pick, width = 48, height = 32) {
  const columns = Math.min(ends, width);
  const rows = Math.min(picks, height);
  return {
    end: Math.max(0, Math.min(ends - columns, end)),
    pick: Math.max(0, Math.min(picks - rows, pick)),
    ends: columns,
    picks: rows,
  };
}
export class Revision {
  #value = 0;
  token() {
    return this.#value;
  }
  change() {
    return ++this.#value;
  }
  current(token) {
    return token === this.#value;
  }
}
export function fabricColor(draft, end, pick, raised = draft.liftplan[pick]) {
  return draft.threading[end] !== 0 && raised.includes(draft.threading[end])
    ? draft.warp_colors[end]
    : draft.weft_colors[pick];
}

export function decodeText(bytes) {
  return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(
    bytes,
  );
}

export function validateFixedTieUp(fixed, slots, shafts = 8) {
  if (!Array.isArray(fixed) || fixed.length !== slots)
    throw new Error("Fixed tie-up must contain one entry per physical pedal.");
  return fixed.map((raises) => {
    if (raises === null) return null;
    if (
      !Array.isArray(raises) ||
      raises.some(
        (shaft, i) =>
          !Number.isInteger(shaft) ||
          shaft < 1 ||
          shaft > shafts ||
          (i > 0 && shaft <= raises[i - 1]),
      )
    )
      throw new Error(
        "Fixed shafts must be distinct ascending shaft numbers in this draft.",
      );
    return [...raises];
  });
}
export function resizeFixedTieUp(fixed, slots) {
  if (!Number.isInteger(slots) || slots < 1 || slots > 10)
    throw new Error("Physical pedal count must be between 1 and 10.");
  if (fixed.slice(slots).some((raises) => raises !== null))
    throw new Error(
      "Make removed pedals free before reducing the physical pedal count.",
    );
  return Array.from({ length: slots }, (_, i) =>
    fixed[i] === undefined || fixed[i] === null ? null : [...fixed[i]],
  );
}
