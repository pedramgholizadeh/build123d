/* Agentic CAD Studio — frontend logic.
   One protocol for humans and agents: every change becomes
   POST /api/build, every verdict comes back from the checks.
   The 3D preview is a small software renderer (painter's algorithm,
   Lambert shading) over the binary STL the server exports — no
   external libraries, works air-gapped. */
"use strict";

/* ------------------------------------------------------------------ */
/* state                                                                */
/* ------------------------------------------------------------------ */

const state = {
  models: [],
  active: null,      // manifest of the active model
  overrides: {},     // parameter name -> current value
  buildId: null,
  mesh: null,        // {positions: Float32Array, normals: Float32Array, count}
  dirty: false,
};

const $ = (id) => document.getElementById(id);
const DEBOUNCE_MS = 150;

/* ------------------------------------------------------------------ */
/* api                                                                  */
/* ------------------------------------------------------------------ */

async function apiGet(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}

async function apiPost(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}

/* ------------------------------------------------------------------ */
/* binary STL -> mesh                                                   */
/* ------------------------------------------------------------------ */

function parseStl(buffer) {
  const view = new DataView(buffer);
  const count = view.getUint32(80, true);
  const positions = new Float32Array(count * 9);
  const normals = new Float32Array(count * 9);
  let offset = 84;
  for (let i = 0; i < count; i++) {
    normals.set(
      [view.getFloat32(offset, true), view.getFloat32(offset + 4, true), view.getFloat32(offset + 8, true)],
      i * 9
    );
    offset += 12;
    for (let v = 0; v < 3; v++) {
      positions.set(
        [view.getFloat32(offset, true), view.getFloat32(offset + 4, true), view.getFloat32(offset + 8, true)],
        i * 9 + v * 3
      );
      offset += 12;
    }
    offset += 2; // attribute byte count
  }
  return { positions, normals, count };
}

/* ------------------------------------------------------------------ */
/* viewer: ortho turntable over Z-up world, painter's algorithm         */
/* ------------------------------------------------------------------ */

