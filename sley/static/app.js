import {
  MAX_WIF_BYTES,
  validateProject,
  validateFixedTieUp,
  resizeFixedTieUp,
  pairPreset,
  boundedWindow,
  Revision,
  fabricColor,
  decodeText,
} from "/model.mjs";
const $ = (id) => document.getElementById(id);
const revision = new Revision();
const state = {
  draft: null,
  wif: "",
  slots: 8,
  pairs: pairPreset(8, "all"),
  fixed: Array(8).fill(null),
  pedal: 0,
  selected: 0,
  end: 0,
  pick: 0,
  view: "source",
  job: null,
  result: null,
  starting: false,
  importing: false,
  importSerial: 0,
  window: null,
};
let canvasMetrics = null;
let pollTimer;
function message(text, error = false) {
  $("message").textContent = text;
  $("message").classList.toggle("error", error);
}
async function api(path, body) {
  const response = await fetch(
    path,
    body === undefined
      ? { cache: "no-store" }
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const data = await response.json();
  if (!response.ok)
    throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}
function feasible() {
  return (
    state.result?.status === "feasible" &&
    state.job?.digest &&
    state.job.revision === revision.token()
  );
}
function controls() {
  $("save-project").disabled = !state.draft;
  $("solve").disabled =
    !state.draft || state.starting || state.job?.running || state.importing;
  $("cancel").disabled = !state.starting && !state.job?.running;
  $("export").disabled = !feasible();
  $("adapted-view").disabled = !feasible();
  $("example").disabled = state.importing;
  $("open-wif").disabled = state.importing;
  $("open-project").disabled = state.importing;
}
function status(label, detail, kind = "") {
  $("status-badge").textContent = label;
  $("status-badge").className = `status-badge ${kind}`;
  $("status-detail").textContent = detail;
}
function cancelRemote(job) {
  if (job?.id) api("/api/cancel", { job_id: job.id }).catch(() => {});
}
function invalidate(detail = "Constraints changed. Find a new plan.") {
  revision.change();
  clearTimeout(pollTimer);
  cancelRemote(state.job);
  state.job = null;
  state.result = null;
  state.starting = false;
  state.view = "source";
  status("No result", state.draft ? detail : "");
  controls();
  renderPick();
  renderTieup();
  draw();
}
function project() {
  return validateProject({
    format: "sley-project",
    version: 2,
    wif: state.wif,
    slot_count: state.slots,
    allowed_pairs: state.pairs,
    fixed_tie_up: state.fixed,
  });
}
function download(blob, name) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function fileName(suffix) {
  return (
    (state.draft?.title || "sley-draft")
      .replace(/[^a-z0-9_-]+/gi, "-")
      .slice(0, 70) + suffix
  );
}
async function importText(
  wif,
  constraints = null,
  serial = ++state.importSerial,
  token = revision.token(),
) {
  if (
    typeof wif !== "string" ||
    new TextEncoder().encode(wif).length > MAX_WIF_BYTES
  )
    throw new Error("WIF exceeds the 1 MiB input limit.");
  const draft = await api("/api/import", { wif });
  if (serial !== state.importSerial || !revision.current(token)) return false;
  const fixed = constraints
    ? validateFixedTieUp(
        constraints.fixed_tie_up ?? Array(constraints.slot_count).fill(null),
        constraints.slot_count,
        draft.shafts,
      )
    : Array(state.slots).fill(null);
  invalidate("Draft loaded. Set constraints, then find a plan.");
  state.wif = wif;
  state.draft = draft;
  state.fixed = fixed;
  state.pedal = 0;
  state.selected = 0;
  state.end = 0;
  state.pick = 0;
  if (constraints) {
    state.slots = constraints.slot_count;
    state.pairs = constraints.allowed_pairs.map((pair) => [...pair]);
  }
  $("slot-count").value = String(state.slots);
  $("pair-note").textContent =
    "Press a pair to allow or disallow it. Presets remain editable.";
  $("draft-title").textContent = draft.title || "Untitled draft";
  $("draft-meta").textContent =
    `${draft.ends.toLocaleString()} ends · ${draft.picks.toLocaleString()} picks · ${draft.shafts} shafts`;
  $("file-state").textContent = draft.title || "Untitled WIF";
  $("grid-empty").hidden = true;
  $("grid-loaded").hidden = false;
  $("pick-number").max = String(draft.picks);
  $("pick-number").disabled = false;
  renderPairs();
  renderFixed();
  controls();
  renderPick();
  renderTieup();
  draw();
  message(
    `Loaded ${draft.ends.toLocaleString()} ends and ${draft.picks.toLocaleString()} picks. Original WIF preserved in project saves.`,
  );
  return true;
}
async function importing(task) {
  state.importing = true;
  controls();
  try {
    await task();
  } catch (error) {
    message(
      `${error.message} ${state.draft ? "Current draft retained." : ""}`,
      true,
    );
  } finally {
    state.importing = false;
    controls();
  }
}
$("open-wif").addEventListener("click", () => $("wif-file").click());
$("open-project").addEventListener("click", () => $("project-file").click());
$("wif-file").addEventListener("change", (event) => {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  const serial = ++state.importSerial,
    token = revision.token();
  importing(async () => {
    if (file.size > MAX_WIF_BYTES)
      throw new Error("WIF exceeds the 1 MiB input limit.");
    await importText(decodeText(await file.arrayBuffer()), null, serial, token);
  });
});
$("project-file").addEventListener("change", (event) => {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  const serial = ++state.importSerial,
    token = revision.token();
  importing(async () => {
    if (file.size > 7 * MAX_WIF_BYTES)
      throw new Error("Project file exceeds the 7 MiB limit.");
    const data = await api("/api/project", {
      project: decodeText(await file.arrayBuffer()),
    });
    const saved = validateProject(data.project);
    await importText(saved.wif, saved, serial, token);
  });
});
$("example").addEventListener("click", () => {
  const serial = ++state.importSerial,
    token = revision.token();
  importing(async () => {
    const example = await api("/api/example");
    await importText(example.wif, example, serial, token);
  });
});
$("save-project").addEventListener("click", () => {
  try {
    download(
      new Blob([JSON.stringify(project(), null, 2) + "\n"], {
        type: "application/json",
      }),
      fileName(".sley.json"),
    );
    message(
      "Project saved with original WIF and physical pedal constraints. Results are recalculated when reopened.",
    );
  } catch (error) {
    message(error.message, true);
  }
});
function renderPairs() {
  const matrix = $("pair-matrix");
  matrix.replaceChildren();
  matrix.style.gridTemplateColumns = `repeat(${state.slots + 1},auto)`;
  const allowed = new Set(state.pairs.map((pair) => pair.join(",")));
  for (let row = 0; row <= state.slots; row++)
    for (let column = 0; column <= state.slots; column++) {
      let cell;
      if (row === 0 || column === 0) {
        cell = document.createElement("span");
        cell.className = "pair-axis";
        cell.textContent = String(row || column || "");
      } else if (row < column) {
        cell = document.createElement("button");
        cell.className = "pair-cell";
        cell.type = "button";
        const key = `${row},${column}`;
        cell.setAttribute(
          "aria-label",
          `Allow physical pedals ${row} and ${column} together`,
        );
        cell.title = `Pedals ${row} + ${column}`;
        cell.setAttribute("aria-pressed", String(allowed.has(key)));
        cell.addEventListener("click", () => {
          if (allowed.has(key))
            state.pairs = state.pairs.filter((pair) => pair.join(",") !== key);
          else state.pairs.push([row, column]);
          state.pairs.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
          invalidate();
          $("pair-note").textContent =
            "Press a pair to allow or disallow it. Presets remain editable.";
          cell.setAttribute("aria-pressed", String(!allowed.has(key)));
          allowed.has(key) ? allowed.delete(key) : allowed.add(key);
          $("pair-count").textContent = `${state.pairs.length} allowed`;
        });
      } else {
        cell = document.createElement("span");
        cell.className = "pair-blank";
        cell.setAttribute("aria-hidden", "true");
      }
      matrix.append(cell);
    }
  $("pair-count").textContent = `${state.pairs.length} allowed`;
}
function fixedLabel(raises) {
  return raises === null
    ? "Free · solver assigns"
    : raises.length
      ? `Fixed · shafts ${raises.join(", ")}`
      : "Fixed · keep untied";
}
function renderFixedSummary() {
  $("fixed-summary").replaceChildren();
  state.fixed.forEach((raises, i) => {
    const row = document.createElement("li");
    row.textContent = `Pedal ${i + 1}: ${fixedLabel(raises)}`;
    $("fixed-summary").append(row);
  });
}
function renderFixed() {
  const selector = $("fixed-pedal");
  selector.replaceChildren();
  for (let i = 0; i < state.slots; i++) {
    const option = document.createElement("option");
    option.value = String(i);
    option.textContent = `Pedal ${i + 1}`;
    selector.append(option);
  }
  selector.value = String(state.pedal);
  selector.disabled = !state.draft;
  const raises = state.fixed[state.pedal];
  $("fixed-selected").textContent =
    `Pedal ${state.pedal + 1}: ${fixedLabel(raises)}`;
  $("fixed-mode").value = raises === null ? "free" : "fixed";
  $("fixed-mode").disabled = !state.draft;
  $("fixed-shafts").replaceChildren();
  for (let shaft = 1; shaft <= (state.draft?.shafts || 0); shaft++) {
    const label = document.createElement("label"),
      input = document.createElement("input");
    input.type = "checkbox";
    input.checked = raises?.includes(shaft) || false;
    input.disabled = raises === null;
    input.setAttribute(
      "aria-label",
      `Pedal ${state.pedal + 1} raises shaft ${shaft}`,
    );
    input.addEventListener("change", () => {
      const selected = new Set(state.fixed[state.pedal]);
      input.checked ? selected.add(shaft) : selected.delete(shaft);
      state.fixed[state.pedal] = [...selected].sort((a, b) => a - b);
      invalidate();
      $("fixed-selected").textContent =
        `Pedal ${state.pedal + 1}: ${fixedLabel(state.fixed[state.pedal])}`;
      renderFixedSummary();
    });
    label.append(input, document.createTextNode(`Shaft ${shaft}`));
    $("fixed-shafts").append(label);
  }
  $("fixed-untied").disabled = !state.draft;
  const source = state.draft?.source_tie_up;
  $("copy-source-pedal").disabled =
    !Array.isArray(source) || state.pedal >= source.length;
  $("copy-source-pedal").textContent =
    `Copy input pedal ${state.pedal + 1} tie-up`;
  $("fixed-source-note").textContent =
    Array.isArray(source) && state.pedal < source.length
      ? `Input pedal ${state.pedal + 1} raises ${source[state.pedal].join(", ") || "no shafts"}. Copies only this pedal.`
      : "No supported input tie-up for this pedal.";
  renderFixedSummary();
}
$("fixed-pedal").addEventListener("change", () => {
  state.pedal = Number($("fixed-pedal").value);
  renderFixed();
});
$("fixed-mode").addEventListener("change", () => {
  state.fixed[state.pedal] = $("fixed-mode").value === "free" ? null : [];
  invalidate();
  renderFixed();
});
$("fixed-untied").addEventListener("click", () => {
  state.fixed[state.pedal] = [];
  invalidate();
  renderFixed();
});
$("copy-source-pedal").addEventListener("click", () => {
  const source = state.draft?.source_tie_up;
  if (!Array.isArray(source) || state.pedal >= source.length) return;
  state.fixed[state.pedal] = [...source[state.pedal]];
  invalidate();
  renderFixed();
});
$("slot-count").addEventListener("change", () => {
  const slots = Number($("slot-count").value);
  try {
    state.fixed = resizeFixedTieUp(state.fixed, slots);
  } catch (error) {
    $("slot-count").value = String(state.slots);
    message(error.message, true);
    return;
  }
  state.slots = slots;
  state.pedal = Math.min(state.pedal, slots - 1);
  state.pairs = state.pairs.filter((pair) => pair[1] <= state.slots);
  invalidate();
  renderPairs();
  renderFixed();
  $("pair-note").textContent =
    "Press a pair to allow or disallow it. Presets remain editable.";
});
for (const button of document.querySelectorAll("[data-preset]"))
  button.addEventListener("click", () => {
    state.pairs = pairPreset(state.slots, button.dataset.preset);
    invalidate();
    renderPairs();
    $("pair-note").textContent =
      button.dataset.preset === "banks" && state.slots === 1
        ? "One pedal has no simultaneous pairs."
        : button.dataset.preset === "banks"
          ? `Two banks: 1–${Math.ceil(state.slots / 2)} and ${Math.ceil(state.slots / 2) + 1}–${state.slots}. Cross-bank preset applied; each pair remains editable.`
          : "Press a pair to allow or disallow it. Presets remain editable.";
  });
$("solve").addEventListener("click", async () => {
  if (!state.draft || state.starting || state.job?.running) return;
  invalidate("Finding a plan…");
  const token = revision.token();
  state.starting = true;
  controls();
  status("Running", "Starting finite search…", "running");
  try {
    const started = await api("/api/solve", {
      wif: state.wif,
      slot_count: state.slots,
      allowed_pairs: state.pairs,
      fixed_tie_up: state.fixed,
    });
    if (!revision.current(token)) {
      cancelRemote({ id: started.job_id });
      return;
    }
    state.starting = false;
    state.job = {
      id: started.job_id,
      digest: started.digest,
      revision: token,
      running: true,
    };
    controls();
    poll(token, state.job.id);
  } catch (error) {
    if (revision.current(token)) {
      state.starting = false;
      status("Failed", error.message);
      message(error.message, true);
      controls();
    }
  }
});
async function poll(token, id) {
  try {
    const job = await api(`/api/jobs/${encodeURIComponent(id)}`);
    if (!revision.current(token) || state.job?.id !== id) return;
    if (job.digest !== state.job.digest)
      throw new Error("Result identity did not match the current constraints.");
    if (job.state === "running") {
      status(
        "Running",
        "Searching one shared tie-up for all requested lifts…",
        "running",
      );
      pollTimer = setTimeout(() => poll(token, id), 400);
      return;
    }
    state.job.running = false;
    if (job.state === "complete") {
      state.result = job.result;
      const result = job.result;
      if (result.status === "feasible")
        status(
          "Feasible",
          `Checked plan · ${result.work.toLocaleString()} search steps · ${result.elapsed_seconds.toFixed(2)} s`,
          "feasible",
        );
      else if (result.status === "infeasible")
        status(
          "Infeasible",
          `Completed finite search. No plan satisfies these constraints. ${result.work.toLocaleString()} steps.`,
          "infeasible",
        );
      else
        status(
          "Unknown",
          `Work or time limit reached · ${result.work.toLocaleString()} steps (limit ${result.work_limit.toLocaleString()}). No conclusion.`,
          "unknown",
        );
      message(
        result.status === "feasible"
          ? "Plan checked. Inspect physical pedals and selected picks, then export."
          : result.status === "infeasible"
            ? "No plan under these constraints. Change physical pedals or allowed pairs to try again."
            : "Search ended without a conclusion. No executable output is available.",
      );
    } else {
      status(
        job.state === "cancelled" ? "Cancelled" : "Failed",
        job.error || "Calculation stopped.",
      );
      message(job.error || "Calculation cancelled.", job.state === "failed");
    }
    controls();
    renderPick();
    renderTieup();
    draw();
  } catch (error) {
    if (revision.current(token) && state.job?.id === id) {
      state.job.running = false;
      status("Failed", error.message);
      message(error.message, true);
      controls();
    }
  }
}
$("cancel").addEventListener("click", () => {
  invalidate("Calculation cancelled.");
  status("Cancelled", "You can change constraints or find a new plan.");
  message("Calculation cancelled.");
});
$("export").addEventListener("click", async () => {
  if (!feasible()) return;
  const token = revision.token(),
    job = { ...state.job };
  $("export").disabled = true;
  try {
    const response = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: job.id, digest: job.digest }),
    });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || "Export failed.");
    }
    const blob = await response.blob();
    if (!revision.current(token) || state.job?.id !== job.id) return;
    download(blob, fileName("-adapted.zip"));
    message(
      "Export saved: adapted WIF, physical actions and printable tie-up sheet.",
    );
  } catch (error) {
    if (revision.current(token)) message(error.message, true);
  } finally {
    controls();
  }
});
function actionForPick() {
  return feasible() ? state.result.picks[state.selected] : null;
}
function selectPick(value) {
  if (!state.draft) return;
  state.selected = Math.max(0, Math.min(state.draft.picks - 1, value));
  if (
    state.window &&
    (state.selected < state.window.pick ||
      state.selected >= state.window.pick + state.window.picks)
  )
    state.pick = state.selected;
  renderPick();
  renderTieup();
  draw();
}
$("pick-number").addEventListener("change", () => {
  const number = Number($("pick-number").value);
  selectPick(Number.isInteger(number) ? number - 1 : state.selected);
});
$("pick-prev").addEventListener("click", () => selectPick(state.selected - 1));
$("pick-next").addEventListener("click", () => selectPick(state.selected + 1));
function renderPick() {
  const draft = state.draft,
    action = actionForPick();
  $("pick-prev").disabled = !draft || state.selected === 0;
  $("pick-next").disabled = !draft || state.selected === draft.picks - 1;
  $("pick-number").value = String(state.selected + 1);
  $("pick-total").textContent = draft
    ? `of ${draft.picks.toLocaleString()}`
    : "of —";
  $("pick-shafts").textContent = draft
    ? draft.liftplan[state.selected].join(", ") || "None · rest"
    : "—";
  const target = $("pick-action");
  target.replaceChildren();
  if (!action) target.textContent = state.draft ? "No current plan" : "—";
  else if (!action.physical_slots.length) target.textContent = "None · rest";
  else
    for (const slot of action.physical_slots) {
      const span = document.createElement("span");
      span.className = "pedal-token";
      span.textContent = String(slot);
      target.append(span);
    }
}
function renderTieup() {
  const container = $("tieup-grid");
  container.replaceChildren();
  $("tieup-count").textContent = feasible() ? `${state.slots} positions` : "";
  if (!feasible()) return;
  const selected = new Set(actionForPick()?.physical_slots || []),
    tieup = new Map(
      state.result.tie_up.map((item) => [item.physical_slot, item.raises]),
    );
  for (let slot = 1; slot <= state.slots; slot++) {
    const raises = tieup.get(slot) || [],
      column = document.createElement("div");
    column.className = `pedal${selected.has(slot) ? " active" : ""}`;
    const label = document.createElement("button");
    label.className = "pedal-number";
    label.textContent = String(slot);
    label.title = `Physical pedal ${slot}: shafts ${raises.join(", ") || "none"}. Select next pick using this pedal.`;
    label.setAttribute("aria-label", label.title);
    const used = state.result.picks.some((pick) =>
      pick.physical_slots.includes(slot),
    );
    label.disabled = !used;
    label.addEventListener("click", () => {
      const picks = state.result.picks;
      const offset = picks
        .slice(state.selected + 1)
        .findIndex((pick) => pick.physical_slots.includes(slot));
      selectPick(
        offset >= 0
          ? state.selected + 1 + offset
          : picks.findIndex((pick) => pick.physical_slots.includes(slot)),
      );
    });
    column.append(label);
    for (let shaft = state.draft.shafts; shaft >= 1; shaft--) {
      const cell = document.createElement("div");
      cell.className = `shaft-cell${raises.includes(shaft) ? " raised" : ""}`;
      cell.textContent = raises.includes(shaft) ? String(shaft) : "·";
      column.append(cell);
    }
    if (!used) {
      const unused = document.createElement("div");
      unused.className = "pedal-unused";
      unused.textContent = "Unused";
      column.append(unused);
    }
    container.append(column);
  }
}
function draw() {
  $("source-view").setAttribute(
    "aria-pressed",
    String(state.view === "source"),
  );
  $("adapted-view").setAttribute(
    "aria-pressed",
    String(state.view === "adapted"),
  );
  if (!state.draft || $("grid-loaded").hidden) return;
  const available = Math.max(160, $("fabric").parentElement.clientWidth),
    cell = 18,
    left = 38,
    top = 40;
  const width = Math.max(
      6,
      Math.min(48, Math.floor((available - left - 6) / cell)),
    ),
    height = window.innerWidth <= 600 ? 16 : 28;
  const frame = boundedWindow(
    state.draft.ends,
    state.draft.picks,
    state.end,
    state.pick,
    width,
    height,
  );
  state.window = frame;
  state.end = frame.end;
  state.pick = frame.pick;
  const canvas = $("fabric"),
    logicalWidth = left + frame.ends * cell + 3,
    logicalHeight = top + frame.picks * cell + 3,
    scale = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = logicalWidth * scale;
  canvas.height = logicalHeight * scale;
  canvas.style.width = `${logicalWidth}px`;
  canvas.style.height = `${logicalHeight}px`;
  const context = canvas.getContext("2d");
  context.scale(scale, scale);
  context.fillStyle = "#f8fafc";
  context.fillRect(0, 0, logicalWidth, logicalHeight);
  context.font = "9px ui-monospace, monospace";
  context.textAlign = "center";
  context.textBaseline = "middle";
  for (let column = 0; column < frame.ends; column++) {
    const end = frame.end + column,
      x = left + column * cell;
    context.fillStyle = state.draft.warp_colors[end];
    context.fillRect(x, 2, cell - 1, 8);
    context.fillStyle = "#516377";
    context.fillText(String(end + 1), x + cell / 2, 18);
    context.fillText(
      state.draft.threading[end] === 0
        ? "—"
        : String(state.draft.threading[end]),
      x + cell / 2,
      31,
    );
  }
  for (let row = 0; row < frame.picks; row++) {
    const pick = frame.pick + row,
      y = top + row * cell;
    const raised =
      state.view === "adapted" && feasible()
        ? state.result.picks[pick].raised_shafts
        : state.draft.liftplan[pick];
    context.fillStyle = state.draft.weft_colors[pick];
    context.fillRect(2, y + 2, 6, cell - 4);
    context.fillStyle = pick === state.selected ? "#145ca8" : "#516377";
    context.fillText(String(pick + 1), 23, y + cell / 2);
    for (let column = 0; column < frame.ends; column++) {
      context.fillStyle = fabricColor(
        state.draft,
        frame.end + column,
        pick,
        raised,
      );
      context.fillRect(left + column * cell, y, cell, cell);
      context.strokeStyle = "#1a2a3a26";
      context.lineWidth = 0.5;
      context.strokeRect(
        left + column * cell + 0.25,
        y + 0.25,
        cell - 0.5,
        cell - 0.5,
      );
    }
    if (pick === state.selected) {
      context.strokeStyle = "#1768ba";
      context.lineWidth = 2;
      context.strokeRect(left + 1, y + 1, frame.ends * cell - 2, cell - 2);
    }
  }
  canvasMetrics = { left, top, cell, frame, logicalWidth, logicalHeight };
  canvas.setAttribute(
    "aria-label",
    `${state.view === "adapted" ? "Adapted" : "Source"} fabric, ends ${frame.end + 1} through ${frame.end + frame.ends}, picks ${frame.pick + 1} through ${frame.pick + frame.picks}. Selected pick ${state.selected + 1}; raised shafts ${state.draft.liftplan[state.selected].join(", ") || "none"}. Arrow keys select picks or move ends.`,
  );
  $("ends-window").textContent =
    `${frame.end + 1}–${frame.end + frame.ends} / ${state.draft.ends.toLocaleString()}`;
  $("picks-window").textContent =
    `${frame.pick + 1}–${frame.pick + frame.picks} / ${state.draft.picks.toLocaleString()}`;
  $("ends-prev").disabled = frame.end === 0;
  $("ends-next").disabled = frame.end + frame.ends >= state.draft.ends;
  $("picks-prev").disabled = frame.pick === 0;
  $("picks-next").disabled = frame.pick + frame.picks >= state.draft.picks;
  $("view-label").textContent =
    state.view === "adapted"
      ? "Adapted · same lift sequence"
      : "Source drawdown";
}
$("source-view").addEventListener("click", () => {
  state.view = "source";
  draw();
});
$("adapted-view").addEventListener("click", () => {
  if (feasible()) {
    state.view = "adapted";
    draw();
  }
});
$("fabric").addEventListener("click", (event) => {
  if (!canvasMetrics) return;
  const box = event.currentTarget.getBoundingClientRect(),
    y = ((event.clientY - box.top) * canvasMetrics.logicalHeight) / box.height;
  const row = Math.floor((y - canvasMetrics.top) / canvasMetrics.cell);
  if (row >= 0 && row < canvasMetrics.frame.picks)
    selectPick(canvasMetrics.frame.pick + row);
});
function moveWindow(axis, direction) {
  if (!state.window) return;
  state[axis] +=
    direction * (axis === "end" ? state.window.ends : state.window.picks);
  draw();
}
$("ends-prev").addEventListener("click", () => moveWindow("end", -1));
$("ends-next").addEventListener("click", () => moveWindow("end", 1));
$("picks-prev").addEventListener("click", () => moveWindow("pick", -1));
$("picks-next").addEventListener("click", () => moveWindow("pick", 1));
$("fabric").addEventListener("keydown", (event) => {
  const keys = [
    "ArrowUp",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
    "PageUp",
    "PageDown",
    "Home",
    "End",
  ];
  if (!keys.includes(event.key) || !state.draft) return;
  event.preventDefault();
  if (event.key === "ArrowUp") selectPick(state.selected - 1);
  if (event.key === "ArrowDown") selectPick(state.selected + 1);
  if (event.key === "ArrowLeft") moveWindow("end", -1);
  if (event.key === "ArrowRight") moveWindow("end", 1);
  if (event.key === "PageUp")
    selectPick(state.selected - (state.window?.picks || 1));
  if (event.key === "PageDown")
    selectPick(state.selected + (state.window?.picks || 1));
  if (event.key === "Home") selectPick(0);
  if (event.key === "End") selectPick(state.draft.picks - 1);
});
new ResizeObserver(() => draw()).observe($("fabric").parentElement);
renderPairs();
controls();
