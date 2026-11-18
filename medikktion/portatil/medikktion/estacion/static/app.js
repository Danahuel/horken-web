// Medikktion · estación de lectura. Sin librerías: el portátil puede no tener internet.
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// 9876.5 → "9.876,5"
function num(v, d = 1) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return Number(v).toLocaleString("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: "always" });
}
const eur = (a, b) => `${num(a, 0)} – ${num(b, 0)} €`;

// Unidades de taller y rangos (los mismos que la app del móvil).
// [etiqueta, unidad, factor, decimales, mín, máx, normal desde, normal hasta, ¿lo bajo es alarma?]
const MEASURES = {
  rpm: ["Régimen motor", "rpm", 1, 0, 0, 2500, 650, 2250],
  oil_pressure_kpa: ["Presión de aceite", "bar", 0.01, 2, 0, 7, 2.5, 6.5],
  coolant_c: ["Refrigerante", "°C", 1, 2, 20, 120, 70, 100, false],
  oil_temp_c: ["Aceite motor", "°C", 1, 2, 20, 130, 60, 115, false],
  hyd_oil_temp_c: ["Aceite hidráulico", "°C", 1, 2, 10, 110, 30, 85, false],
  trans_oil_temp_c: ["Aceite transmisión", "°C", 1, 2, 10, 130, 40, 105, false],
  boost_kpa: ["Sobrealimentación", "bar", 0.01, 2, 0, 3, null, null],
  fuel_rate_lh: ["Consumo", "L/h", 1, 1, 0, 70, null, null],
  battery_v: ["Tensión batería", "V", 1, 2, 18, 32, 24.5, 29.5],
  fuel_level_pct: ["Combustible", "%", 1, 1, 0, 100, 12, null],
  def_level_pct: ["AdBlue", "%", 1, 1, 0, 100, 12, null],
  torque_pct: ["Par motor", "%", 1, 0, 0, 100, null, null],
};

const KIND = { active: "activa", emissions: "activa · emisiones", pending: "pendiente", permanent: "permanente",
  emissions_prev: "emisiones anterior", history: "histórica" };
let S = null;               // último estado del servidor
let mode = "maquina";
let firstLoad = true;
const shown = {};           // valores mostrados (para que se deslicen, no salten)
const target = {};

// ─────────────────────────────────────────── comunicación
async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  return r.json();
}

async function poll() {
  try {
    S = await api("/api/estado");
    render();
  } catch (e) {
    $("#status-line").textContent = "Sin respuesta del programa. ¿Se ha cerrado?";
  }
  setTimeout(poll, 1000);
}

// ─────────────────────────────────────────── formulario
function fillSelects() {
  const lec = $("#f-lector");
  lec.innerHTML = S.adapters.flatMap((a) => (a.devices.length ? a.devices : [{ id: 1, description: "" }]).map((d) =>
    `<option value="${esc(a.api)}" data-dev="${d.id}">${esc(a.vendor)}${d.description ? " · " + esc(d.description) : ""}</option>`)).join("");
  $("#no-lector").hidden = S.adapters.length > 0;
  $("#f-clase").innerHTML = Object.entries(S.classes).map(([k, v]) =>
    `<option value="${k}"${k === "generica" ? " selected" : ""}>${esc(v)}</option>`).join("");
  $("#f-escenario").innerHTML = Object.entries(S.scenarios).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  fillRecordings();
  if (!S.adapters.length && firstLoad) setMode("demo");
}

function fillRecordings() {
  const sel = $("#f-archivo");
  const cur = sel.value;
  sel.innerHTML = S.recordings.map((r) => `<option value="${esc(r.name)}">${esc(r.name)} · ${num(r.mb, 1)} MB</option>`).join("");
  if (cur) sel.value = cur;
  $("#no-rec").hidden = S.recordings.length > 0;
}

