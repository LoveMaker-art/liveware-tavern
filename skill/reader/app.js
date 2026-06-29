"use strict";
const $ = (s) => document.querySelector(s);
const state = { cards: [], cardMap: {}, worldbooks: {}, productions: [], activeId: null, active: null, busy: false };

function esc(s) { return (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function fmt(t) { return esc(t).replace(/\*([^*]+)\*/g, '<span class="nar">$1</span>'); }
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), 2600); }

async function loadAll() {
  const [pr, cr, wr] = await Promise.all([
    bridge.get("/api/productions"), bridge.get("/api/cards"), bridge.get("/api/worldbooks"),
  ]);
  state.productions = pr.productions || [];
  state.cards = cr.cards || [];
  state.cardMap = {}; state.cards.forEach((c) => (state.cardMap[c.id] = c));
  state.worldbooks = {}; (wr.worldbooks || []).forEach((w) => (state.worldbooks[w.id] = w));
  state.activeId = pr.active || (state.productions[0] && state.productions[0].id) || null;
  state.active = state.productions.find((p) => p.id === state.activeId) || null;
  renderRail(); renderStage(); renderPanel();
}

function renderRail() {
  const ul = $("#prodList");
  ul.innerHTML = state.productions.map((p) =>
    `<li class="prodItem ${p.id === state.activeId ? "active" : ""}" data-id="${p.id}">
       <span class="prodDot"></span><span>${esc(p.name)}</span></li>`).join("");
  ul.querySelectorAll(".prodItem").forEach((li) =>
    li.onclick = () => switchProd(li.dataset.id));
}

function renderStage() {
  const p = state.active;
  $("#prodName").textContent = p ? p.name : "酒馆";
  const c = $("#convo");
  if (!p) { c.innerHTML = `<div class="empty"><div class="emptyMark">✦</div><p>导入一张角色卡，开一场戏。</p><p class="hint">墨会入戏陪你演。</p></div>`; return; }
  const turns = p.story.map((m) => turnHtml(m)).join("");
  c.innerHTML = `<div class="thread">${turns}</div>`;
  bindCtls();
  scrollDown();
}

function turnHtml(m) {
  if (m.role === "user") {
    return `<div class="turn user"><div class="body">${fmt(m.text)}</div></div>`;
  }
  return `<div class="turn char" data-id="${m.id}">
    <div class="body">${fmt(m.text)}</div>
    <div class="ctl"><button data-act="regen">重生成</button><button data-act="edit">编辑</button></div></div>`;
}

function bindCtls() {
  document.querySelectorAll('.ctl [data-act="regen"]').forEach((b) =>
    b.onclick = () => regenerate());
  document.querySelectorAll('.ctl [data-act="edit"]').forEach((b) =>
    b.onclick = (e) => editMsg(e.target.closest(".turn").dataset.id));
}

function renderPanel() {
  const p = state.active;
  const ci = $("#charInfo"), li = $("#loreInfo");
  if (!p) { ci.innerHTML = '<p class="cdesc">还没开戏。</p>'; li.innerHTML = ""; return; }
  const card = state.cardMap[p.card_id] || {};
  ci.innerHTML = `<p class="cname">${esc(card.name || "")}</p>
    <p class="cdesc">${esc(card.description || "")}</p>
    <div class="ctags">${(card.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>`;
  const lore = [];
  (p.worldbook_ids || []).forEach((wid) => (state.worldbooks[wid]?.entries || []).forEach((e) => lore.push(e)));
  li.innerHTML = lore.length ? lore.map((e) =>
    `<div class="lore"><span class="lk">${(e.keys || []).join(" · ") || "常驻"}</span><br>${esc(e.content)}</div>`).join("")
    : '<p class="cdesc" style="color:var(--muted)">无</p>';
}

async function switchProd(id) {
  closeDrawers();
  try {
    const r = await bridge.event({ type: "switch_loadout", production_id: id });
    state.active = r.production; state.activeId = id;
    renderRail(); renderStage(); renderPanel();
  } catch (e) { toast("切换失败：" + e.message); }
}

