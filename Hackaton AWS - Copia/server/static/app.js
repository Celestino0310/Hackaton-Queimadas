// QueimAlerta - mobile frontend logic
"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

/* ---------------------------------------------------- API base resolution */
const LS_API = "queimalerta_api_base";
function getApiBase() {
  const saved = localStorage.getItem(LS_API);
  if (saved !== null) return saved;
  return (window.QUEIMALERTA_CONFIG && window.QUEIMALERTA_CONFIG.API_BASE) || "";
}
function setApiBase(v) {
  localStorage.setItem(LS_API, v || "");
}
function apiUrl(path) {
  const base = getApiBase().replace(/\/+$/, "");
  return base + path;
}

const api = {
  async get(path) {
    const r = await fetch(apiUrl(path));
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(apiUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || r.statusText);
    return data;
  },
  async del(path) {
    const r = await fetch(apiUrl(path), { method: "DELETE" });
    if (!r.ok) throw new Error(r.statusText);
    return r.json();
  },
};

/* ---------------------------------------------------- Toast */
let toastTimer;
function toast(msg, kind = "") {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast " + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 2600);
}

/* ---------------------------------------------------- Bottom navigation */
$$(".nav-item").forEach((item) => {
  item.addEventListener("click", () => {
    $$(".nav-item").forEach((n) => n.classList.remove("active"));
    $$(".view").forEach((v) => v.classList.remove("active"));
    item.classList.add("active");
    const tab = item.dataset.tab;
    $("#" + tab).classList.add("active");
    $("#appbar-title").textContent = item.dataset.title;
    $(".screen").scrollTop = 0;
    if (tab === "relatos") loadRelatos();
    if (tab === "painel") loadRanking();
  });
});

/* ---------------------------------------------------- Helpers */
function fillSelect(sel, items, { value, label, placeholder }) {
  sel.innerHTML = "";
  if (placeholder) {
    const o = document.createElement("option");
    o.value = "";
    o.textContent = placeholder;
    sel.appendChild(o);
  }
  items.forEach((it) => {
    const o = document.createElement("option");
    o.value = value(it);
    o.textContent = label(it);
    sel.appendChild(o);
  });
}
function fmt(n) { return (n ?? 0).toLocaleString("pt-BR"); }
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------------------------------------------------- Geo base data */
let ESTADOS = [];
let REGIOES = [];

async function loadGeoBase() {
  [REGIOES, ESTADOS] = await Promise.all([
    api.get("/api/regioes"),
    api.get("/api/estados"),
  ]);
  fillSelect($("#f-regiao"), REGIOES, { value: (r) => r.nome, label: (r) => r.nome, placeholder: "Todas" });
  fillSelect($("#f-uf"), ESTADOS, { value: (e) => e.sigla, label: (e) => `${e.nome} (${e.sigla})`, placeholder: "Todos" });
  fillSelect($("#r-uf"), ESTADOS, { value: (e) => e.sigla, label: (e) => `${e.nome} (${e.sigla})`, placeholder: "Selecione…" });
}

async function loadMunicipios(sigla, targetSel) {
  if (!sigla) {
    targetSel.innerHTML = '<option value="">Selecione um estado</option>';
    targetSel.disabled = true;
    return;
  }
  targetSel.disabled = true;
  targetSel.innerHTML = '<option value="">Carregando…</option>';
  try {
    const mun = await api.get(`/api/municipios?uf=${encodeURIComponent(sigla)}`);
    fillSelect(targetSel, mun, { value: (m) => m.nome, label: (m) => m.nome, placeholder: "Todas as cidades" });
    targetSel.disabled = false;
  } catch (e) {
    targetSel.innerHTML = `<option value="">Erro ao carregar</option>`;
  }
}

/* ---------------------------------------------------- Ranking */
async function loadRanking() {
  const nivel = $("#f-nivel").value;
  const regiao = $("#f-regiao").value;
  const uf = $("#f-uf").value;

  const params = new URLSearchParams();
  params.set("nivel", nivel);
  if (regiao) params.set("regiao", regiao);
  if (uf) params.set("uf", uf);

  const box = $("#ranking");
  box.innerHTML = '<p class="muted">Carregando…</p>';
  try {
    const data = await api.get("/api/ocorrencias?" + params.toString());
    renderStats(data);
    renderRanking(data);
  } catch (e) {
    box.innerHTML = `<p class="msg err">Sem conexão com o servidor. Verifique as configurações (⚙).</p>`;
  }
}