function setMode(m) {
  mode = m;
  $$("#modes button").forEach((b) => b.classList.toggle("on", b.dataset.mode === m));
  $$("fieldset[data-for]").forEach((f) => (f.hidden = !f.dataset.for.split(" ").includes(m)));
  $$("[data-hide]").forEach((el) => (el.hidden = el.dataset.hide.split(" ").includes(m)));
}

function segValue(name) {
  const b = $(`.seg[data-name="${name}"] button.on`);
  return b ? b.dataset.v : null;
}

function formData() {
  const f = $("#form");
  const opt = $("#f-lector").selectedOptions[0];
  return {
    modo: mode,
    lector: f.lector.value, dispositivo: opt ? opt.dataset.dev : 1,
    protocolo: segValue("protocolo"), sin_uds: segValue("uds") === "0",
    puerto: f.puerto.value.trim(),
    marca: f.marca.value.trim(), modelo: f.modelo.value.trim(), serie_placa: f.serie_placa.value.trim(),
    anio: parseInt(f.anio.value) || null, horas_cuadro: parseFloat(f.horas_cuadro.value.replace(",", ".")) || null,
    km_cuadro: parseFloat(f.km_cuadro.value.replace(",", ".")) || null,
    km_viaje: parseFloat(f.km_viaje.value.replace(",", ".")) || 0,
    precio: parseFloat(f.precio.value.replace(/\./g, "").replace(",", ".")) || null,
    escenario: f.escenario.value, archivo: f.archivo.value, velocidad: segValue("velocidad"),
    clase: f.clase.value, ubicacion: f.ubicacion.value.trim(),
    grabar: $("#f-grabar").getAttribute("aria-pressed") === "true",
  };
}

async function go() {
  if (S && S.running) {
    $("#go").disabled = true;
    await api("/api/parar", {});
    return;
  }
  const d = formData();
  if (d.modo === "maquina" && !d.lector) return note("Elija un lector.");
  if (d.modo === "reproducir" && !d.archivo) return note("No hay grabaciones para reproducir.");
  $("#go").disabled = true;
  const r = await api("/api/iniciar", d);
  if (!r.ok) note(r.error);
}

function note(t) {
  $("#status-line").textContent = t;
}

// ─────────────────────────────────────────── pintar
function render() {
  if (firstLoad) {
    fillSelects();
    firstLoad = false;
  } else if (!S.running) {
    fillRecordings();
  }
  $("#operator").textContent = S.operator ? `Puesto de ${S.operator}` : "";
  const t = new Date();
  $("#clock").textContent = t.toLocaleTimeString("es-ES");

  // Lámparas
  const snap = S.snapshot;
  const frames = snap ? snap.summary.frames : 0;
  lamp("#l-lector", S.running ? "on" : (S.adapters.length ? "" : ""));
  lamp("#l-bus", S.running && frames > 0 ? "ok" : (S.running ? "warn" : ""));
  const c = S.connection;
  lamp("#l-nube", !S.firebase ? "" : (S.running ? (c && c.online ? "ok" : "warn") : "ok"));
  lamp("#l-rec", snap && snap.recording && snap.recording.active ? "rec" : "");

  // Botón
  const g = $("#go");
  g.disabled = false;
  g.classList.toggle("stop", S.running);
  g.querySelector("span").textContent = S.running ? "Parar lectura" : "Empezar lectura";
  $("#form").querySelectorAll("input, select, button").forEach((el) => (el.disabled = S.running));
  $$("#modes button").forEach((b) => (b.disabled = S.running));

  // Sistema
  const d = S.disk;
  $("#sys").innerHTML = `
    <dt>Nube (Firebase)</dt><dd class="${S.firebase ? "yes" : "no"}">${S.firebase ? "configurada" : "sin configurar"}</dd>
    <dt>Correo (Gmail)</dt><dd class="${S.gmail ? "yes" : "no"}">${S.gmail ? "configurado" : "sin configurar"}</dd>
    <dt>Pendientes de subir</dt><dd class="${d.pending ? "no" : ""}">${d.pending}</dd>
    <dt>Espacio usado</dt><dd>${num(d.mb, 1)} MB</dd>`;

  // Registro
  $("#status-line").textContent = S.running ? S.status_line : (S.error ? "ERROR: " + S.error : "");
  const log = $("#log");
  const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 4;
  log.innerHTML = S.log.map((l) => `<li class="${/ERROR|No se pudo/.test(l.text) ? "err" : ""}"><span>${l.t}</span>${esc(l.text)}</li>`).join("");
  if (atBottom) log.scrollTop = log.scrollHeight;

  S.running && snap ? renderReading(snap) : renderIdle();
}