const viewer = {
  canvas: null,
  ctx: null,
  azimuth: -Math.PI / 5,
  elevation: Math.PI / 5,
  zoom: 1,
  fit: null, // {cx, cy, cz, radius} of last mesh
  dpr: 1,

  init(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.resize();
    window.addEventListener("resize", () => { this.resize(); this.dirty(); });
    canvas.addEventListener("pointerdown", (event) => {
      canvas.setPointerCapture(event.pointerId);
      this.dragging = { x: event.clientX, y: event.clientY };
    });
    canvas.addEventListener("pointermove", (event) => {
      if (!this.dragging) return;
      const scale = 0.0085;
      this.azimuth += (event.clientX - this.dragging.x) * scale;
      this.elevation = Math.min(Math.PI / 2 - 0.01, Math.max(0.01,
        this.elevation + (event.clientY - this.dragging.y) * scale));
      this.dragging = { x: event.clientX, y: event.clientY };
      this.dirty();
    });
    canvas.addEventListener("pointerup", () => { this.dragging = null; });
    canvas.addEventListener("wheel", (event) => {
      event.preventDefault();
      this.zoom *= event.deltaY < 0 ? 1.1 : 0.9;
      this.zoom = Math.min(20, Math.max(0.2, this.zoom));
      this.dirty();
    }, { passive: false });
    canvas.addEventListener("dblclick", () => this.resetView());
    const loop = () => { if (state.dirty) { state.dirty = false; this.draw(); } requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
  },

  resize() {
    this.dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.max(1, Math.round(rect.width * this.dpr));
    this.canvas.height = Math.max(1, Math.round(rect.height * this.dpr));
  },

  resetView() {
    this.azimuth = -Math.PI / 5;
    this.elevation = Math.PI / 5;
    this.zoom = 1;
    this.dirty();
  },

  dirty() { state.dirty = true; },

  setMesh(mesh) {
    state.mesh = mesh;
    if (mesh.count > 0) this.computeFit(mesh);
    this.dirty();
  },

  computeFit(mesh) {
    let minX = Infinity, minY = Infinity, minZ = Infinity;
    let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
    for (let i = 0; i < mesh.positions.length; i += 3) {
      minX = Math.min(minX, mesh.positions[i]); maxX = Math.max(maxX, mesh.positions[i]);
      minY = Math.min(minY, mesh.positions[i + 1]); maxY = Math.max(maxY, mesh.positions[i + 1]);
      minZ = Math.min(minZ, mesh.positions[i + 2]); maxZ = Math.max(maxZ, mesh.positions[i + 2]);
    }
    this.fit = {
      cx: (minX + maxX) / 2, cy: (minY + maxY) / 2, cz: (minZ + maxZ) / 2,
      radius: Math.max(maxX - minX, maxY - minY, maxZ - minZ) / 2 || 1,
      dims: [maxX - minX, maxY - minY, maxZ - minZ],
    };
  },

  rotation() {
    // turntable basis: orbit by azimuth around world Z, then tilt by
    // elevation. Rows: screen-x (right), screen-y (up), view-z (toward
    // the viewer) — derived from right/up/forward of a camera at
    // (az, el) with world Z as up hint.
    const { azimuth, elevation } = this;
    const sa = Math.sin(azimuth), ca = Math.cos(azimuth);
    const se = Math.sin(elevation), ce = Math.cos(elevation);
    return [
      -sa, ca, 0,
      -ca * se, -sa * se, ce,
      ce * ca, ce * sa, se,
    ];
  },

  transform(p, rotation, fit, scale, width, height) {
    const dx = p[0] - fit.cx, dy = p[1] - fit.cy, dz = p[2] - fit.cz;
    const x = rotation[0] * dx + rotation[1] * dy + rotation[2] * dz;
    const y = rotation[3] * dx + rotation[4] * dy + rotation[5] * dz;
    const z = rotation[6] * dx + rotation[7] * dy + rotation[8] * dz;
    return [width / 2 + x * scale, height / 2 - y * scale, z];
  },

  draw() {
    const { ctx, canvas } = this;
    const width = canvas.width, height = canvas.height;
    ctx.clearRect(0, 0, width, height);
    if (!this.fit || !state.mesh) return;

    // canvas width/height are already device pixels; 3.6 leaves room for
    // the screen-space diagonal of a cube (≈2.83·radius)
    const scale = (Math.min(width, height) / (3.6 * this.fit.radius)) * this.zoom;
    const rotation = this.rotation();

    this.drawGrid(rotation, scale, width, height);
    this.drawMesh(rotation, scale, width, height);
    this.drawTriad(rotation, width, height);
    this.drawDims(width, height);
  },

  drawGrid(rotation, scale, width, height) {
    const ctx = this.ctx;
    const fit = this.fit;
    const step = niceStep(fit.radius * 2);
    const extent = Math.ceil((fit.radius * 1.6) / step) * step;
    ctx.strokeStyle = "rgba(90, 130, 190, 0.14)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let g = -extent; g <= extent + 1e-9; g += step) {
      const a = this.transform([g, -extent, fit.cz - fit.radius], rotation, fit, scale, width, height);
      const b = this.transform([g, extent, fit.cz - fit.radius], rotation, fit, scale, width, height);
      const c = this.transform([-extent, g, fit.cz - fit.radius], rotation, fit, scale, width, height);
      const d = this.transform([extent, g, fit.cz - fit.radius], rotation, fit, scale, width, height);
      ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]);
      ctx.moveTo(c[0], c[1]); ctx.lineTo(d[0], d[1]);
    }
    ctx.stroke();
  },

  drawMesh(rotation, scale, width, height) {
    const ctx = this.ctx;
    const mesh = state.mesh;
    const pos = mesh.positions, nrm = mesh.normals;
    // light in view space: key + fill
    const L1 = norm3([-0.45, 0.65, 0.61]);
    const L2 = norm3([0.6, -0.3, 0.74]);
    const order = new Array(mesh.count);
    const projected = new Float32Array(mesh.count * 9);
    const shaded = new Float32Array(mesh.count);
    for (let t = 0; t < mesh.count; t++) {
      let depth = 0;
      let shade = 0;
      for (let v = 0; v < 3; v++) {
        const i = t * 9 + v * 3;
        const p = this.transform([pos[i], pos[i + 1], pos[i + 2]], rotation, this.fit, scale, width, height);
        projected.set(p, t * 9 + v * 3);
        depth += p[2];
      }
      // rotate the triangle normal into view space
      const nx = nrm[t * 9], ny = nrm[t * 9 + 1], nz = nrm[t * 9 + 2];
      const rx = rotation[0] * nx + rotation[1] * ny + rotation[2] * nz;
      const ry = rotation[3] * nx + rotation[4] * ny + rotation[5] * nz;
      const rz = rotation[6] * nx + rotation[7] * ny + rotation[8] * nz;
      const light = Math.max(0, rx * L1[0] + ry * L1[1] + rz * L1[2]) * 0.8
        + Math.max(0, rx * L2[0] + ry * L2[1] + rz * L2[2]) * 0.35;
      shaded[t] = 0.22 + Math.min(0.85, light);
      order[t] = t;
    }
    // view-space z points toward the viewer: draw farthest (smallest) first
    order.sort((a, b) => depthOf(a, projected) - depthOf(b, projected));
    ctx.lineWidth = this.dpr;
    for (const t of order) {
      const x0 = projected[t * 9], y0 = projected[t * 9 + 1];
      const x1 = projected[t * 9 + 3], y1 = projected[t * 9 + 4];
      const x2 = projected[t * 9 + 6], y2 = projected[t * 9 + 7];
      // backface culling: closed solids never show their far side, and
      // painting front faces only removes large-triangle sort artifacts
      const nx = nrm[t * 9], ny = nrm[t * 9 + 1], nz = nrm[t * 9 + 2];
      const rz = rotation[6] * nx + rotation[7] * ny + rotation[8] * nz;
      if (rz <= 0) continue;
      const level = shaded[t];
      ctx.fillStyle = `rgb(${Math.round(96 + 90 * level)}, ${Math.round(112 + 96 * level)}, ${Math.round(132 + 100 * level)})`;
      ctx.strokeStyle = ctx.fillStyle;
      ctx.beginPath();
      ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.lineTo(x2, y2);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }
    function depthOf(t, proj) {
      return proj[t * 9 + 2] + proj[t * 9 + 5] + proj[t * 9 + 8];
    }
  },

  drawTriad(rotation, width, height) {
    const ctx = this.ctx;
    const origin = [40 * this.dpr, height - 40 * this.dpr];
    const length = 26 * this.dpr;
    const axes = [
      { p: [1, 0, 0], label: "X", color: "#e5534b" },
      { p: [0, 1, 0], label: "Y", color: "#4e9a61" },
      { p: [0, 0, 1], label: "Z", color: "#5a8fce" },
    ];
    ctx.font = `${11 * this.dpr}px ${getComputedStyle(document.body).getPropertyValue("--mono")}`;
    for (const axis of axes) {
      const end = [
        origin[0] + (rotation[0] * axis.p[0] + rotation[1] * axis.p[1] + rotation[2] * axis.p[2]) * length,
        origin[1] - (rotation[3] * axis.p[0] + rotation[4] * axis.p[1] + rotation[5] * axis.p[2]) * length,
      ];
      ctx.strokeStyle = axis.color;
      ctx.lineWidth = 1.5 * this.dpr;
      ctx.beginPath();
      ctx.moveTo(origin[0], origin[1]);
      ctx.lineTo(end[0], end[1]);
      ctx.stroke();
      ctx.fillStyle = axis.color;
      ctx.fillText(axis.label, end[0] + 4 * this.dpr, end[1] + 4 * this.dpr);
    }
  },

  drawDims(width, height) {
    const el = $("vp-dims");
    if (!this.fit || !this.fit.dims) { el.textContent = ""; return; }
    const [dx, dy, dz] = this.fit.dims;
    el.textContent = `ΔX ${fmt(dx)}  ΔY ${fmt(dy)}  ΔZ ${fmt(dz)} mm`;
  },
};

