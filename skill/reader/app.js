"use strict";
const $ = (s) => document.querySelector(s);
const state = { cards: [], cardMap: {}, worldbooks: {}, productions: [], activeId: null, active: null,
  actor: "", version: "", busy: false, abort: null, stick: true, _anchor: null };

function esc(s) { return (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function fmt(t) { return esc(t).replace(/\*([^*]+)\*/g, '<span class="nar">$1</span>'); }
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), 2600); }
function el(tag, cls) { const e = document.createElement(tag); if (cls) e.className = cls; return e; }

// 内联图标(reader 不挂图标字体)——细描边,克制。
const TRASH_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>';
const SEED_SVG = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21V11M12 11C12 7 9 5 4 5c0 5 3 6 8 6M12 13c0-3 3-5 8-5 0 4-3 5-8 5"/></svg>';
const BOOK_SVG = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4a2 2 0 0 1 2-2h12v15H7a2 2 0 0 0-2 2zM19 17H7M5 4v16"/></svg>';
const WORLD_SVG = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/></svg>';
const SEND_SVG = '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20V5M6 11l6-6 6 6"/></svg>';
const STOP_SVG = '<svg viewBox="0 0 24 24" width="15" height="15"><rect x="6.5" y="6.5" width="11" height="11" rx="2.6" fill="currentColor"/></svg>';

// 对话轮数 = 用户出手数(first_mes 是 char 开场,不算)。最近活跃 = story 末条时间。
function countTurns(story) { return (story || []).filter((m) => m.role === "user").length; }
function lastActivity(story, createdAt) {
  let t = createdAt || 0;
  (story || []).forEach((m) => { if (m.ts && m.ts > t) t = m.ts; });
  return t ? relTime(t) : "";
}
function relTime(ts) {
  const d = Math.max(0, Date.now() / 1000 - ts);
  if (d < 60) return "刚刚";
  if (d < 3600) return Math.floor(d / 60) + " 分钟前";
  if (d < 86400) return Math.floor(d / 3600) + " 小时前";
  if (d < 172800) return "昨天";
  if (d < 86400 * 8) return Math.floor(d / 86400) + " 天前";
  const dt = new Date(ts * 1000);
  return (dt.getMonth() + 1) + " 月 " + dt.getDate() + " 日";
}

async function loadAll() {
  const [pr, cr, wr, ar] = await Promise.all([
    bridge.get("/api/productions"), bridge.get("/api/cards"), bridge.get("/api/worldbooks"),
    bridge.get("/api/actor"),
  ]);
  state.productions = pr.productions || [];
  state.cards = cr.cards || [];
  state.cardMap = {}; state.cards.forEach((c) => (state.cardMap[c.id] = c));
  state.worldbooks = {}; (wr.worldbooks || []).forEach((w) => (state.worldbooks[w.id] = w));
  state.actor = ar.actor_self || "";        // 演员墨技艺层(富提示词,会积累)
  state.version = ar.version || "";          // 活件版本(酒馆 app 自己的发版号)
  state.activeId = pr.active || (state.productions[0] && state.productions[0].id) || null;
  state.active = state.productions.find((p) => p.id === state.activeId) || null;
  renderRail(); renderStage(); renderPanel();
}

function renderRail() {
  const ul = $("#prodList");
  ul.innerHTML = state.productions.map((p) => {
    const card = state.cardMap[p.card_id] || {};
    const turns = countTurns(p.story);
    const meta = [card.name, turns > 0 ? turns + " 轮" : "新戏", lastActivity(p.story, p.created_at)]
      .filter(Boolean).join(" · ");
    return `<li class="prodItem ${p.id === state.activeId ? "active" : ""}" data-id="${p.id}">
      <div class="prodName2">${esc(p.name)}</div>
      <div class="prodMeta">${esc(meta)}</div>
      <button class="prodDel" data-del="${p.id}" aria-label="删除剧组" title="删除剧组">${TRASH_SVG}</button>
    </li>`;
  }).join("");
  ul.querySelectorAll(".prodItem").forEach((li) =>
    li.onclick = () => switchProd(li.dataset.id));
  // 删除 = 看得见可点的 trash(桌面 hover 浮出 / 触屏常驻),tap → 二次确认。无原生长按手势。
  ul.querySelectorAll(".prodDel").forEach((b) =>
    b.onclick = (e) => { e.stopPropagation(); askDeleteProduction(b.dataset.del); });
}