function lamp(sel, cls) {
  const el = $(sel);
  el.className = "lamp" + (cls ? " " + cls : "");
}

function verdictTag(v) {
  return { ok: ["Íntegro", "t-ok"], sospechoso: ["Dudoso", "t-warn"], manipulado: ["Alterado", "t-bad"] }[v] || ["Sin datos", "t-dim"];
}
const healthCls = (h) => (h == null ? "t-dim" : h >= 85 ? "t-ok" : h >= 40 ? "t-warn" : "t-bad");

function renderIdle() {
  const main = $("#main");
  if (main.dataset.view === "idle" && main.dataset.sig === sig()) return;
  main.dataset.view = "idle";
  main.dataset.sig = sig();
  const last = S.last;
  const book = S.logbook;
  main.innerHTML = `
    <div class="idle-head">
      <div><p>${new Date().toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" })}</p>
        <h1>Libro de lecturas</h1></div>
      <p>${book.length ? `${book.length} lecturas guardadas en este portátil` : ""}</p>
    </div>
    ${last ? `<div class="banner"><b>ÚLTIMA LECTURA</b><span>${esc(last.machine.brand_name?.split(" (")[0] || "")} ${esc(last.machine.model || "")}
       · ${last.summary.active_dtcs} averías activas · índice ${last.health?.score ?? "—"} · ${esc(last.tamper.label || "")}</span></div>` : ""}
    ${book.length ? `
    <table class="book">
      <thead><tr><th>Fecha</th><th>Máquina</th><th>Nº de serie</th><th>Lugar</th><th>Averías</th><th>Índice</th><th>Horómetro</th><th></th></tr></thead>
      <tbody>${book.map((r) => {
        const [vt, vc] = verdictTag(r.tamper);
        return `<tr>
          <td class="num">${esc(r.when)}</td>
          <td class="m"><b>${esc(r.brand)} ${esc(r.model)}</b><span>${r.simulated ? "prueba" : ""}</span></td>
          <td class="num">${esc(r.serial)}</td>
          <td>${esc(r.location)}</td>
          <td class="num ${r.active ? "t-warn" : "t-ok"}">${r.active}</td>
          <td class="num ${healthCls(r.health)}">${r.health ?? "—"}</td>
          <td><span class="tag ${vc}">${vt}</span></td>
          <td>${r.pdf ? `<a data-pdf="${esc(r.id)}.pdf">Informe PDF</a>` : ""}</td></tr>`;
      }).join("")}</tbody>
    </table>` : `<p class="empty">Todavía no hay lecturas en este portátil. Conecte el lector a la máquina, elija el lector y pulse
      <b>Empezar lectura</b>. Para ver cómo funciona sin máquina, use el modo <b>Prueba</b>.</p>`}`;
  $$("[data-pdf]", main).forEach((a) => (a.onclick = () => api("/api/abrir", { que: "pdf", nombre: a.dataset.pdf })));
}

function sig() {
  return JSON.stringify([S.logbook.map((r) => r.id), S.last && S.last.session_id]);
}