function norm3(v) {
  const length = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / length, v[1] / length, v[2] / length];
}

function niceStep(range) {
  const raw = range / 8;
  const power = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  for (const mult of [1, 2, 5, 10]) {
    if (raw <= mult * power) return mult * power;
  }
  return 10 * power;
}

function fmt(value) {
  return Number(value.toFixed(2)).toString();
}

/* ------------------------------------------------------------------ */
/* parameters + build flow                                              */
/* ------------------------------------------------------------------ */

let buildTimer = null;

function scheduleBuild() {
  clearTimeout(buildTimer);
  buildTimer = setTimeout(runBuild, DEBOUNCE_MS);
}

async function runBuild() {
  const name = state.active.name;
  setStatus("building…", "pill-pending");
  try {
    const result = await apiPost("/api/build", { model: name, overrides: state.overrides });
    renderBuild(result);
    // panels and mesh load after the verdict, in parallel
    loadReport(result.build_id);
    if (result.stl_url) loadMesh(result.stl_url);
  } catch (error) {
    setStatus(`studio error: ${error.message}`, "pill-error");
  }
}

async function loadReport(buildId) {
  try {
    const report = await apiGet(`/api/report?build=${buildId}`);
    // hide the assumptions table when the ledger has no parameter rows
    const ledgerLines = (report.assumptions_markdown || "").trim().split("\n");
    const assumptions = ledgerLines.length >= 3 ? report.assumptions_markdown : null;
    renderChecks(assumptions, state.lastResult);
    renderGraph(report.graph_markdown, report.mermaid);
    $("context-body").textContent = report.context_markdown;
  } catch (error) {
    $("checks-body").prepend(
      Object.assign(document.createElement("div"), {
        className: "finding finding-error",
        textContent: `report failed: ${error.message}`,
      })
    );
  }
}

