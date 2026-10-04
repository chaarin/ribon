// 공구 유지보수 Multi-Agent 시연 화면.
// 서버(src/web/server.py)가 실제 QIT-CEMC 기록을 한 Cycle씩 재생하고, 화면은 그 결과를 그린다.

const $ = (sel) => document.querySelector(sel);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

const ACTION_LABEL = {
  CONTINUE: "계속 가공",
  REMEASURE: "센서 재측정",
  INSPECT_EDGE: "날 검사",
  REPLACE_AFTER_JOB: "윙 리브 마친 뒤 교체",
  REPLACE_NOW: "즉시 교체",
};
const actionLabel = (d) =>
  d.action === "INSPECT_EDGE" ? (d.target_edge ? `Edge ${d.target_edge} 검사` : "4개 날 검사") : ACTION_LABEL[d.action];
const fmt = (v, n = 3) => (v == null || Number.isNaN(v) ? "–" : Number(v).toFixed(n));
const EDGE_VARS = ["--edge1", "--edge2", "--edge3", "--edge4"];
const SENSOR_LABELS = { Fx_std: "Fx (N)", Fy_std: "Fy (N)", Fz_std: "Fz (N)", Mz_std: "Mz (N·m)" };

const S = {
  meta: null,
  presetId: null,
  sid: null,
  records: [],
  first: new Map(), // Cycle → 그 Cycle의 첫 판단 (센서 예측 기준)
  last: new Map(), // Cycle → 그 Cycle의 마지막 판단 (검사 반영 후)
  truth: null,
  timer: null,
  finished: false,
  startRemaining: null,
  lastRisk: null,
};

// ---------- 초기화 ----------

async function init() {
  S.meta = await api("GET", "/api/presets");
  fillDefaults();
  $("#startBtn").onclick = start;
  $("#stepBtn").onclick = () => step().catch(showError);
  $("#playBtn").onclick = togglePlay;
  $("#resetBtn").onclick = reset;
  $("#truthToggle").onchange = renderWearChart;
  $("#scale").onchange = renderComparison;
  $("#inspForm").onsubmit = submitInspection;
  $("#customForm").elements.tool_purpose.onchange = () => { if (!S.sid) renderWearChart(); };
  renderWearChart();
  renderSensors();
}

// 조건 입력란을 기본 상황(정삭 공구 프리셋)의 값으로 채운다
function fillDefaults() {
  S.presetId = S.meta.default;
  const ctx = S.meta.presets.find((p) => p.id === S.presetId).context;
  const f = $("#customForm");
  for (const key of ["tool_purpose", "change_time_min", "tool_stock", "due_slack_min", "production_priority", "process_progress_pct"]) {
    f.elements[key].value = ctx[key];
  }
  f.elements.inspection_available.checked = ctx.inspection_available;
}

function readOverrides() {
  const f = $("#customForm").elements;
  return {
    tool_purpose: f.tool_purpose.value,
    change_time_min: Number(f.change_time_min.value),
    tool_stock: Number(f.tool_stock.value),
    due_slack_min: Number(f.due_slack_min.value),
    production_priority: f.production_priority.value,
    inspection_available: f.inspection_available.checked,
    process_progress_pct: Number(f.process_progress_pct.value),
  };
}

// ---------- 진행 ----------

async function start() {
  reset();
  try {
    const res = await api("POST", "/api/sessions", { preset_id: S.presetId, overrides: readOverrides() });
    S.sid = res.session_id;
    S.startRemaining = res.context.remaining_parts;
    if (!S.truth) S.truth = await api("GET", "/api/truth");
    setControls(true);
    const c = res.context;
    addLog("시작", `${purposeLabel(c.tool_purpose)} 공구, 교체 ${c.change_time_min}분, ` +
      `재고 ${c.tool_stock}개, 납기 여유 ${c.due_slack_min}분, 검사 ${c.inspection_available ? "가능" : "불가"}`);
  } catch (e) {
    showError(e);
  }
}

