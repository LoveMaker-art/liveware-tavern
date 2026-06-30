"use strict";
const $ = (s) => document.querySelector(s);
const state = { cards: [], cardMap: {}, worldbooks: {}, productions: [], activeId: null, active: null, busy: false, abort: null };

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

// 发送中按钮变「停止」:点它/回车 = 早停(中途停)。否则 = 发送。
function submitOrStop() {
  if (state.busy) { if (state.abort) state.abort.abort(); }
  else send();
}
function setComposerSending(sending) {
  const b = $("#sendBtn");
  b.classList.toggle("stop", sending);
  b.textContent = sending ? "■" : "↵";
  b.setAttribute("aria-label", sending ? "停止" : "发送");
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
  scrollTurnToTop($("#think")); // 回复的「头」钉到顶部,内容往下生长,用户从头读
  const ev = { type: "send_message", production_id: state.active.id, text };
  let acc = "";
  const onDelta = (d) => {
    acc += d;
    const b = document.querySelector("#think .body");
    if (b) { b.classList.remove("thinking"); b.innerHTML = fmt(acc); } // 不跟尾:头钉住,从头读
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
    scrollLastCharToTop(); // 回复就位后定位到消息头(双端,覆盖 renderStage 的 scrollDown)
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
    scrollLastCharToTop(); // 重生成的回复也定位到消息头,从头读
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
  scrollTurnToTop(document.querySelector(`.turn.char[data-id="${id}"]`)); // 切到的备选也从头读
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
// AI 回复后定位到消息「头」而非尾——长回复用户能从头完整读(反馈 2026-06-30,双端)。
function scrollTurnToTop(el) {
  const c = $("#convo");
  if (!c || !el) return;
  const thread = c.querySelector(".thread");
  if (thread) {
    // 末条消息下方无内容、本来滚不到顶 → 垫够 padding-bottom,让它的头也能到顶部(短回复也一致)。
    // 仅对末条垫(否则中间消息下方本有内容,加 padding 会留怪空隙)。renderStage 重建 thread 会清掉旧值。
    const isLast = el === thread.lastElementChild;
    thread.style.paddingBottom = (isLast
      ? Math.max(0, c.clientHeight - el.getBoundingClientRect().height - 24) : 0) + "px";
  }
  const top = el.getBoundingClientRect().top - c.getBoundingClientRect().top + c.scrollTop;
  c.scrollTop = Math.max(0, top - 16); // 16px 余量,让消息头上方留口气
}
function scrollLastCharToTop() {
  const turns = document.querySelectorAll(".turn.char");
  scrollTurnToTop(turns[turns.length - 1]);
}
// 触屏(移动)= 无 hover。用于「发送后不自动弹键盘」等只在移动端做的事(反馈 2026-06-30)。
const isTouch = () => window.matchMedia("(hover: none)").matches;
function openDrawer(id) { $(id).classList.add("open"); $("#scrim").classList.remove("hidden"); }
function closeDrawers() { $("#rail").classList.remove("open"); $("#panel").classList.remove("open"); $("#scrim").classList.add("hidden"); }

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
  input.oninput = (e) => autoGrow(e.target);
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
}

keyboardInset();
wire();
loadAll().catch((e) => toast("加载失败：" + e.message));