function renderStats(data) {
  $("#stat-total").textContent = fmt(data.total_focos);
  $("#stat-relatos").textContent = fmt(data.total_relatos_ativos);
  const top = data.itens[0];
  $("#stat-lider").textContent = top ? (top.regiao_nome || top.uf_nome || top.uf) : "—";
}

function renderRanking(data) {
  const box = $("#ranking");
  const nivel = data.nivel;
  $("#ranking-title").textContent = nivel === "regiao" ? "Ranking por região" : "Ranking por estado";
  if (!data.itens.length) {
    box.innerHTML = '<p class="muted">Nenhuma ocorrência para os filtros selecionados.</p>';
    return;
  }
  const max = Math.max(...data.itens.map((i) => i.focos), 1);
  box.innerHTML = "";
  data.itens.forEach((it, idx) => {
    const name = nivel === "regiao" ? it.regiao_nome : it.uf_nome;
    const sub = nivel === "regiao" ? "Região" : `${it.uf} · ${it.regiao_nome}`;
    const pct = Math.round((it.focos / max) * 100);
    const row = document.createElement("div");
    row.className = "rank-row";
    row.innerHTML = `
      <div class="rank-pos">${idx + 1}</div>
      <div class="rank-name">${escapeHtml(name)}<small>${escapeHtml(sub)}</small></div>
      <div class="rank-num">
        <b>${fmt(it.focos)}</b>
        ${it.relatos_ativos ? `<span class="relatos">${it.relatos_ativos} relato(s)</span>` : ""}
      </div>
      <div class="rank-mid"><div class="bar-wrap"><div class="bar" style="width:${pct}%"></div></div></div>`;
    box.appendChild(row);
  });
}

/* ---------------------------------------------------- Relatos */
async function loadRelatos() {
  const box = $("#relatos-list");
  box.innerHTML = '<p class="muted">Carregando…</p>';
  try {
    const reports = await api.get("/api/reports");
    if (!reports.length) {
      box.innerHTML = '<p class="muted">Nenhum relato ativo no momento.</p>';
      return;
    }
    box.innerHTML = "";
    reports.forEach((r) => {
      const d = new Date(r.criado_em);
      const quando = isNaN(d) ? r.criado_em : d.toLocaleString("pt-BR");
      const el = document.createElement("div");
      el.className = "relato " + r.intensidade;
      el.innerHTML = `
        <div>
          <h3>${escapeHtml(r.municipio)} — ${escapeHtml(r.uf)}
            <span class="badge ${r.intensidade}">${r.intensidade}</span></h3>
          <div class="meta">🕒 ${quando}${r.lat && r.lon ? ` · 📍 ${Number(r.lat).toFixed(3)}, ${Number(r.lon).toFixed(3)}` : ""}</div>
          ${r.descricao ? `<p class="desc">${escapeHtml(r.descricao)}</p>` : ""}
        </div>
        <button class="btn-del" data-id="${r.id}" title="Resolver">✕</button>`;
      box.appendChild(el);
    });
    $$(".btn-del").forEach((b) =>
      b.addEventListener("click", async () => {
        try {
          await api.del(`/api/reports/${b.dataset.id}`);
          toast("Relato resolvido", "ok");
          loadRelatos();
          loadRanking();
        } catch (e) { toast("Erro ao resolver", "err"); }
      }));
  } catch (e) {
    box.innerHTML = `<p class="msg err">Sem conexão com o servidor. Verifique as configurações (⚙).</p>`;
  }
}

/* ---------------------------------------------------- Report form */
let lastGeo = { lat: null, lon: null };

$("#btn-geo").addEventListener("click", () => {
  const status = $("#geo-status");
  if (!navigator.geolocation) { status.textContent = "Geolocalização não suportada."; return; }
  status.textContent = "Obtendo localização…";
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      lastGeo = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      status.textContent = `📍 ${lastGeo.lat.toFixed(4)}, ${lastGeo.lon.toFixed(4)}`;
    },
    () => (status.textContent = "Não foi possível obter a localização.")
  );
});