function renderStage() {
  const p = state.active;
  $("#prodName").textContent = p ? p.name : "酒馆";
  const card = p ? (state.cardMap[p.card_id] || {}) : {};
  $("#prodSub").textContent = card.name ? "墨 · " + card.name : "";   // 活件/演员归属(副标题)
  const c = $("#convo");
  if (!p) { c.innerHTML = `<div class="empty"><div class="emptyMark">✦</div><p>导入一张角色卡，开一场戏。</p><p class="hint">墨会入戏陪你演。</p></div>`; return; }
  const turns = p.story.map((m, i) => turnHtml(m, i === p.story.length - 1)).join("");
  c.innerHTML = `<div class="thread">${turns}</div>`;
  bindCtls();
  scrollDown();
}

function turnHtml(m, isLast) {
  if (m.role === "user") {
    return `<div class="turn user"><div class="body">${fmt(m.text)}</div></div>`;
  }
  // swipe 备选回复:char 消息持有 alts[]/active_alt(非破坏性,conversation-surface §3.1)
  const alts = Array.isArray(m.alts) ? m.alts.length : 0;
  const active = m.active_alt || 0;
  const swipe = alts > 1
    ? `<span class="swipe">
         <button data-act="swl" aria-label="上一条" ${active === 0 ? "disabled" : ""}>‹</button>
         <span class="idx">${active + 1}/${alts}</span>
         <button data-act="swr" aria-label="下一条" ${active === alts - 1 ? "disabled" : ""}>›</button>
       </span>` : "";
  // 重生成只挂最后一条 char(服务端只重演 story 末条;挂别处会重生成错的那条)
  const regen = isLast ? `<button data-act="regen">重生成</button>` : "";
  return `<div class="turn char" data-id="${m.id}">
    <div class="body">${fmt(m.text)}</div>
    <div class="ctl">${swipe}${regen}<button data-act="edit">编辑</button></div></div>`;
}

function bindCtls() {
  document.querySelectorAll('.ctl [data-act="regen"]').forEach((b) =>
    b.onclick = () => regenerate());
  document.querySelectorAll('.ctl [data-act="edit"]').forEach((b) =>
    b.onclick = (e) => editMsg(e.target.closest(".turn").dataset.id));
  document.querySelectorAll('.ctl [data-act="swl"]').forEach((b) =>
    b.onclick = (e) => swipe(e.target.closest(".turn").dataset.id, -1));
  document.querySelectorAll('.ctl [data-act="swr"]').forEach((b) =>
    b.onclick = (e) => swipe(e.target.closest(".turn").dataset.id, 1));
}

// 角色卡来源/出处(Task 2):有 creator(卡作者)显作者;Agent 原创(import_card_json)显「Agent 创作」。
function provenanceHtml(card) {
  const creator = (card.creator || "").trim();
  const src = card.source || "";
  if (creator) return `<div class="prov">${WORLD_SVG}${esc("来源 · " + creator)}</div>`;
  if (src === "agent") return `<div class="prov"><span style="color:var(--brand)">✦</span>Agent 创作</div>`;
  if (src === "chub") return `<div class="prov">${WORLD_SVG}来源 · Chub</div>`;
  return "";
}