async function loadMesh(url) {
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error("stl unavailable");
    viewer.setMesh(parseStl(await response.arrayBuffer()));
    $("strip-mesh").textContent = `${state.mesh.count.toLocaleString()} triangles`;
  } catch (error) {
    $("strip-mesh").textContent = "mesh unavailable";
  }
}

/* ------------------------------------------------------------------ */
/* rendering: parameters, checks, graph                                 */
/* ------------------------------------------------------------------ */

function renderParams() {
  const container = $("params");
  container.replaceChildren();
  for (const parameter of state.active.parameters) {
    const value = state.overrides[parameter.name];
    const wrap = document.createElement("div");
    wrap.className = "param";
    wrap.dataset.param = parameter.name;

    const head = document.createElement("div");
    head.className = "param-head";
    const name = document.createElement("span");
    name.className = "param-name";
    name.textContent = parameter.name;
    name.id = `label-${parameter.name}`;
    const unit = document.createElement("span");
    unit.className = "param-unit";
    unit.textContent = parameter.unit || "";
    head.append(name, unit);

    const row = document.createElement("div");
    row.className = "param-row";
    const range = document.createElement("input");
    range.type = "range";
    const numeric = typeof value === "number";
    if (numeric && parameter.minimum != null) range.min = parameter.minimum;
    if (numeric && parameter.maximum != null) range.max = parameter.maximum;
    if (numeric && parameter.step) range.step = parameter.step;
    range.value = value;
    range.setAttribute("aria-labelledby", `label-${parameter.name}`);
    const number = document.createElement("input");
    number.type = typeof value === "number" ? "number" : "text";
    if (typeof value === "number") {
      if (parameter.minimum != null) number.min = parameter.minimum;
      if (parameter.maximum != null) number.max = parameter.maximum;
      if (parameter.step) number.step = parameter.step;
    }
    number.value = value;

    const apply = (raw) => {
      const parsed = typeof value === "number" ? parseFloat(raw) : raw;
      if (raw === "" || Number.isNaN(parsed)) return;
      state.overrides[parameter.name] = parsed;
      range.value = parsed;
      number.value = parsed;
      scheduleBuild();
    };
    range.addEventListener("input", () => apply(range.value));
    // "input" so Enter commits too; the debounce absorbs per-keystroke events
    number.addEventListener("input", () => apply(number.value));
    number.addEventListener("change", () => apply(number.value));
    row.append(range, number);

    const errorLine = document.createElement("div");
    errorLine.className = "param-error";
    errorLine.dataset.role = "param-error";

    wrap.append(head, row, errorLine);
    container.append(wrap);
  }
}

function renderBuild(result) {
  state.lastResult = result;
  state.buildId = result.build_id;
  $("strip-rebuild").textContent = `rebuild ${result.rebuild_ms} ms`;

  // per-parameter inline errors: the finding that names the parameter
  for (const wrap of document.querySelectorAll(".param")) {
    const name = wrap.dataset.param;
    const slot = wrap.querySelector('[data-role="param-error"]');
    slot.textContent = result.errors.find((message) => message.startsWith(`${name}=`)) || "";
  }

  renderChecks(null, result);
  const pillState = result.errors.length ? "pill-error" : result.warnings.length ? "pill-warn" : "pill-ok";
  setStatus(
    result.errors.length
      ? `${result.errors.length} error${result.errors.length > 1 ? "s" : ""}`
      : result.warnings.length
        ? `ok · ${result.warnings.length} warning${result.warnings.length > 1 ? "s" : ""}`
        : "ok",
    pillState
  );
}

function renderChecks(assumptions, result) {
  const body = $("checks-body");
  const summary = $("error-summary");
  const errors = result ? result.errors : [];
  const warnings = result ? result.warnings : [];

  summary.hidden = errors.length === 0;
  if (errors.length) {
    const heading = document.createElement("div");
    heading.textContent = `${errors.length} blocking problem${errors.length > 1 ? "s" : ""}:`;
    const list = document.createElement("ul");
    for (const message of errors) {
      const item = document.createElement("li");
      item.textContent = message;
      list.append(item);
    }
    summary.replaceChildren(heading, list);
  }

  body.replaceChildren();
  body.append(section("Interference", findingList(interferenceFindings(result))));
  body.append(section("Design state", findingList(stateFindings(result))));
  if (assumptions) {
    const pre = document.createElement("pre");
    pre.className = "mono-pre";
    pre.textContent = assumptions;
    body.append(section("Facts vs assumptions", pre));
  }
}