function renderReading(s) {
  const main = $("#main");
  if (main.dataset.view !== "reading" || main.dataset.sid !== s.session_id) {
    main.dataset.view = "reading";
    main.dataset.sid = s.session_id;
    main.innerHTML = readingSkeleton(s);
    $("#rec-sw").onclick = () => {
      const on = $("#rec-sw").getAttribute("aria-pressed") !== "true";
      api("/api/grabar", { activo: on });
    };
    $("#mail-go").onclick = async () => {
      const to = $("#mail-to").value.split(/[,; ]+/).filter((x) => x.includes("@"));
      if (!to.length) return note("Escriba al menos un correo.");
      await api("/api/informe", { destinatarios: to, idioma: $("#mail-lang").value });
      note("Preparando el informe…");
    };
  }
  const m = s.machine;
  $("#m-brand").textContent = (m.brand_name || "").split(" (")[0] || "Máquina";
  $("#m-model").textContent = m.model || "sin identificar";
  $("#m-meta").innerHTML = `${esc(m.machine_class_label || "")} · nº <span class="mono-num">${esc(m.serial || "—")}</span>
    ${s.protocols.length ? " · " + esc(s.protocols.join(" + ")) : ""}`;
  const secs = Math.floor((Date.now() / 1000) - S.started);
  const online = !S.connection || S.connection.online;
  const r = $("#m-reading");
  r.classList.toggle("off", !online);
  r.lastElementChild.textContent = `${online ? "LEYENDO" : "SIN CONEXIÓN · GUARDANDO EN EL PORTÁTIL"} · ${hms(secs)}`;
  const h = s.health || {};
  $("#m-index").className = "v " + healthCls(h.score);
  $("#m-index").textContent = h.score ?? "—";
  $("#m-index-l").className = "l " + healthCls(h.score);
  $("#m-index-l").textContent = (h.label || "").toUpperCase();

  const [vt, vc] = verdictTag(s.tamper.verdict);
  $("#counters").innerHTML = `
    <div><span>TRAMAS</span><b class="mono-num">${num(s.summary.frames, 0)}</b></div>
    <div><span>CENTRALITAS</span><b>${s.summary.ecus}</b></div>
    <div><span>ACTIVAS</span><b class="${s.summary.active_dtcs ? "t-warn" : "t-ok"}">${s.summary.active_dtcs}</b></div>
    <div><span>HISTÓRICAS</span><b>${s.summary.history_dtcs}</b></div>
    <div><span>HORÓMETRO</span><b>${num(s.tamper.reported_hours, 0)}<small style="font-size:13px;color:var(--text3)"> h</small></b>
      <span class="tag ${vc}" style="margin:4px 0 0">${vt}${s.tamper.estimated_real_hours ? " · real ≈ " + num(s.tamper.estimated_real_hours, 0) + " h" : ""}</span></div>`;

  // Valores en vivo (las filas se crean una vez; los números se deslizan)
  const box = $("#live");
  for (const [k, p] of Object.entries(s.live)) {
    const M = MEASURES[k];
    if (!M) continue;
    let row = box.querySelector(`[data-k="${k}"]`);
    if (!row) {
      row = document.createElement("div");
      row.className = "live-row";
      row.dataset.k = k;
      const lo = M[6] != null ? pct(M, M[6]) : null, hi = M[7] != null ? pct(M, M[7]) : null;
      row.innerHTML = `<span class="lbl">${M[0]}</span><span class="val"><em></em><small>${M[1]}</small></span>
        <div class="bar"><i></i>${lo != null ? `<s style="left:${lo}%"></s>` : ""}${hi != null ? `<s style="left:${hi}%"></s>` : ""}</div>`;
      box.appendChild(row);
      shown[k] = p.value * M[2];
    }
    target[k] = p.value * M[2];
  }

  const u = s.usage || {};
  const idBy = m.identified_by === "placa" ? "por la placa" : m.identified_by === "centralita" ? "por la centralita" : "sin identificar";
  $("#usage").innerHTML = `
    <div><span>VIN</span><b>${esc(m.vin || "—")}</b></div>
    <div><span>IDENTIFICADA</span><b>${idBy}</b></div>
    <div><span>RALENTÍ</span><b>${u.idle_pct != null ? num(u.idle_pct, 0) + " % de su vida" : "—"}</b></div>
    <div><span>CONSUMO MEDIO</span><b>${u.fuel_per_hour != null ? num(u.fuel_per_hour, 1) + " L/h" : "—"}${u.hours_per_year ? " · " + num(u.hours_per_year, 0) + " h/año" : ""}</b></div>
    <div><span>ÚLTIMO BORRADO</span><b>${u.cleared_min != null ? "hace " + num(u.cleared_min / 60, u.cleared_min < 600 ? 1 : 0) + " h" : "—"}</b></div>`;
  $("#evid").innerHTML = [...(s.tamper.evidence || []), ...(s.mods || [])].map((e) => `
    <div class="evid-row"><i style="background:${e.level === "ok" ? "var(--green)" : e.level === "alta" ? "var(--red)" : "var(--amber)"}"></i>
      <div><b>${esc(e.title)}</b><p>${esc(e.detail)}</p></div></div>`).join("");

  const b = s.purchase || {};
  if (b.verdict) {
    const col = { comprar: "var(--green)", negociar: "var(--amber)", no_comprar: "var(--red)" }[b.verdict];
    $("#buy").innerHTML = `
      <div class="buy-v" style="color:${col}">${esc(b.label)}</div>
      <div><span>DEJARLA A PUNTO</span><b>${eur(b.ready_min_eur, b.ready_max_eur)}</b></div>
      <div><span>HORAS OCULTAS</span><b>${b.hidden_hours ? num(b.hidden_hours, 0) + " h · " + num(b.hidden_hours_value_eur, 0) + " €" : "ninguna"}</b></div>
      <div><span>REBAJA RECOMENDADA</span><b style="color:var(--yellow)">${num(b.recommended_discount_eur, 0)} €</b></div>
      <div><span>${b.asking_price_eur ? "OFERTA MÁXIMA" : "TARIFA"}</span><b>${b.asking_price_eur ? num(b.max_offer_eur, 0) + " €"
        : num(s.pricing?.rate, 0) + " €/h · " + esc(s.pricing?.country_name || "")}</b></div>`;
  }

  const faults = s.dtcs;
  $("#faults").innerHTML = faults.length ? faults.map((d) => `
    <div class="fault ${d.active || d.kind === "permanent" || d.kind === "pending" ? "" : "hist"}">
      <div class="s" style="background:${sevColor(d.severity, d.active)}"></div>
      <div><div class="c">${esc(d.code)} · ${KIND[d.kind] || (d.active ? "activa" : "histórica")} · ${esc(d.source_name)}</div>
        <div class="n">${esc(d.name)}</div><div class="f">${esc(d.fmi_text)}</div></div>
      <div class="e">alt. ${num(d.cost_min_eur, 0)} €<br>orig. ${num(d.cost_max_eur, 0)} €<br><span style="color:var(--text3)">dif. ${d.difficulty}/5</span></div>
    </div>`).join("") : `<p class="empty" style="padding:10px 0">Sin averías.</p>`;

  $("#ecus").innerHTML = s.ecus.map((e) => `<div class="ecu"><span class="a">${esc(e.address_hex)}</span>
    <span>${esc(e.name)}</span><span class="h">${e.engine_hours != null ? num(e.engine_hours) + " h" : ""}</span></div>`).join("");

  const rec = s.recording || {};
  $("#rec-sw").setAttribute("aria-pressed", rec.active ? "true" : "false");
  $("#rec-d").textContent = rec.active ? `${rec.file} · ${num(rec.frames, 0)} tramas · ${num(rec.mb, 2)} MB`
    : (rec.file ? `Última: ${rec.file}` : "Guarda todo lo que circula por el bus (BLF)");
  const mt = $("#mail-to");
  if (!mt.value && S.recipients.length && document.activeElement !== mt) mt.value = S.recipients.join(", ");
}