function reset() {
  stopPlay();
  Object.assign(S, { sid: null, records: [], finished: false, lastRisk: null });
  S.first.clear();
  S.last.clear();
  $("#log").innerHTML = "";
  $("#endCard").hidden = true;
  $("#truthToggle").checked = false;
  for (const id of ["#agWear", "#agQuality", "#agEcon", "#agMaster"]) {
    const body = $(id).querySelector(".body");
    body.className = "body empty";
    body.textContent = id === "#agWear" ? "시연을 시작하세요" : "–";
  }
  renderStatus(null);
  renderWearChart();
  renderSensors();
  setControls(false);
}

function setControls(on) {
  $("#playBtn").disabled = !on || S.finished;
  $("#stepBtn").disabled = !on || S.finished;
  $("#resetBtn").disabled = !S.sid;
}

async function step() {
  if (!S.sid || S.finished) return;
  const rec = await api("POST", `/api/sessions/${S.sid}/step`);
  handle(rec);
}

function togglePlay() {
  if (S.timer) return stopPlay();
  $("#playBtn").textContent = "⏸ 일시 정지";
  const tick = async () => {
    try {
      await step();
    } catch (e) {
      stopPlay();
      return showError(e);
    }
    if (S.timer && !S.finished && !currentPending()) S.timer = setTimeout(tick, Number($("#speed").value));
    else stopPlay();
  };
  S.timer = setTimeout(tick, 0);
}

function stopPlay() {
  clearTimeout(S.timer);
  S.timer = null;
  $("#playBtn").textContent = "▶ 자동 재생";
}

const currentPending = () => S.records.at(-1)?.pending;

function handle(rec) {
  S.records.push(rec);
  if (!S.first.has(rec.cycle)) S.first.set(rec.cycle, rec);
  S.last.set(rec.cycle, rec);
  S.finished = rec.finished;
  logRecord(rec);
  renderStatus(rec);
  renderWearChart();
  renderSensors();
  renderAgents(rec);
  setControls(true);
  if (rec.pending?.type === "inspection") {
    stopPlay();
    openInspection(rec);
  } else if (rec.pending?.type === "remeasure") {
    api("POST", `/api/sessions/${S.sid}/remeasure`).then(handle).catch(showError);
  } else if (rec.finished) {
    stopPlay();
    showEnd(rec);
  }
}

// ---------- 검사 ----------

function openInspection(rec) {
  const p = rec.pending;
  $("#inspTitle").textContent = `Cycle ${rec.cycle} · ${p.edges.length === 4 ? "4개 날" : `Edge ${p.edges[0]}`} 현미경 검사`;
  $("#inspWhy").textContent = rec.decision.reasons[0];
  $("#inspInputs").innerHTML = p.edges
    .map(
      (e) => `<label><span style="color:var(--edge${e})">●</span> Edge ${e} VBmax (mm)
        <input name="e${e}" type="number" step="0.001" min="0" max="2" value="${fmt(p.suggested[e])}" required></label>`
    )
    .join("");
  $("#inspDialog").showModal();
  $("#inspInputs input").focus();
}

async function submitInspection(ev) {
  ev.preventDefault();
  const rec = S.records.at(-1);
  const values = {};
  for (const e of rec.pending.edges) values[e] = Number($("#inspForm").elements[`e${e}`].value);
  $("#inspDialog").close();
  try {
    handle(await api("POST", `/api/sessions/${S.sid}/inspection`, { values }));
  } catch (e) {
    showError(e);
  }
}

// ---------- 상태 ----------

function purposeLabel(p) {
  return S.meta.tool_purposes[p]?.label ?? p;
}

function renderStatus(rec) {
  $("#stCycle").textContent = rec ? `${rec.cycle} / ${S.meta.total_cycles}` : "–";
  if (rec) {
    const m = Math.round(rec.cut_time_min);
    $("#stTime").textContent = `${Math.floor(m / 60)}시간 ${m % 60}분`;
    const ribNo = S.startRemaining - rec.context.remaining_parts + 1;
    $("#stRib").textContent = `#${ribNo} (남은 ${rec.context.remaining_parts}개)`;
    $("#stProgress").style.width = `${rec.context.process_progress_pct}%`;
  } else {
    $("#stTime").textContent = "–";
    $("#stRib").textContent = "–";
    $("#stProgress").style.width = "0";
  }
  $("#stInsp").textContent = `${S.records.filter((r) => r.kind === "inspection").length}회`;
}

// ---------- 그래프 ----------