async function send() {
  const input = $("#input"); const text = input.value.trim();
  if (!text || state.busy || !state.active) return;
  state.busy = true; $("#sendBtn").disabled = true;
  input.value = ""; autoGrow(input);
  state.active.story.push({ role: "user", text });
  renderStage();
  const thread = $(".thread");
  thread.insertAdjacentHTML("beforeend", `<div class="turn char" id="think"><div class="body thinking">墨正在入戏…</div></div>`);
  scrollDown();
  try {
    const r = await bridge.event({ type: "send_message", production_id: state.active.id, text });
    state.active.story.push(r.message);
    renderStage();
  } catch (e) {
    $("#think")?.remove(); toast("生成失败：" + e.message);
    state.active.story.pop(); renderStage();
  } finally { state.busy = false; $("#sendBtn").disabled = false; input.focus(); }
}

async function regenerate() {
  if (state.busy || !state.active) return;
  state.busy = true;
  try {
    const r = await bridge.event({ type: "regenerate", production_id: state.active.id });
    const last = state.active.story[state.active.story.length - 1];
    if (last) last.text = r.message.text;
    renderStage();
  } catch (e) { toast("重生成失败：" + e.message); }
  finally { state.busy = false; }
}

async function editMsg(id) {
  const m = state.active.story.find((x) => x.id === id); if (!m) return;
  const v = prompt("编辑这条：", m.text); if (v == null) return;
  try { await bridge.event({ type: "edit_message", production_id: state.active.id, message_id: id, text: v }); m.text = v; renderStage(); }
  catch (e) { toast("编辑失败：" + e.message); }
}

function fileToB64(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(String(r.result).split(",")[1]);
    r.onerror = rej; r.readAsDataURL(file);
  });
}

async function importCard(file) {
  if (!file) return;
  toast("解析角色卡…");
  try {
    const b64 = await fileToB64(file);
    const r = await bridge.event({ type: "import_card", png_base64: b64 });
    await loadAll();
    toast("已导入：" + r.card.name);
    await newProductionFrom(r.card.id);
  } catch (e) { toast("导入失败：" + e.message); }
}

async function newProductionFrom(cardId) {
  const card = state.cardMap[cardId]; if (!card) return;
  const wbId = "wb_" + cardId;
  const wbs = state.worldbooks[wbId] ? [wbId] : [];
  try {
    const r = await bridge.event({ type: "create_production", card_id: cardId, worldbook_ids: wbs, name: card.name });
    await loadAll(); switchProd(r.production.id);
  } catch (e) { toast("建剧组失败：" + e.message); }
}

function showCardPicker() {
  const box = $("#cardPicker");
  if (!state.cards.length) { toast("先导入一张角色卡"); return; }
  box.innerHTML = state.cards.map((c) => `<div class="cardPick" data-id="${c.id}">${esc(c.name)}</div>`).join("");
  box.classList.toggle("hidden");
  box.querySelectorAll(".cardPick").forEach((d) => d.onclick = () => { box.classList.add("hidden"); newProductionFrom(d.dataset.id); });
}

function autoGrow(el) { el.style.height = "auto"; el.style.height = Math.min(el.scrollHeight, 140) + "px"; }
function scrollDown() { const c = $("#convo"); c.scrollTop = c.scrollHeight; }
function openDrawer(id) { $(id).classList.add("open"); $("#scrim").classList.remove("hidden"); }
function closeDrawers() { $("#rail").classList.remove("open"); $("#panel").classList.remove("open"); $("#scrim").classList.add("hidden"); }

function wire() {
  $("#composer").onsubmit = (e) => { e.preventDefault(); send(); };
  $("#input").oninput = (e) => autoGrow(e.target);
  $("#input").onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } };
  $("#cardFile").onchange = (e) => importCard(e.target.files[0]);
  $("#newProdBtn").onclick = showCardPicker;
  $("#railToggle").onclick = () => openDrawer("#rail");
  $("#panelToggle").onclick = () => openDrawer("#panel");
  $("#scrim").onclick = closeDrawers;
}

wire();
loadAll().catch((e) => toast("加载失败：" + e.message));
