"use strict";

const state = {
  payload: null,
  selectedId: null,
  mode: "static",
  config: null,
};

const LAYER_LABELS = {
  input_separation: "L1 输入",
  tool_whitelist: "L2 工具",
  output_filter: "L3 输出",
  behavior_audit: "L4 行为",
  constitutional: "L5 宪法",
};

const LAYERS = Object.keys(LAYER_LABELS);
const ACTIONS = ["block", "modify", "flag", "allow", "not_exercised"];

const $ = (id) => document.getElementById(id);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function actionClass(action) {
  return `action-${String(action || "not_exercised")}`;
}

function actionText(action) {
  const value = String(action || "not_exercised");
  return value === "not_exercised" ? "—" : value.toUpperCase();
}

function fmt(value) {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function renderSummary(payload) {
  const summary = payload.summary;
  const cards = [
    {
      value: summary.attacks,
      label: "攻击",
      hint: `${summary.layers} 层防御`,
    },
    {
      value: summary.mitigated,
      label: "已削弱/拦截",
      hint: "至少一个 BLOCK 或 MODIFY",
    },
    {
      value: summary.blocked,
      label: "BLOCK",
      hint: "至少一层真正拦截",
    },
    {
      value: summary.flagged_only,
      label: "仅 FLAG",
      hint: "被标记但没被拦住",
    },
    {
      value: `${summary.expected_hit}/${summary.attacks}`,
      label: "expected 层命中",
      hint: summary.expected_miss.length
        ? `miss: ${summary.expected_miss.join(", ")}`
        : "全部命中",
    },
  ];
  const root = $("summary");
  root.replaceChildren();
  for (const card of cards) {
    const node = el("div", "metric-card");
    node.append(el("span", "metric-value", card.value));
    node.append(el("span", "metric-label", card.label));
    node.append(el("span", "metric-hint", card.hint));
    root.append(node);
  }
}

function renderMatrix() {
  const table = $("matrix");
  table.replaceChildren();
  const thead = el("thead");
  const headRow = el("tr");
  headRow.append(el("th", null, "攻击"));
  for (const layer of LAYERS) {
    headRow.append(el("th", null, LAYER_LABELS[layer]));
  }
  thead.append(headRow);
  table.append(thead);

  const tbody = el("tbody");
  for (const item of state.payload.cases) {
    const row = el(
      "tr",
      "matrix-row" + (item.id === state.selectedId ? " is-selected" : "")
    );
    row.addEventListener("click", () => {
      state.selectedId = item.id;
      renderMatrix();
      renderDetail();
    });
    const nameCell = el("td");
    nameCell.append(el("span", "attack-name", item.title));
    nameCell.append(el("span", "attack-id", item.id));
    nameCell.append(el("span", "severity", `${item.category} · ${item.severity}`));
    row.append(nameCell);
    for (const layer of LAYERS) {
      const cell = el("td");
      const action = item.by_layer[layer];
      const badge = el("span", `action ${actionClass(action)}`, actionText(action));
      if (item.expected_layers.includes(layer)) {
        cell.classList.add("cell-expected");
        badge.title = "样本声明的 expected block layer";
      }
      cell.append(badge);
      row.append(cell);
    }
    tbody.append(row);
  }
  table.append(tbody);
}

function selectedCase() {
  if (!state.payload || !state.payload.cases || !state.payload.cases.length) {
    return null;
  }
  return (
    state.payload.cases.find((item) => item.id === state.selectedId) ||
    state.payload.cases[0]
  );
}

function renderExpected(item) {
  const root = $("expected");
  root.replaceChildren();
  root.append(el("h3", null, "expected block layers"));
  const list = el("div", "expected-list");
  for (const layer of item.expected_layers || []) {
    const missed = (item.expected_miss || []).includes(layer);
    const badge = el(
      "span",
      "expected-badge" + (missed ? " miss" : ""),
      `${LAYER_LABELS[layer] || layer}${missed ? " · 未命中" : ""}`
    );
    list.append(badge);
  }
  if (!list.childNodes.length) {
    list.append(el("span", "expected-badge", "样本未声明"));
  }
  root.append(list);
}

function renderActions(item) {
  const root = $("actions");
  root.replaceChildren();
  root.append(el("h3", null, "逐层动作"));
  for (const action of item.actions || []) {
    const card = el("div", "action-card");
    const head = el("div", "action-head");
    head.append(
      el("span", "action-layer", LAYER_LABELS[action.layer] || action.layer)
    );
    head.append(
      el("span", `action ${actionClass(action.action)}`, actionText(action.action))
    );
    card.append(head);
    card.append(el("p", "action-reason", action.reason || "—"));
    if (action.note) card.append(el("p", "action-note", action.note));
    root.append(card);
  }
}

function renderDetail() {
  const item = selectedCase();
  if (!item) return;
  state.selectedId = item.id;
  $("case-title").textContent = item.title;
  $("case-id").textContent = item.id;

  const meta = $("case-meta");
  meta.replaceChildren();
  meta.append(el("span", "chip", item.category));
  meta.append(el("span", "chip", item.severity));
  meta.append(el("span", "chip", `role=${item.attack_role}`));
  meta.append(el("span", "chip", item.sample_id));

  const verdict = $("verdict");
  verdict.replaceChildren();
  verdict.append(
    el("span", `action ${actionClass(item.verdict)}`, actionText(item.verdict))
  );
  verdict.append(el("p", "verdict-meaning", item.meaning || ""));
  if (item.expected_miss && item.expected_miss.length) {
    verdict.append(
      el(
        "p",
        "verdict-meaning",
        `expected 但没命中的层：${item.expected_miss
          .map((layer) => LAYER_LABELS[layer] || layer)
          .join("、")}`
      )
    );
  }

  $("case-payload").textContent = item.payload;
  renderExpected(item);
  renderActions(item);
  $("raw-json").textContent = JSON.stringify(item, null, 2);
}

function renderLayerBars(payload) {
  const root = $("layer-bars");
  root.replaceChildren();
  const total = payload.summary.attacks;
  for (const layer of LAYERS) {
    const counts = payload.summary.layer_counts[layer] || {};
    const row = el("div", "layer-row");
    row.append(el("div", "layer-name", LAYER_LABELS[layer]));
    const bar = el("div", "layer-bar");
    for (const action of ACTIONS) {
      const count = counts[action] || 0;
      if (!count) continue;
      const seg = el("div", `layer-seg seg-${action}`);
      seg.style.width = `${(count / total) * 100}%`;
      seg.title = `${action}: ${count}`;
      bar.append(seg);
    }
    row.append(bar);
    const detail = ACTIONS.map((action) => `${action}=${counts[action] || 0}`).join(" · ");
    row.append(el("div", "layer-counts", detail));
    root.append(row);
  }
}

function renderLayerAblation(payload) {
  const data = payload.layer_ablation;
  const table = $("layer-ablation");
  table.replaceChildren();
  if (!data) {
    $("layer-ablation-note").textContent = "层内 LOO 数据不可用。";
    return;
  }
  const thead = el("thead");
  const headRow = el("tr");
  for (const label of [
    "层", "mitigated", "blocked", "flagged-only", "unmitigated",
    "lost mitigation", "lost flag", "lost expected hit",
  ]) {
    headRow.append(el("th", null, label));
  }
  thead.append(headRow);
  table.append(thead);
  const body = el("tbody");
  for (const row of data.rows || []) {
    const tr = el("tr");
    tr.append(el("td", null, LAYER_LABELS[row.layer] || row.layer));
    for (const key of ["mitigated", "blocked", "flagged_only", "unmitigated"]) {
      tr.append(el("td", null, fmt(row[key])));
    }
    for (const key of ["lost_mitigation", "lost_flag", "lost_expected_hit"]) {
      const cases = row[key] || [];
      tr.append(el("td", null, cases.length ? cases.join(", ") : "—"));
    }
    body.append(tr);
  }
  table.append(body);
  $("layer-ablation-note").textContent = data.note || "";
}

function renderBoundaries(payload) {
  const root = $("boundaries");
  root.replaceChildren();
  for (const boundary of payload.boundaries || []) {
    root.append(el("li", null, boundary));
  }
}

function renderMeta(payload) {
  const meta = payload.meta || {};
  const verification = payload.verification || {};
  const rows = [
    ["仓库", meta.repo],
    ["Demo", meta.demo],
    ["提交", meta.commit],
    ["工作区", meta.worktree_dirty ? "有未提交改动" : "干净（matrix.json 除外）"],
    ["生成时间 (UTC)", meta.generated_at],
    ["模式", meta.mode],
    ["Python", meta.python],
    ["断言", `${verification.status || "—"} (${(verification.checks || []).length} checks)`],
    ["攻击源", payload.sources ? payload.sources.attacks : "—"],
    ["防御源", payload.sources ? payload.sources.defenses : "—"],
  ];
  if (meta.dirty_paths && meta.dirty_paths.length) {
    rows.push(["未提交路径", meta.dirty_paths.join(", ")]);
  }
  const dl = $("meta");
  dl.replaceChildren();
  for (const [key, value] of rows) {
    dl.append(el("dt", null, key));
    dl.append(el("dd", null, value === undefined || value === null ? "—" : value));
  }
}

function renderMode() {
  const badge = $("mode-badge");
  badge.className = "badge " + (state.mode === "live" ? "badge-live" : "badge-static");
  badge.textContent = state.mode === "live" ? "本地实时" : "静态回放";
  $("mode-note").textContent =
    state.mode === "live"
      ? "点击“重跑矩阵”会重新执行全部层内覆盖检查。"
      : "这是提交进仓库的一次确定性构建。运行 python3 demo/server.py 可实时重算。";
  $("rerun").disabled = state.mode !== "live";
}

function renderAll() {
  renderSummary(state.payload);
  renderMatrix();
  renderDetail();
  renderLayerBars(state.payload);
  renderLayerAblation(state.payload);
  renderBoundaries(state.payload);
  renderMeta(state.payload);
  renderMode();
}

async function loadConfig() {
  try {
    const response = await fetch("./config.json", { cache: "no-store" });
    if (response.ok) return await response.json();
  } catch (error) {
    // file:// or a static host without config.json: stay in replay mode.
  }
  return { mode: "static" };
}

async function rerun() {
  const button = $("rerun");
  const status = $("rerun-status");
  button.disabled = true;
  status.textContent = "正在重跑层内覆盖检查…";
  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.payload = payload;
    if (!payload.cases.some((item) => item.id === state.selectedId)) {
      state.selectedId = payload.cases[0] ? payload.cases[0].id : null;
    }
    renderAll();
    status.textContent = `重跑完成 · ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    status.textContent = `重跑失败：${error.message}`;
  } finally {
    button.disabled = state.mode !== "live";
  }
}

async function init() {
  try {
    state.config = await loadConfig();
    state.mode = state.config.mode === "live" ? "live" : "static";
    const response = await fetch("./matrix.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`matrix.json HTTP ${response.status}`);
    state.payload = await response.json();
    state.selectedId = state.payload.cases[0] ? state.payload.cases[0].id : null;
    renderAll();

    $("rerun").addEventListener("click", rerun);
    $("raw-toggle").addEventListener("click", () => {
      const pre = $("raw-json");
      const button = $("raw-toggle");
      const wasHidden = pre.hidden;
      pre.hidden = !wasHidden;
      button.setAttribute("aria-expanded", String(wasHidden));
      button.textContent = wasHidden ? "收起原始 case JSON" : "查看原始 case JSON";
    });
  } catch (error) {
    const box = $("error");
    box.hidden = false;
    box.textContent =
      `加载失败：${error.message}。如果你在用 file:// 打开页面，` +
      "请运行 python3 demo/server.py 或 python3 -m http.server -d demo/public。";
  }
}

document.addEventListener("DOMContentLoaded", init);