function section(title, node) {
  const wrap = document.createElement("div");
  wrap.className = "check-section";
  const heading = document.createElement("h3");
  heading.className = "check-title";
  heading.textContent = title;
  wrap.append(heading, node);
  return wrap;
}

const ICONS = {
  error: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8v5m0 3h.01"/></svg>',
  warn: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 4 2.5 20h19L12 4Z"/><path d="M12 10v4m0 3h.01"/></svg>',
  ok: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m8.5 12.5 2.5 2.5 4.5-5"/></svg>',
  info: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v5m0-8h.01"/></svg>',
};

function findingList(findings) {
  const wrap = document.createElement("div");
  if (!findings.length) {
    const line = document.createElement("div");
    line.className = "finding finding-info";
    line.innerHTML = `${ICONS.info}<span>nothing to report</span>`;
    wrap.append(line);
    return wrap;
  }
  for (const finding of findings) {
    const line = document.createElement("div");
    line.className = `finding finding-${finding.kind}`;
    line.innerHTML = `${ICONS[finding.kind]}<span></span>`;
    line.lastChild.textContent = finding.text;
    wrap.append(line);
  }
  return wrap;
}

function interferenceFindings(result) {
  if (!result) return [];
  const findings = [];
  const interference = result.interference;
  if (!interference) return [{ kind: "info", text: "interference checks disabled" }];
  for (const pair of interference.pairs) {
    if (pair.status === "interference") {
      findings.push({ kind: "error", text: `${pair.a} <-> ${pair.b}: overlap ${pair.interference_volume} mm³` });
    } else if (pair.status === "contact") {
      findings.push({ kind: "warn", text: `${pair.a} <-> ${pair.b}: contact ${pair.contact_area} mm²` });
    } else {
      findings.push({ kind: "ok", text: `${pair.a} <-> ${pair.b}: clearance ${pair.clearance} mm` });
    }
  }
  return findings;
}

function stateFindings(result) {
  if (!result) return [];
  const findings = result.errors.map((text) => ({ kind: "error", text }));
  findings.push(...result.warnings.map((text) => ({ kind: "warn", text })));
  return findings;
}

function renderGraph(graphMarkdown, mermaid) {
  const body = $("graph-body");
  if (!graphMarkdown) {
    body.textContent = "no graph (single part or disabled)";
    return;
  }
  body.textContent = `${graphMarkdown}\n\n— mermaid —\n${mermaid}`;
}

function setStatus(text, pillClass) {
  const pill = $("status-pill");
  pill.textContent = text;
  pill.className = `pill ${pillClass}`;
}

/* ------------------------------------------------------------------ */
/* boot                                                                 */
/* ------------------------------------------------------------------ */

async function boot() {
  viewer.init($("view"));
  try {
    const payload = await apiGet("/api/models");
    state.models = payload.models;
  } catch (error) {
    setStatus(`cannot reach server: ${error.message}`, "pill-error");
    return;
  }
  if (!state.models.length) {
    setStatus("no models registered", "pill-error");
    return;
  }
  const select = $("model-select");
  for (const manifest of state.models) {
    const option = document.createElement("option");
    option.value = manifest.name;
    option.textContent = manifest.name;
    select.append(option);
  }
  select.addEventListener("change", () => selectModel(select.value));
  selectModel(state.models[0].name);
}

function selectModel(name) {
  state.active = state.models.find((manifest) => manifest.name === name);
  state.overrides = Object.fromEntries(
    state.active.parameters.map((parameter) => [parameter.name, parameter.default])
  );
  renderParams();
  runBuild();
}

function initTabs() {
  for (const button of document.querySelectorAll(".tab")) {
    button.addEventListener("click", () => {
      for (const other of document.querySelectorAll(".tab")) {
        const active = other === button;
        other.classList.toggle("is-active", active);
        other.setAttribute("aria-selected", active ? "true" : "false");
      }
      for (const pane of document.querySelectorAll(".pane")) {
        pane.classList.toggle("is-active", pane.id === button.getAttribute("aria-controls"));
      }
    });
  }
}

boot();
initTabs();