// 演员墨技艺层(Task 5):随演出/复盘积累的富提示词,把「越演越懂你」做成可见特征。
function parseActorSelf(md) {
  const out = { knows: [], growth: 0 };
  if (!md) return out;
  const sections = {}; let cur = null;
  md.split("\n").forEach((line) => {
    const h = line.match(/^#\s+(.+)/);
    if (h) { cur = h[1]; sections[cur] = []; return; }
    if (cur) sections[cur].push(line);
  });
  const find = (kw) => Object.keys(sections).find((k) => k.includes(kw));
  const isPlaceholder = (s) => /^（.*）$/.test(s.trim()) || s.includes("还不了解") || s.includes("空。");
  const ks = find("我对你的了解");
  if (ks) sections[ks].forEach((l) => { const m = l.match(/^[-*]\s+(.+)/); if (m && !isPlaceholder(m[1])) out.knows.push(m[1].trim()); });
  const gs = find("成长记");
  if (gs) sections[gs].forEach((l) => { const m = l.match(/^[-*]\s+(.+)/); if (m && !isPlaceholder(m[1])) out.growth++; });
  return out;
}

function actorSectionHtml() {
  const a = parseActorSelf(state.actor);
  const knows = a.knows.length
    ? `<ul class="knowList">${a.knows.slice(0, 4).map((k) => `<li>${esc(k)}</li>`).join("")}</ul>`
    : `<p class="pmuted">还在熟悉你。等演几场，墨会把你的口味记到这。</p>`;
  const grow = a.growth > 0 ? `<div class="growRow">${SEED_SVG}成长记 ${a.growth} 条</div>` : "";
  return `<div class="pSection actorSec">
    <div class="actorHd"><span class="pHead">演员 · 墨</span></div>
    <div class="knowHd">越演越懂你</div>
    ${knows}${grow}
    <button class="actorMore" id="actorMore">${BOOK_SVG}查看演员手记</button>
  </div>`;
}

function renderPanel() {
  const body = $("#panelBody");
  const p = state.active;
  const actorSec = actorSectionHtml();   // 演员墨跨剧组,始终显
  const lwFoot = state.version
    ? `<div class="lwFoot" title="酒馆是一个活件：墨可以改它的功能与样子，再发一版"><span class="mark">✦</span>活件 · 酒馆 v${esc(state.version)}</div>`
    : "";
  let sections;
  if (!p) {
    sections = `<div class="pSection"><div class="pHead">角色</div><p class="pmuted">还没开戏。</p></div>`;
  } else {
    const card = state.cardMap[p.card_id] || {};
    const tags = (card.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("");
    const charSec = `<div class="pSection">
      <div class="pHead">角色</div>
      <p class="cname">${esc(card.name || "")}</p>
      ${provenanceHtml(card)}
      <p class="cdesc">${esc(card.description || "")}</p>
      ${tags ? `<div class="ctags">${tags}</div>` : ""}
    </div>`;
    const lore = [];
    (p.worldbook_ids || []).forEach((wid) => (state.worldbooks[wid]?.entries || []).forEach((e) => lore.push(e)));
    const loreSec = `<div class="pSection">
      <div class="pHead">世界书</div>
      ${lore.length ? lore.map((e) => `<div class="lore"><span class="lk">${esc((e.keys || []).join(" · ") || "常驻")}</span><br>${esc(e.content)}</div>`).join("")
        : '<p class="pmuted">无</p>'}
    </div>`;
    sections = charSec + loreSec;
  }
  body.innerHTML = sections + actorSec + lwFoot;
  const more = $("#actorMore");
  if (more) more.onclick = openActorSheet;
}

async function switchProd(id) {
  closeDrawers();
  try {
    const r = await bridge.event({ type: "switch_loadout", production_id: id });
    state.active = r.production; state.activeId = id;
    renderRail(); renderStage(); renderPanel();
  } catch (e) { toast("切换失败：" + e.message); }
}

// 发送中按钮变「停止」:点它/回车 = 早停(中途停)。否则 = 发送。
function submitOrStop() {
  if (state.busy) { if (state.abort) state.abort.abort(); }
  else send();
}
function setComposerSending(sending) {
  const b = $("#sendBtn");
  b.classList.toggle("stop", sending);
  b.innerHTML = sending ? STOP_SVG : SEND_SVG;
  b.setAttribute("aria-label", sending ? "停止" : "发送");
  if (sending) b.classList.remove("empty");
  else updateSendEmpty();
}
// 没东西可发时发送键走静默灰态(发送中=停止键,恒亮)。
function updateSendEmpty() {
  if (state.busy) return;
  $("#sendBtn").classList.toggle("empty", !$("#input").value.trim());
}

async function send() {
  const input = $("#input"); const text = input.value.trim();
  if (!text || state.busy || !state.active) return;
  const ac = new AbortController(); state.abort = ac;
  state.busy = true; setComposerSending(true);
  input.value = ""; autoGrow(input);
  if (isTouch()) input.blur(); // 移动端:发送即收键盘,别盖住正在生成的回复(反馈 2026-06-30)
  state.active.story.push({ role: "user", text });
  renderStage();
  $(".thread").insertAdjacentHTML("beforeend", `<div class="turn char" id="think"><div class="body thinking">墨正在入戏…</div></div>`);
  anchorTurn(lastUserTurn(), true); // 锚到「我刚输入的那条」(新回合,重置 stick)
  const ev = { type: "send_message", production_id: state.active.id, text };
  let acc = "";
  const onDelta = (d) => {
    acc += d;
    const b = document.querySelector("#think .body");
    if (b) { b.classList.remove("thinking"); b.innerHTML = fmt(acc); anchorTurn(lastUserTurn()); } // 跟内容长:短→跟到底,长→钉住我的话
  };
  try {
    let msg;
    try {
      msg = await bridge.eventStream(ev, onDelta, ac.signal);   // 流式逐字
    } catch (streamErr) {
      if (ac.signal.aborted) {
        if (!acc.trim()) {                                       // 早停且还没生成出东西 → 当取消
          $("#think")?.remove(); state.active.story.pop(); renderStage();
          input.value = text; autoGrow(input);
          return;
        }
        // 早停:保留已生成的半截(流式断开时 server 没落盘,这里把这一回合补存)
        msg = (await bridge.event({ type: "append_turn", production_id: state.active.id,
                                    user_text: text, char_text: acc })).message;
      } else {
        msg = (await bridge.event(ev)).message;                 // 传输层不支持流式 → 回退阻塞式
      }
    }
    $("#think")?.remove();
    state.active.story.push(msg);
    renderStage();
    anchorTurn(lastUserTurn()); // 回复就位:沿用锚定(尊重用户生成中途的上滚)
  } catch (e) {
    $("#think")?.remove(); toast("生成失败：" + e.message);
    state.active.story.pop(); renderStage();
    input.value = text; autoGrow(input); // 失败不丢已输入文字,可直接重发(§4)
  } finally {
    state.busy = false; state.abort = null; setComposerSending(false);
    if (!isTouch()) input.focus(); // 桌面续焦点方便接着打;移动不抢焦,留给阅读
  }
}

async function regenerate() {
  if (state.busy || !state.active) return;
  state.busy = true;
  try {
    const r = await bridge.event({ type: "regenerate", production_id: state.active.id });
    // 非破坏性:整条替换(服务端已把新生成 append 进 alts、active_alt 指向它),保留旧版供 swipe
    state.active.story[state.active.story.length - 1] = r.message;
    renderStage();
    anchorTurn(lastUserTurn(), true); // 重生成:重新锚到我的话,新回复在下方
  } catch (e) { toast("重生成失败：" + e.message); }
  finally { state.busy = false; }
}

async function swipe(id, dir) {
  const m = state.active && state.active.story.find((x) => x.id === id);
  if (!m || !Array.isArray(m.alts)) return;
  const cur = m.active_alt || 0;
  const next = cur + dir;
  if (next < 0 || next >= m.alts.length) return;
  m.active_alt = next; m.text = m.alts[next]; renderStage(); // 乐观切换
  anchorTurn(lastUserTurn(), true); // 切备选:锚到我的话,新版本在下方
  try {
    await bridge.event({ type: "swipe", production_id: state.active.id, message_id: id, dir });
  } catch (e) {
    m.active_alt = cur; m.text = m.alts[cur]; renderStage(); toast("切换失败：" + e.message);
  }
}

// 行内编辑器:替代 window.prompt()——macOS 容器 WKWebView 里 prompt 是死的(未实现
// runJavaScriptTextInputPanel),且单行对多段 RP 文本是灾难(conversation-surface §3.2)。
function editMsg(id) {
  const turn = document.querySelector(`.turn[data-id="${id}"]`);
  const m = state.active && state.active.story.find((x) => x.id === id);
  if (!turn || !m || turn.querySelector(".editbox")) return;
  const body = turn.querySelector(".body");
  const ctl = turn.querySelector(".ctl");
  const ta = document.createElement("textarea");
  ta.className = "editbox"; ta.value = m.text;
  const acts = document.createElement("div");
  acts.className = "editacts";
  acts.innerHTML = `<button class="save">保存</button><button class="cancel">取消</button>`;
  body.style.display = "none"; if (ctl) ctl.style.display = "none";
  turn.appendChild(ta); turn.appendChild(acts);
  growEdit(ta); ta.focus();
  const close = () => { ta.remove(); acts.remove(); body.style.display = ""; if (ctl) ctl.style.display = ""; };
  const save = async () => {
    const v = ta.value;
    try {
      await bridge.event({ type: "edit_message", production_id: state.active.id, message_id: id, text: v });
      m.text = v; if (Array.isArray(m.alts)) m.alts[m.active_alt || 0] = v;
      renderStage();
    } catch (e) { toast("编辑失败：" + e.message); }
  };
  ta.oninput = () => growEdit(ta);
  ta.onkeydown = (e) => {
    if (e.isComposing || e.keyCode === 229) return; // IME 合成中不抢键
    if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); save(); }
  };
  acts.querySelector(".cancel").onclick = close;
  acts.querySelector(".save").onclick = save;
}