function svgEl(tag, attrs = {}, text) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (text != null) el.textContent = text;
  return el;
}

function renderWearChart() {
  const W = 900, H = 300, L = 46, R = 70, T = 12, B = 30;
  const total = S.meta?.total_cycles ?? 68;
  const showTruth = $("#truthToggle").checked && S.truth;
  const ctx = S.records.at(-1)?.context;
  const purpose = ctx?.tool_purpose ?? $("#customForm")?.elements.tool_purpose.value ?? "finishing";
  const caution = S.meta?.tool_purposes[purpose]?.caution_vb_mm ?? 0.2;
  const limit = S.meta?.vb_limit_mm ?? 0.3;

  const firsts = [...S.first.values()];
  const seenMax = Math.max(0, ...firsts.map((r) => r.wear.vb_max + r.wear.edges[r.wear.worst_edge - 1].uncertainty_mm));
  const measuredMax = Math.max(0, ...S.records.flatMap((r) => r.wear.edges.filter((e) => e.measured).map((e) => e.vb_max_mm)));
  const yMax = Math.max(0.45, showTruth ? Math.max(...S.truth.worst_vb_mm) + 0.05 : 0, seenMax + 0.03, measuredMax + 0.03);
  const x = (c) => L + ((c - 1) / (total - 1)) * (W - L - R);
  const y = (v) => T + (1 - Math.min(v, yMax) / yMax) * (H - T - B);

  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Cycle별 최대 날 마모 그래프" });
  // 구간 배경
  svg.append(svgEl("rect", { x: L, y: y(limit), width: W - L - R, height: y(caution) - y(limit), fill: css("--warn-soft") }));
  svg.append(svgEl("rect", { x: L, y: T, width: W - L - R, height: y(limit) - T, fill: css("--danger-soft") }));
  // 눈금
  for (let v = 0; v <= yMax + 1e-9; v += 0.1) {
    svg.append(svgEl("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: css("--grid") }));
    svg.append(svgEl("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end" }, v.toFixed(1)));
  }
  for (let c = 1; c <= total; c += c === 1 ? 9 : 10) {
    svg.append(svgEl("text", { x: x(c), y: H - 10, "text-anchor": "middle" }, c));
  }
  svg.append(svgEl("text", { x: W - R, y: H - 10, "text-anchor": "end" }, "Cycle"));
  svg.append(svgEl("text", { x: L, y: T + 10, "text-anchor": "start" }, "mm"));
  // 기준선
  svg.append(svgEl("line", { x1: L, x2: W - R, y1: y(caution), y2: y(caution), stroke: css("--warn"), "stroke-dasharray": "5 4", "stroke-width": 1.5 }));
  svg.append(svgEl("text", { x: W - R + 4, y: y(caution) + 4, style: `fill:${css("--warn")}` }, `주의 ${caution}`));
  svg.append(svgEl("line", { x1: L, x2: W - R, y1: y(limit), y2: y(limit), stroke: css("--danger"), "stroke-width": 1.5 }));
  svg.append(svgEl("text", { x: W - R + 4, y: y(limit) + 4, style: `fill:${css("--danger")}` }, `한계 ${limit}`));

  // 정답 (실제 측정값)
  if (showTruth) {
    const path = (arr) => arr.map((v, i) => `${i ? "L" : "M"}${x(i + 1)},${y(v)}`).join("");
    svg.append(svgEl("path", { d: path(S.truth.mean_vb_mm), fill: "none", stroke: css("--truth"), "stroke-dasharray": "1 4", "stroke-width": 1.5 }));
    svg.append(svgEl("path", { d: path(S.truth.worst_vb_mm), fill: "none", stroke: css("--truth"), "stroke-dasharray": "5 4", "stroke-width": 1.5 }));
  }

  // 센서 예측 + 불확실성 띠 (각 Cycle 첫 판단 기준)
  if (firsts.length) {
    const pts = firsts.map((r) => {
      const u = r.wear.edges[r.wear.worst_edge - 1].uncertainty_mm;
      return { c: r.cycle, v: r.wear.vb_max, lo: Math.max(0, r.wear.vb_max - u), hi: r.wear.vb_max + u };
    });
    const band = pts.map((p, i) => `${i ? "L" : "M"}${x(p.c)},${y(p.hi)}`).join("") +
      pts.slice().reverse().map((p) => `L${x(p.c)},${y(p.lo)}`).join("") + "Z";
    svg.append(svgEl("path", { d: band, fill: css("--band"), stroke: "none" }));
    svg.append(svgEl("path", { d: pts.map((p, i) => `${i ? "L" : "M"}${x(p.c)},${y(p.v)}`).join(""), fill: "none", stroke: css("--accent"), "stroke-width": 2 }));
  }

  // 검사 실측값
  for (const r of S.records.filter((r) => r.kind === "inspection")) {
    svg.append(svgEl("line", { x1: x(r.cycle), x2: x(r.cycle), y1: T, y2: H - B, stroke: css("--accent"), "stroke-dasharray": "2 3", opacity: 0.5 }));
    r.wear.edges.filter((e) => e.measured).forEach((e) => {
      svg.append(svgEl("circle", { cx: x(r.cycle), cy: y(e.vb_max_mm), r: 4.5, fill: css(EDGE_VARS[e.edge_id - 1]), stroke: css("--panel"), "stroke-width": 1.5 }));
    });
  }

  // 현재 위치, 교체 표시
  const cur = S.records.at(-1);
  if (cur) {
    const color = cur.finished && cur.decision.action.startsWith("REPLACE") ? css("--danger") : css("--muted");
    svg.append(svgEl("line", { x1: x(cur.cycle), x2: x(cur.cycle), y1: T, y2: H - B, stroke: color, "stroke-width": cur.finished ? 2 : 1 }));
    if (cur.finished && cur.decision.action.startsWith("REPLACE")) {
      svg.append(svgEl("text", { x: x(cur.cycle) + 4, y: T + 12, style: `fill:${css("--danger")};font-weight:700` }, `교체 · Cycle ${cur.cycle}`));
    }
  }

  const box = $("#wearChart");
  box.innerHTML = "";
  box.append(svg);

  const edgeDots = [1, 2, 3, 4].map((e) => `<span><i class="dot" style="background:var(--edge${e})"></i>Edge ${e} 실측</span>`).join("");
  $("#wearLegend").innerHTML =
    `<span><i style="background:var(--accent)"></i>센서 예측 최대 마모 (+최근 검사 보정)</span>` +
    `<span><i style="background:var(--band);height:8px"></i>예측 불확실성 ±σ</span>` + edgeDots +
    (showTruth ? `<span><i class="dash"></i>실제 최대 날</span><span><i class="dash" style="background:repeating-linear-gradient(90deg,var(--truth) 0 1px,transparent 1px 5px)"></i>실제 4날 평균</span>` : "");
}

function renderSensors() {
  const box = $("#sensorCharts");
  box.innerHTML = "";
  const firsts = [...S.first.values()];
  const total = S.meta?.total_cycles ?? 68;
  for (const [key, label] of Object.entries(SENSOR_LABELS)) {
    const vals = firsts.map((r) => [r.cycle, r.sensor[key]]).filter(([, v]) => v != null);
    const div = document.createElement("div");
    div.className = "sensor";
    const latest = vals.at(-1)?.[1];
    div.innerHTML = `<div class="name">${label}</div><div class="val">${latest == null ? "–" : latest.toFixed(key === "Mz_std" ? 3 : 1)}</div>`;
    const W = 200, H = 44;
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", "aria-hidden": "true" });
    if (vals.length > 1) {
      const max = Math.max(...vals.map(([, v]) => v)) * 1.1;
      const d = vals.map(([c, v], i) => `${i ? "L" : "M"}${((c - 1) / (total - 1)) * W},${H - (v / max) * (H - 4) - 2}`).join("");
      svg.append(svgEl("path", { d, fill: "none", stroke: css("--accent"), "stroke-width": 1.5, "vector-effect": "non-scaling-stroke" }));
    }
    div.append(svg);
    box.append(div);
  }
}

// ---------- Agent 카드 ----------

function setBody(id, html) {
  const body = $(id).querySelector(".body");
  body.className = "body";
  body.innerHTML = html;
}

function renderAgents(rec) {
  const { wear, quality, economics, decision, context } = rec;
  const caution = quality.caution_vb_mm, limit = S.meta.vb_limit_mm, scaleMax = 0.45;
  const pct = (v) => `${Math.min(100, (v / scaleMax) * 100)}%`;

  const edges = wear.edges.map((e) => `
    <div class="edge-row">
      <span style="color:var(--edge${e.edge_id})">● Edge ${e.edge_id}</span>
      <div class="edge-bar">
        <div class="fill" style="width:${pct(e.vb_max_mm)};background:var(--edge${e.edge_id})"></div>
        <div class="tick" style="left:${pct(caution)};background:var(--warn)"></div>
        <div class="tick" style="left:${pct(limit)};background:var(--danger)"></div>
      </div>
      <span class="edge-val">${fmt(e.vb_max_mm)}${e.measured ? '<span class="tag meas">실측</span>' : `<span class="tag pred">±${fmt(e.uncertainty_mm, 2)}</span>`}</span>
    </div>`).join("");
  const sensorOnly = wear.edges.every((e) => !e.measured) && new Set(wear.edges.map((e) => e.vb_max_mm.toFixed(4))).size === 1;
  setBody("#agWear", `${edges}
    <dl class="kv" style="margin-top:8px">
      <dt>최대 / 평균</dt><dd>${fmt(wear.vb_max)} / ${fmt(wear.vb_mean)} mm (가장 많이 닳은 날 Edge ${wear.worst_edge})</dd>
      <dt>편마모</dt><dd>${wear.uneven_flag ? "편마모" : "정상"} (지수 ${fmt(wear.uneven_index, 2)}, 날 간 차이 ${fmt(wear.wear_difference_mm)} mm)</dd>
      <dt>센서 품질</dt><dd>${fmt(wear.signal_quality, 2)}${wear.notes.length ? " · " + wear.notes.join(", ") : ""}</dd>
    </dl>
    ${sensorOnly ? '<p class="hint">센서로는 어느 날이 닳았는지 구분할 수 없어 4날 모두 같은 예측값을 씁니다. 날별 값은 검사로 확인합니다.</p>' : ""}`);

  setBody("#agQuality", `
    <span class="risk ${quality.risk_level}">${quality.risk_level}</span>
    <span class="conf">${purposeLabel(quality.tool_purpose)} 공구 · 주의 ${quality.caution_vb_mm} mm · 한계 ${limit} mm</span>
    <ul class="reasons">${quality.drivers.map((d) => `<li>${d}</li>`).join("")}</ul>
    ${quality.reasons[1] ? `<p class="hint">${quality.reasons[1]}</p>` : ""}`);

  const losses = [
    ["지금 교체", economics.loss_replace_now_min],
    ["윙 리브 마친 뒤 교체", economics.loss_replace_after_rib_min],
    ["계속 가공", economics.loss_continue_min],
  ];
  const lmax = Math.max(1, ...losses.map(([, v]) => v));
  const lmin = Math.min(...losses.map(([, v]) => v));
  const showVoi = !wear.edges.some((e) => e.measured) && context.inspection_available;
  setBody("#agEcon", `
    ${losses.map(([name, v]) => `
      <div class="loss-row ${v === lmin ? "best" : ""}"><span>${name}</span>
        <div class="loss-bar"><div style="width:${(v / lmax) * 100}%"></div></div>
        <span class="num">${v.toFixed(1)}분</span></div>`).join("")}
    <dl class="kv" style="margin-top:8px">
      <dt>윙 리브</dt><dd>진행률 ${Math.round(context.process_progress_pct)}%, 남은 ${economics.cycles_left_in_rib} Cycle</dd>
      ${showVoi ? `<dt>검사 가치</dt><dd>${economics.inspection_value_min.toFixed(1)}분 vs 검사 ${economics.inspection_time_min}분 → ${economics.inspection_value_min >= economics.inspection_time_min ? "검사 이득" : "검사 불필요"}</dd>` : ""}
      <dt>생산 압박</dt><dd><span class="risk ${economics.production_pressure}" style="font-size:12px;padding:0 6px">${economics.production_pressure}</span>
        납기 여유 ${context.due_slack_min}분, 우선순위 ${context.production_priority}</dd>
      ${economics.delay_if_replace_now_min > 0 ? `<dt>납기</dt><dd style="color:var(--warn)">지금 교체하면 ${economics.delay_if_replace_now_min.toFixed(0)}분 지연</dd>` : ""}
      <dt>재고 / 검사</dt><dd>여분 공구 ${context.tool_stock}개 · 현장 검사 ${context.inspection_available ? "가능" : "불가"}</dd>
    </dl>`);

  $("#agMaster").style.borderColor = decision.action === "CONTINUE" ? "" : css(
    decision.action === "REPLACE_NOW" ? "--danger" : decision.action === "REPLACE_AFTER_JOB" ? "--warn" : "--accent");
  setBody("#agMaster", `
    <div class="action ${decision.action}">${actionLabel(decision)}</div>
    <div class="reason">${decision.reasons[0]}</div>
    <div class="conf">신뢰도 ${fmt(decision.confidence, 2)} · Cycle ${decision.cycle}${rec.kind === "inspection" ? " · 검사 반영 후 재판단" : ""}</div>`);
}

// ---------- 기록 ----------

function addLog(when, text) {
  const li = document.createElement("li");
  li.innerHTML = `<span class="when">${when}</span><span>${text}</span>`;
  $("#log").prepend(li);
}

function logRecord(rec) {
  const d = rec.decision;
  const risk = rec.quality.risk_level;
  if (rec.kind === "inspection") {
    const vals = rec.wear.edges.filter((e) => e.measured).map((e) => `E${e.edge_id} ${fmt(e.vb_max_mm)}`).join(", ");
    addLog(`Cycle ${rec.cycle}`, `검사 결과 ${vals} mm → <strong>${actionLabel(d)}</strong>`);
  } else if (d.action !== "CONTINUE") {
    addLog(`Cycle ${rec.cycle}`, `<strong>${actionLabel(d)}</strong> · ${d.reasons[0]}`);
  } else if (S.lastRisk && risk !== S.lastRisk) {
    addLog(`Cycle ${rec.cycle}`, `품질 위험 ${S.lastRisk} → ${risk}`);
  }
  S.lastRisk = risk;
}

// ---------- 결과 ----------

async function showEnd(rec) {
  $("#truthToggle").checked = true;
  renderWearChart();
  const d = rec.decision;
  const insp = S.records.filter((r) => r.kind === "inspection").length;
  const replaced = d.action.startsWith("REPLACE");
  $("#endSummary").innerHTML = replaced
    ? `Cycle ${rec.cycle}에 <strong>${actionLabel(d)}</strong>. 검사 ${insp}회. 이유: ${d.reasons[0]}`
    : `68 Cycle 끝까지 교체하지 않았습니다. 검사 ${insp}회.`;
  $("#endCard").hidden = false;
  await renderComparison();
  $("#endCard").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function renderComparison() {
  if (!S.sid) return;
  const scale = $("#scale").value;
  const res = await api("GET", `/api/sessions/${S.sid}/comparison?defect_scale=${scale}`).catch(showError);
  if (!res) return;
  const best = Math.min(...res.outcomes.map((o) => o.loss_min_per_rib));
  $("#compTable").innerHTML = `
    <thead><tr><th>판단 방식</th><th class="num">교체 Cycle</th><th class="num">검사</th>
      <th class="num">한계 초과 가공</th><th class="num">윙 리브당 손실</th><th class="num">그중 불량</th><th class="num">윙 리브당 공구</th></tr></thead>
    <tbody>${res.outcomes.map((o, i) => `
      <tr class="${i === 0 ? "system" : ""}">
        <td>${o.name}</td>
        <td class="num">${o.replace_cycle}${o.replaced ? "" : " (교체 안 함)"}</td>
        <td class="num">${o.n_inspections}회</td>
        <td class="num">${o.over_limit_cycles} Cycle</td>
        <td class="num ${o.loss_min_per_rib === best ? "best" : ""}">${o.loss_min_per_rib.toFixed(1)}분</td>
        <td class="num">${o.defect_loss_min_per_rib.toFixed(1)}분</td>
        <td class="num">${o.tools_per_rib.toFixed(2)}개</td>
      </tr>`).join("")}</tbody>`;
}

function showError(e) {
  alert(`오류: ${e.message ?? e}`);
}

init().catch(showError);