function readingSkeleton() {
  return `
    <div class="mhead">
      <div>
        <div class="b" id="m-brand"></div>
        <h1 id="m-model"></h1>
        <div class="meta" id="m-meta"></div>
        <div class="reading" id="m-reading"><i></i><span></span></div>
      </div>
      <div class="index"><div class="k">ÍNDICE DE ESTADO</div><div class="v" id="m-index">—</div><div class="l" id="m-index-l"></div></div>
    </div>
    <div class="counters" id="counters"></div>
    <div class="usage" id="usage"></div>
    <div class="buy" id="buy"></div>
    <div class="cols">
      <div><div class="sec-title">VALORES EN VIVO</div><div id="live"></div>
        <div class="sec-title" style="margin-top:22px">CENTRALITAS</div><div id="ecus"></div></div>
      <div><div class="sec-title">AVERÍAS</div><div id="faults"></div>
        <div class="sec-title evid">HORÓMETRO Y PROCEDENCIA</div><div id="evid"></div></div>
    </div>
    <div class="actions">
      <div class="act-rec"><div><div class="t">Grabación de tramas</div><div class="d" id="rec-d"></div></div>
        <button type="button" class="sw" id="rec-sw" aria-pressed="false"><i></i></button></div>
      <div><div class="act-mail"><input id="mail-to" placeholder="correo@ejemplo.com, otro@ejemplo.com">
        <select id="mail-lang" style="width:86px"><option value="es">ES</option><option value="de">DE</option></select>
        <button id="mail-go">Enviar informe</button></div></div>
    </div>`;
}