function growEdit(el) { el.style.height = "auto"; el.style.height = el.scrollHeight + "px"; }

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

// 粘贴卡 JSON 导入(import_card_json):macOS 容器文件选择器是死的,这是纯 web 旁路。
async function importCardJson(raw) {
  let card;
  try { card = JSON.parse(raw); }
  catch (_) { toast("不是合法的角色卡 JSON"); return; }
  toast("解析角色卡…");
  try {
    const r = await bridge.event({ type: "import_card_json", card });
    await loadAll();
    toast("已导入：" + r.card.name);
    await newProductionFrom(r.card.id);
  } catch (e) { toast("导入失败：" + e.message); }
}

// 拖入 PNG(import_card)/JSON(import_card_json)——另一条不依赖文件选择器的入口。
function wireDropImport() {
  const stage = $("#stage");
  const stop = (e) => { e.preventDefault(); e.stopPropagation(); };
  ["dragenter", "dragover"].forEach((t) =>
    stage.addEventListener(t, (e) => { stop(e); stage.classList.add("dragging"); }));
  stage.addEventListener("dragleave", (e) => {
    stop(e);
    if (e.relatedTarget && stage.contains(e.relatedTarget)) return; // 仍在 stage 内,别闪
    stage.classList.remove("dragging");
  });
  stage.addEventListener("drop", async (e) => {
    stop(e); stage.classList.remove("dragging");
    const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    if (!file) return;
    if (/\.png$/i.test(file.name) || file.type === "image/png") importCard(file);
    else if (/\.json$/i.test(file.name) || file.type === "application/json") importCardJson(await file.text());
    else toast("拖入 PNG 角色卡或卡 JSON");
  });
}

