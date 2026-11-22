const $ = (selector) => document.querySelector(selector);
const state = { presets: [], schema: null, lastResult: null };
const format = (value) => Number(value || 0).toLocaleString();
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
async function api(path, options={}) {
  const response = await fetch(path, {headers:{"Content-Type":"application/json"}, ...options});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "The API request failed.");
  return data;
}
function renderPresets() {
  $("#presetList").innerHTML = state.presets.map(p => `<button class="preset" data-preset="${escapeHtml(p.id)}"><strong>${escapeHtml(p.name)}</strong><small>${escapeHtml(p.description)}</small><span class="severity ${escapeHtml(p.severity)}">${escapeHtml(p.severity.toUpperCase())} BOTTLENECK</span></button>`).join("");
  document.querySelectorAll("[data-preset]").forEach(button => button.addEventListener("click", () => {
    const preset = state.presets.find(p => p.id === button.dataset.preset);
    $("#sqlEditor").value = preset.sql;
    document.querySelectorAll(".preset").forEach(el => el.classList.toggle("active", el === button));
  }));
}
function renderSchema() {
  $("#schemaGrid").innerHTML = state.schema.tables.map(table => `<article class="schema-card"><h3>${escapeHtml(table.name)}</h3><div class="count">${format(table.rowCount)} <span class="muted">rows</span></div><details><summary>${table.columns.length} columns · ${table.indexes.length} indexes</summary><ul>${table.columns.map(c => `<li>${escapeHtml(c.name)} <span>· ${escapeHtml(c.type)}</span>${c.pk ? " · PRIMARY KEY" : ""}</li>`).join("")}</ul></details></article>`).join("");
  $("#rowCount").textContent = format(state.schema.seededRows);
  $("#indexCount").textContent = state.schema.activeIndexCount;
  $("#engineStatus").textContent = "QueryLens SQLite Engine: Active";
}
function renderMetrics(result) {
  const before = result.before, after = result.after;
  const speed = result.speedup;
  const metrics = [
    ["BASELINE LATENCY", before.executionMs.toFixed(3)+" ms", before.scanNodes+" scan node(s)", "bad"],
    ["ROWS RETURNED", format(before.rowsReturned), before.truncated ? "Preview capped at 500 rows" : "Complete result set", ""],
    ["INDEXED LOOKUPS", format(before.indexedSearchNodes), "In baseline plan", "good"],
    ["INDEX SPEEDUP", after ? speed+"×" : "—", after ? after.executionMs.toFixed(3)+" ms after index" : "Enable comparison to test", after && speed>1 ? "good" : "warn"]
  ];
  $("#metrics").innerHTML = metrics.map(m => `<div class="metric ${m[3]}"><span>${m[0]}</span><strong>${m[1]}</strong><small>${m[2]}</small></div>`).join("");
}
function renderPlan(plan) {
  $("#planTree").innerHTML = plan.map(node => `<div class="plan-node ${node.kind}"><span class="node-id">#${node.id}</span><div style="min-width:0;flex:1"><div class="node-detail">${escapeHtml(node.detail)}</div><div class="node-explain">${escapeHtml(node.explanation)}</div></div><span class="plan-badge ${node.kind}">${node.kind.toUpperCase()}</span></div>`).join("") || '<p class="muted">No plan nodes returned.</p>';
}
function renderAdvice(advice) {
  $("#adviceList").innerHTML = advice.length ? advice.map((item,i) => `<div class="advice"><p>${escapeHtml(item.reason)} <span class="muted">· ${escapeHtml(item.table)}</span></p><code id="ddl-${i}">${escapeHtml(item.sql)}</code><button class="btn ghost copy-btn" data-copy="${i}">Copy index SQL</button></div>`).join("") : '<p class="muted">No obvious index candidate found. Inspect the query plan and schema before adding indexes.</p>';
  document.querySelectorAll("[data-copy]").forEach(button => button.addEventListener("click", async () => {
    await navigator.clipboard.writeText(advice[Number(button.dataset.copy)].sql);
    button.textContent = "Copied";
  }));
}
function renderRows(rows) {
  if (!rows.length) { $("#sampleTable").innerHTML = ""; $("#sampleMeta").textContent = "No rows"; return; }
  const columns = Object.keys(rows[0]);
  $("#sampleTable").innerHTML = `<thead><tr>${columns.map(c=>`<th>${escapeHtml(c)}</th>`).join("")}</tr></thead><tbody>${rows.map(row=>`<tr>${columns.map(c=>`<td>${escapeHtml(row[c])}</td>`).join("")}</tr>`).join("")}</tbody>`;
  $("#sampleMeta").textContent = `Showing ${rows.length} sample row(s)`;
}
function renderResult(data) {
  state.lastResult = data;
  $("#results").classList.remove("hidden");
  renderMetrics(data); renderPlan(data.before.plan); renderAdvice(data.recommendations); renderRows(data.before.sampleRows);
  $("#indexCount").textContent = data.indexes.length;
}
async function runQuery() {
  const button=$("#runBtn"), error=$("#errorBox");
  error.classList.add("hidden"); button.disabled=true; button.textContent="Analyzing…";
  try {
    const data=await api("/api/explain",{method:"POST",body:JSON.stringify({sql:$("#sqlEditor").value,applySuggestedIndexes:$("#compareToggle").checked})});
    renderResult(data);
  } catch (err) { error.textContent=err.message; error.classList.remove("hidden"); }
  finally { button.disabled=false; button.innerHTML="<span>▶</span> Run EXPLAIN & Benchmark"; }
}
async function init() {
  try {
    state.schema=await api("/api/schema"); state.presets=state.schema.presets;
    renderPresets(); renderSchema();
  } catch (err) {
    $("#engineStatus").textContent="Offline · API unavailable";
    $("#presetList").innerHTML='<div class="muted">Start the Python API to load live presets.</div>';
    $("#schemaGrid").innerHTML='<div class="muted">Schema explorer requires the backend. This UI can still show a local SQL safety explainer.</div>';
    $("#errorBox").textContent="Backend unavailable. QueryLens requires its Python serverless API for real SQLite query plans; no fake benchmark results are shown. Deploy on Vercel or run a compatible local server.";
    $("#errorBox").classList.remove("hidden");
  }
}
$("#runBtn").addEventListener("click",runQuery);
$("#resetBtn").addEventListener("click",()=>{ $("#indexCount").textContent="0"; $("#errorBox").textContent="Indexes are created only inside each isolated in-memory benchmark request. A new run starts from a clean database."; $("#errorBox").classList.remove("hidden"); });
$("#sqlEditor").addEventListener("keydown",e=>{if((e.ctrlKey||e.metaKey)&&e.key==="Enter"){e.preventDefault();runQuery();}});
init();