const pct = (M, v) => Math.max(0, Math.min(100, ((v - M[4]) / (M[5] - M[4])) * 100));
const sevColor = (s, active) => (!active ? "var(--line2)" : s >= 5 ? "var(--red)" : s === 4 ? "#e07a3e" : s === 3 ? "var(--amber)" : "var(--text3)");
const hms = (s) => [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60].map((x) => String(x).padStart(2, "0")).join(":");

// Animación: cada valor recorre el camino hasta la nueva lectura (como una aguja)
function tick() {
  for (const k of Object.keys(target)) {
    const M = MEASURES[k];
    const row = document.querySelector(`.live-row[data-k="${k}"]`);
    if (!M || !row) continue;
    shown[k] += (target[k] - shown[k]) * 0.08;
    const v = shown[k];
    row.querySelector("em").textContent = num(v, M[3]);
    row.querySelector(".bar i").style.width = pct(M, v) + "%";
    row.classList.toggle("alert", (M[6] != null && M[8] !== false && v < M[6]) || (M[7] != null && v > M[7]));
  }
  requestAnimationFrame(tick);
}

// ─────────────────────────────────────────── eventos
$$("#modes button").forEach((b) => (b.onclick = () => setMode(b.dataset.mode)));
$$(".seg").forEach((seg) => seg.querySelectorAll("button").forEach((b) => (b.onclick = () => {
  seg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
})));
$("#f-grabar").onclick = (e) => {
  const el = e.currentTarget;
  el.setAttribute("aria-pressed", el.getAttribute("aria-pressed") === "true" ? "false" : "true");
};
$("#go").onclick = go;
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !["INPUT", "SELECT"].includes(document.activeElement.tagName)) go();
});
$("#btn-check").onclick = async () => {
  const box = $("#check");
  box.hidden = false;
  box.textContent = "Comprobando…";
  const r = await api("/api/comprobar", {});
  box.textContent = r.lines ? r.lines.join("\n") : r.error;
};
$("#btn-folder").onclick = () => api("/api/abrir", { que: "sesiones" });

poll();
requestAnimationFrame(tick);