function togglePastePanel(show) {
  const pp = $("#pastePanel");
  const open = show === undefined ? pp.classList.contains("hidden") : show;
  pp.classList.toggle("hidden", !open);
  if (open) $("#pasteBox").focus(); else $("#pasteBox").value = "";
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
// 这一回合「我说的那条」(末条用户消息)——滚动锚定的基准。
function lastUserTurn() { const us = document.querySelectorAll(".turn.user"); return us[us.length - 1] || null; }
// 发送后的滚动定位(双端,反馈 2026-06-30 修正):把「我刚输入的那条」摆到接近视口顶(留 20px),
// 再夹进自然滚动范围。→ 回复短:夹到自然底(IM 式,我的话+回复都在视口、几乎不滚);
//   回复长:我的话钉在顶、回复在下方铺开(从我说的话往下读)。两种情况都始终看得到自己输入的那条。
// force=true:新回合,重置 stick 并锚定;否则尊重用户生成中途的上滚(不跟用户抢)。
function anchorTurn(el, force) {
  const c = $("#convo");
  if (!c || !el) return;
  if (force) state.stick = true;
  if (!state.stick) return;
  const top = el.getBoundingClientRect().top - c.getBoundingClientRect().top + c.scrollTop - 20;
  c.scrollTop = state._anchor = Math.max(0, Math.min(top, c.scrollHeight - c.clientHeight));
}
// 触屏(移动)= 无 hover。用于「发送后不自动弹键盘」等只在移动端做的事(反馈 2026-06-30)。
const isTouch = () => window.matchMedia("(hover: none)").matches;
function openDrawer(id) { $(id).classList.add("open"); $("#scrim").classList.remove("hidden"); }
function closeDrawers() { $("#rail").classList.remove("open"); $("#panel").classList.remove("open"); $("#scrim").classList.add("hidden"); }

// ---- 弹层(二次确认 / 演员手记):点背板或 Esc 关闭 ----
let _modalClose = null;
function openModal(node, onClose) {
  const m = $("#modal");
  m.innerHTML = ""; m.appendChild(node);
  m.classList.remove("hidden");
  _modalClose = onClose || null;
  m.onclick = (e) => { if (e.target === m) closeModal(); };
  document.addEventListener("keydown", modalEsc);
}
function closeModal() {
  const m = $("#modal");
  if (m.classList.contains("hidden")) return;
  m.classList.add("hidden"); m.innerHTML = "";
  document.removeEventListener("keydown", modalEsc);
  const cb = _modalClose; _modalClose = null; if (cb) cb();
}

function modalEsc(e) { if (e.key === "Escape") closeModal(); }

// 二次确认(不可逆动作):返回 Promise<bool>。背板/Esc/取消 → false。
function confirmDialog({ title, body, confirmLabel = "删除" }) {
  return new Promise((resolve) => {
    let decided = false;
    const card = el("div", "modalCard");
    card.innerHTML = `<p class="modalTitle">${esc(title)}</p>
      <p class="modalBody">${esc(body)}</p>
      <div class="modalActs"><button class="mBtnCancel">取消</button>
      <button class="mBtnDanger">${esc(confirmLabel)}</button></div>`;
    openModal(card, () => { if (!decided) resolve(false); });
    const done = (v) => { decided = true; closeModal(); resolve(v); };
    card.querySelector(".mBtnCancel").onclick = () => done(false);
    card.querySelector(".mBtnDanger").onclick = () => done(true);
  });
}

async function askDeleteProduction(id) {
  const p = state.productions.find((x) => x.id === id);
  if (!p) return;
  const ok = await confirmDialog({
    title: `删除「${p.name}」？`,
    body: "这场戏的全部对话记录会一起删除，且无法恢复。",
    confirmLabel: "删除",
  });
  if (!ok) return;
  try {
    await bridge.event({ type: "delete_production", production_id: id });
    await loadAll();   // server 已切好 active,loadAll 重渲染
    toast("已删除剧组");
  } catch (e) { toast("删除失败：" + e.message); }
}

// 演员手记:把 actor_self.md(随演出积累的那份富提示词)整份渲染出来——「越演越懂你」看得见。
const mfmt = (s) => esc(s).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/\*([^*]+)\*/g, "<em>$1</em>");
function mdToHtml(md) {
  let html = "";
  (md || "").split("\n").forEach((raw) => {
    const line = raw.replace(/\r$/, "");
    const h = line.match(/^#+\s+(.+)/), li = line.match(/^[-*]\s+(.+)/);
    if (h) html += `<div class="mh">${mfmt(h[1])}</div>`;
    else if (li) html += `<div class="mli">${mfmt(li[1])}</div>`;
    else if (line.trim()) html += `<div class="mp">${mfmt(line)}</div>`;
  });
  return `<div class="md">${html}</div>`;
}
function openActorSheet() {
  const intro = '<div class="mp" style="color:var(--muted);margin-bottom:13px">墨随每场戏与复盘积累的演艺手记——越演越懂你。这是注入每一场戏的那份提示词。</div>';
  const card = el("div", "modalCard sheetCard");
  card.innerHTML = `<div class="sheetHd"><span class="t">演员手记 · 墨</span>
      <button class="sheetClose" aria-label="关闭">✕</button></div>
    <div class="sheetBody">${intro}${mdToHtml(state.actor)}</div>`;
  openModal(card);
  card.querySelector(".sheetClose").onclick = closeModal;
}

// 软键盘弹起把可视视口压小:iOS WKWebView 不认 interactive-widget/dvh 的键盘收缩,
// 用 visualViewport 把 body 高度贴到可视视口(Android 由 meta interactive-widget+dvh 覆盖)。
function keyboardInset() {
  const vv = window.visualViewport;
  if (!vv) return;
  const apply = () => { document.body.style.height = vv.height + "px"; };
  vv.addEventListener("resize", apply);
  vv.addEventListener("scroll", apply);
  apply();
}

function wire() {
  $("#composer").onsubmit = (e) => { e.preventDefault(); submitOrStop(); };
  const input = $("#input");
  input.oninput = (e) => { autoGrow(e.target); updateSendEmpty(); };
  // IME 守卫(含 macOS WKWebView/WebKit 修正):
  // - Chromium:合成中的 Enter 带 isComposing=true / keyCode=229,直接挡。
  // - WebKit(macOS 容器 + Safari):compositionend 排在「确认候选词」的 Enter keydown **之前**,
  //   那个 keydown 的 isComposing 已是 false、keyCode=13 → 光靠 isComposing/229 挡不住(实测仍误发)。
  //   故再记一个「刚合成完」时间窗(CodeMirror/ProseMirror 同款),把紧跟其后的回车也判为确认、不发送。
  let imeComposing = false, imeEndedAt = 0;
  input.addEventListener("compositionstart", () => { imeComposing = true; });
  input.addEventListener("compositionend", () => { imeComposing = false; imeEndedAt = Date.now(); });
  input.onkeydown = (e) => {
    if (e.isComposing || e.keyCode === 229 || imeComposing) return;
    if (e.key === "Enter" && !e.shiftKey) {
      if (Date.now() - imeEndedAt < 120) return; // 刚确认候选词的那个回车(WebKit 排序),别当发送
      e.preventDefault(); submitOrStop();
    }
  };
  $("#cardFile").onchange = (e) => importCard(e.target.files[0]);
  $("#pasteCardBtn").onclick = () => togglePastePanel();
  $("#pasteCancel").onclick = () => togglePastePanel(false);
  $("#pasteImport").onclick = () => { const v = $("#pasteBox").value.trim(); if (v) { togglePastePanel(false); importCardJson(v); } };
  $("#newProdBtn").onclick = showCardPicker;
  wireDropImport();
  $("#railToggle").onclick = () => openDrawer("#rail");
  $("#panelToggle").onclick = () => openDrawer("#panel");
  $("#scrim").onclick = closeDrawers;
  // 生成中用户主动上滚(回看历史)→ 停止自动锚定,别跟用户抢;下一回合 force 重置。
  $("#convo").addEventListener("scroll", () => {
    if (state.busy && state._anchor != null && state._anchor - $("#convo").scrollTop > 24) state.stick = false;
  }, { passive: true });
  setComposerSending(false);   // 初始 SVG 发送图标 + 空态
}

keyboardInset();
wire();
loadAll().catch((e) => toast("加载失败：" + e.message));
