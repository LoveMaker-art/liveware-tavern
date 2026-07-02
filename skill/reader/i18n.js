/* i18n — reader 的语言层(locale contract:容器打开活件时在 URL 带 ?lang=<app语言>,
 * 详见 clawchat 仓 docs/liveware/container.md §语言;liveware-frontend §i18n)。
 *
 * 解析链:?lang=(容器注入,存 sessionStorage 供页内导航)→ sessionStorage →
 * navigator.language(独立浏览器打开时的兜底)→ zh;未收录的语言回落 en。
 *
 * 给二创墨的「加语言」入口:在 STRINGS 加一个 locale 对象(**全量 key**,拿 en 当模板
 * 逐 key 翻),升 SKILL.md version 发版即可——别的文件一行不用动。守则:
 * ① 「Liveware」「✦」是品牌锚不翻译;「墨」用该语言的自然写法(en = Mo)。
 * ② 缺 key 自动回落 en → zh,但别依赖回落——加语言就加全。
 * ③ 带 {x} 的是插值占位,翻译时保留。
 */
"use strict";
const I18N = (() => {
  const STRINGS = {
    zh: {
      // 文档 / 顶栏
      docTitleConsole: "酒馆",
      docTitleActor: "墨 · 演员卡",
      appTitle: "酒馆",
      actorPageTitle: "墨 · 演员",
      prodSubPrefix: "墨 · {name}",
      ariaRail: "剧组",
      ariaPanel: "角色与世界书",
      ariaBack: "返回酒馆",
      // 左栏 · 剧组
      railHead: "剧组",
      importCard: "导入角色卡",
      pasteJson: "粘贴卡 JSON",
      newFromCards: "从已有卡新建",
      pastePlaceholder: "粘贴角色卡 JSON(V1/V2/V3,可含 character_book)…",
      pasteImport: "导入",
      cancel: "取消",
      deleteProd: "删除剧组",
      newPlay: "新戏",
      turnsShort: "{n} 轮",
      // 相对时间
      justNow: "刚刚",
      minAgo: "{n} 分钟前",
      hourAgo: "{n} 小时前",
      yesterday: "昨天",
      dayAgo: "{n} 天前",
      monthDay: "{m} 月 {d} 日",
      // 舞台
      emptyLead: "导入一张角色卡,开一场戏。",
      emptyHint: "墨会入戏陪你演。",
      composerPlaceholder: "续写这一场…",
      ariaSend: "发送",
      ariaStop: "停止",
      thinking: "墨正在入戏…",
      regen: "重生成",
      edit: "编辑",
      save: "保存",
      ariaPrev: "上一条",
      ariaNext: "下一条",
      dropHint: "松手导入角色卡(PNG / JSON)",
      // 右栏 · 面板
      pCharacter: "角色",
      pNoPlay: "还没开戏。",
      pLorebook: "世界书",
      pAlwaysOn: "常驻",
      pNone: "无",
      provSource: "来源 · {name}",
      provAgent: "Agent 创作",
      pActor: "演员 · 墨",
      reflectWithMo: "找墨复盘",
      moActorCard: "墨的演员卡",
      reflectDraft: "复盘「{name}」这场戏",
      reflectDraftNoPlay: "复盘最近一场戏",
      pModel: "大模型",
      modelManage: "切换 / 管理",
      modelBuiltin: "墨自带",
      lwFoot: "活件 · 酒馆 v{v}",
      lwFootTip: "酒馆是一个活件:墨可以改它的功能与样子,再发一版",
      // 大模型 sheet
      modelSheetTitle: "大模型",
      ariaClose: "关闭",
      modelBuiltinMeta: "{model} · 调用墨的大模型,开箱即用",
      modelKeyMeta: "{model} · key {mask}",
      ariaDeleteConfig: "删除配置",
      modelHint: "想用自己的 API?对墨说:<br><span class=\"q\">「帮我配上 DeepSeek,key 是 sk-…」</span><br>墨认识市面上主流的大模型服务,会先实测、通了才保存,存好即刻生效。",
      modelSwitchFailed: "切换失败:{err}",
      modelDeleteTitle: "删除「{name}」?",
      modelDeleteBody: "这份 API 配置会被删除。正在用它的话,会切回墨自带。",
      delete: "删除",
      modelDeleted: "已删除配置",
      modelDeleteFailed: "删除失败:{err}",
      // 剧组删除 / 对话动作 toast
      prodDeleteTitle: "删除「{name}」?",
      prodDeleteBody: "这场戏的全部对话记录会一起删除,且无法恢复。",
      prodDeleted: "已删除剧组",
      prodDeleteFailed: "删除失败:{err}",
      switchFailed: "切换失败:{err}",
      genFailed: "生成失败:{err}",
      regenFailed: "重生成失败:{err}",
      editFailed: "编辑失败:{err}",
      loadFailed: "加载失败:{err}",
      parsingCard: "解析角色卡…",
      imported: "已导入:{name}",
      importFailed: "导入失败:{err}",
      badCardJson: "不是合法的角色卡 JSON",
      createProdFailed: "建剧组失败:{err}",
      importFirst: "先导入一张角色卡",
      dropWrongType: "拖入 PNG 角色卡或卡 JSON",
      // 演员卡页
      acLoading: "读取演员卡…",
      acLoadFailed: "读不到演员卡:{err}",
      acNameFallback: "墨",
      statDebut: "出道", statDebutUnit: "天",
      statPlayed: "演出", statPlayedUnit: "轮",
      statWritten: "累计", statWrittenUnit: "字",
      statProds: "剧组", statProdsUnit: "个",
      statRoles: "戏路", statRolesUnit: "条",
      statTimeline: "年表", statTimelineUnit: "笔",
      intimacySub: "一起 {n} 轮 · 记下你 {m} 笔",
      intimacyToNext: "距「{next}」还差 {n} 轮戏",
      intimacyMax: "已是知己",
      acKnowsHead: "我对你的了解",
      acKnowsEmpty: "还在读你的口味——演几场我就懂了。",
      acTimelineHead: "生涯年表",
      acEntriesCount: "{n} 笔",
      acTimelineEmpty: "还没有生涯记录。演几场、复个盘,我就开始长了。",
      acFoot: "活件 · 酒馆 v{v}",
      wan: "万",
    },
    en: {
      docTitleConsole: "Tavern",
      docTitleActor: "Mo · Actor Card",
      appTitle: "Tavern",
      actorPageTitle: "Mo · Actor",
      prodSubPrefix: "Mo · {name}",
      ariaRail: "Productions",
      ariaPanel: "Character & lorebook",
      ariaBack: "Back to Tavern",
      railHead: "Productions",
      importCard: "Import character card",
      pasteJson: "Paste JSON",
      newFromCards: "New from cards",
      pastePlaceholder: "Paste character card JSON (V1/V2/V3, character_book supported)…",
      pasteImport: "Import",
      cancel: "Cancel",
      deleteProd: "Delete production",
      newPlay: "new",
      turnsShort: "{n} turns",
      justNow: "just now",
      minAgo: "{n} min ago",
      hourAgo: "{n} h ago",
      yesterday: "yesterday",
      dayAgo: "{n} days ago",
      monthDay: "{m}/{d}",
      emptyLead: "Import a character card and start a scene.",
      emptyHint: "Mo will step in and play along.",
      composerPlaceholder: "Continue the scene…",
      ariaSend: "Send",
      ariaStop: "Stop",
      thinking: "Mo is getting into character…",
      regen: "Regenerate",
      edit: "Edit",
      save: "Save",
      ariaPrev: "Previous",
      ariaNext: "Next",
      dropHint: "Drop to import a character card (PNG / JSON)",
      pCharacter: "Character",
      pNoPlay: "No scene yet.",
      pLorebook: "Lorebook",
      pAlwaysOn: "Always on",
      pNone: "None",
      provSource: "Source · {name}",
      provAgent: "Created by agent",
      pActor: "Actor · Mo",
      reflectWithMo: "Debrief with Mo",
      moActorCard: "Mo's actor card",
      reflectDraft: "Let's debrief the \"{name}\" scenes",
      reflectDraftNoPlay: "Let's debrief our latest scenes",
      pModel: "Model",
      modelManage: "Switch / Manage",
      modelBuiltin: "Mo's built-in",
      lwFoot: "Liveware · Tavern v{v}",
      lwFootTip: "The Tavern is a liveware: Mo can reshape it and ship a new version",
      modelSheetTitle: "Model",
      ariaClose: "Close",
      modelBuiltinMeta: "{model} · runs on Mo's own model, works out of the box",
      modelKeyMeta: "{model} · key {mask}",
      ariaDeleteConfig: "Delete config",
      modelHint: "Want your own API? Tell Mo:<br><span class=\"q\">\"Set me up with DeepSeek, key sk-…\"</span><br>Mo knows the mainstream model providers — it test-calls first, saves only what works, effective immediately.",
      modelSwitchFailed: "Switch failed: {err}",
      modelDeleteTitle: "Delete \"{name}\"?",
      modelDeleteBody: "This API config will be deleted. If it's in use, Tavern falls back to Mo's built-in.",
      delete: "Delete",
      modelDeleted: "Config deleted",
      modelDeleteFailed: "Delete failed: {err}",
      prodDeleteTitle: "Delete \"{name}\"?",
      prodDeleteBody: "The production's entire story will be deleted. This cannot be undone.",
      prodDeleted: "Production deleted",
      prodDeleteFailed: "Delete failed: {err}",
      switchFailed: "Switch failed: {err}",
      genFailed: "Generation failed: {err}",
      regenFailed: "Regenerate failed: {err}",
      editFailed: "Edit failed: {err}",
      loadFailed: "Load failed: {err}",
      parsingCard: "Parsing card…",
      imported: "Imported: {name}",
      importFailed: "Import failed: {err}",
      badCardJson: "Not a valid character card JSON",
      createProdFailed: "Couldn't create production: {err}",
      importFirst: "Import a character card first",
      dropWrongType: "Drop a PNG character card or card JSON",
      acLoading: "Loading actor card…",
      acLoadFailed: "Couldn't load the actor card: {err}",
      acNameFallback: "Mo",
      statDebut: "Debut", statDebutUnit: "d",
      statPlayed: "Played", statPlayedUnit: "turns",
      statWritten: "Written", statWrittenUnit: "chars",
      statProds: "Productions", statProdsUnit: "",
      statRoles: "Roles", statRolesUnit: "",
      statTimeline: "Timeline", statTimelineUnit: "",
      intimacySub: "{n} turns together · {m} notes on you",
      intimacyToNext: "{n} turns to \"{next}\"",
      intimacyMax: "Already a confidant",
      acKnowsHead: "What I know about you",
      acKnowsEmpty: "Still reading your taste — a few scenes and I'll get it.",
      acTimelineHead: "Career timeline",
      acEntriesCount: "{n} entries",
      acTimelineEmpty: "No career entries yet. Play a few scenes, run a debrief — I'll start growing.",
      acFoot: "Liveware · Tavern v{v}",
      wan: "0k",  // 未用于 en(fmtWords 分语言),占位防回落
    },
  };

  // 解析链:?lang(存 session 供页内导航)→ session → navigator → zh;未收录 → en。
  function pick() {
    let lang = null;
    try {
      const q = new URLSearchParams(location.search).get("lang");
      if (q) { lang = q; sessionStorage.setItem("cc_lang", q); }
      if (!lang) lang = sessionStorage.getItem("cc_lang");
    } catch (_) { /* sessionStorage 被禁(极端隐私模式)→ 走 navigator */ }
    if (!lang) lang = (navigator.language || "zh").slice(0, 2).toLowerCase();
    else lang = lang.slice(0, 2).toLowerCase();
    if (STRINGS[lang]) return lang;
    return lang === "zh" ? "zh" : "en";
  }
  const lang = pick();

  function t(key, params) {
    let s = STRINGS[lang][key];
    if (s === undefined) s = STRINGS.en[key];
    if (s === undefined) s = STRINGS.zh[key];
    if (s === undefined) return key;
    if (params) {
      for (const k in params) s = s.split("{" + k + "}").join(String(params[k]));
    }
    return s;
  }

  // 静态节点填充:data-i18n(textContent)/-placeholder/-aria/-title;
  // <body data-doc-title=key> 定文档标题。动态节点由 app.js/actor.js 用 t() 拼。
  function applyStatic() {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : lang;
    const dt = document.body.dataset.docTitle;
    if (dt) document.title = t(dt);
    document.querySelectorAll("[data-i18n]").forEach((e) => { e.textContent = t(e.dataset.i18n); });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((e) => { e.placeholder = t(e.dataset.i18nPlaceholder); });
    document.querySelectorAll("[data-i18n-aria]").forEach((e) => { e.setAttribute("aria-label", t(e.dataset.i18nAria)); });
    document.querySelectorAll("[data-i18n-title]").forEach((e) => { e.title = t(e.dataset.i18nTitle); });
  }

  return { t, lang, applyStatic };
})();