$("#form-report").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const msg = $("#report-msg");
  msg.textContent = ""; msg.className = "msg";

  const body = {
    uf: $("#r-uf").value,
    municipio: $("#r-municipio").value,
    intensidade: $("#r-intensidade").value,
    descricao: $("#r-descricao").value,
    lat: lastGeo.lat, lon: lastGeo.lon,
  };
  if (!body.uf || !body.municipio) {
    msg.textContent = "Selecione o estado e a cidade."; msg.classList.add("err"); return;
  }
  try {
    await api.post("/api/reports", body);
    msg.textContent = "✅ Relato enviado. Obrigado!"; msg.classList.add("ok");
    toast("Relato enviado 🔥", "ok");
    $("#r-descricao").value = "";
    lastGeo = { lat: null, lon: null };
    $("#geo-status").textContent = "";
    loadRanking();
  } catch (e) {
    msg.textContent = "Erro ao enviar: " + e.message; msg.classList.add("err");
  }
});

/* ---------------------------------------------------- Filters wiring */
$("#f-uf").addEventListener("change", (e) => loadMunicipios(e.target.value, $("#f-municipio")));
$("#r-uf").addEventListener("change", (e) => loadMunicipios(e.target.value, $("#r-municipio")));
$("#btn-aplicar").addEventListener("click", loadRanking);
$("#btn-limpar").addEventListener("click", () => {
  $("#f-nivel").value = "uf";
  $("#f-regiao").value = "";
  $("#f-uf").value = "";
  $("#f-municipio").innerHTML = '<option value="">Selecione um estado</option>';
  $("#f-municipio").disabled = true;
  loadRanking();
});

$("#toggle-filters").addEventListener("click", () => {
  const head = $("#toggle-filters");
  const body = $("#filters-body");
  const open = head.getAttribute("aria-expanded") === "true";
  head.setAttribute("aria-expanded", String(!open));
  body.classList.toggle("collapsed", open);
});

/* ---------------------------------------------------- Refresh */
$("#btn-refresh").addEventListener("click", () => {
  const active = $(".nav-item.active").dataset.tab;
  if (active === "relatos") loadRelatos(); else loadRanking();
  toast("Atualizado");
});

/* ---------------------------------------------------- Settings sheet */
function openSheet() {
  $("#cfg-api").value = localStorage.getItem(LS_API) ?? ((window.QUEIMALERTA_CONFIG || {}).API_BASE || "");
  $("#conn-status").textContent = "";
  $("#settings-backdrop").classList.remove("hidden");
  $("#settings-sheet").classList.remove("hidden");
}
function closeSheet() {
  $("#settings-backdrop").classList.add("hidden");
  $("#settings-sheet").classList.add("hidden");
}
$("#btn-settings").addEventListener("click", openSheet);
$("#cfg-close").addEventListener("click", closeSheet);
$("#settings-backdrop").addEventListener("click", closeSheet);

$("#cfg-test").addEventListener("click", async () => {
  const val = $("#cfg-api").value.trim().replace(/\/+$/, "");
  const status = $("#conn-status");
  status.textContent = "Testando…";
  try {
    const r = await fetch((val || "") + "/health");
    const j = await r.json();
    status.textContent = r.ok ? `✅ Conectado (${j.status})` : `⚠ Resposta ${r.status}`;
    status.style.color = r.ok ? "var(--ok)" : "var(--danger)";
  } catch (e) {
    status.textContent = "❌ Não foi possível conectar.";
    status.style.color = "var(--danger)";
  }
});

$("#cfg-save").addEventListener("click", async () => {
  const val = $("#cfg-api").value.trim();
  setApiBase(val);
  closeSheet();
  toast("Configuração salva", "ok");
  try {
    await loadGeoBase();
    await loadRanking();
  } catch (e) { toast("Servidor inacessível", "err"); }
});

/* ---------------------------------------------------- Init */
(async function init() {
  // register service worker (PWA)
  if ("serviceWorker" in navigator) {
    try { await navigator.serviceWorker.register("sw.js"); } catch (e) { /* ignore */ }
  }
  try {
    await loadGeoBase();
    await loadRanking();
  } catch (e) {
    $("#ranking").innerHTML =
      `<p class="msg err">Não foi possível conectar ao servidor.<br>Abra as configurações (⚙) e informe o endereço da API.</p>`;
  }
})();
