"""server — 酒馆演员运行时的同源 server（stdlib http.server，仿 digest）。

serve 控制台静态页(reader/) + /api/*（同源，浏览器同源策略天然满足，模型 creds 留 server 端）。
状态全落 state/ 下 JSON 文件，永不写能力服务器/member-backend。

跑：TAVERN_MODEL_KEY=... python3 server.py [--port 8799]
"""
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import actor  # noqa: E402
import card_import  # noqa: E402

STATE = os.path.join(HERE, "state")
READER = os.path.join(HERE, "reader")
SEED_ACTOR = os.path.join(HERE, "actor_self.md")
for sub in ("cards", "worldbooks", "productions"):
    os.makedirs(os.path.join(STATE, sub), exist_ok=True)

CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
                 ".png": "image/png", ".svg": "image/svg+xml"}


# ---------- state helpers ----------
def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def _write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _state_path():
    return os.path.join(STATE, "state.json")


def _get_state():
    return _read(_state_path(), {"active_production_id": None})


def _set_active(pid):
    s = _get_state()
    s["active_production_id"] = pid
    _write(_state_path(), s)


def actor_self_text():
    rt = os.path.join(STATE, "actor_self.md")
    if not os.path.exists(rt):  # 首次：种子 → 运行时副本(成长改这份，不动种子)
        with open(SEED_ACTOR, encoding="utf-8") as f:
            seed = f.read()
        with open(rt, "w", encoding="utf-8") as f:
            f.write(seed)
    with open(rt, encoding="utf-8") as f:
        return f.read()


def liveware_version():
    # 活件版本 = 酒馆这个 app 自己的发版号(agent 改了功能/皮肤再部署 = 一次发版)。
    # 取 SKILL.md frontmatter 的 version,代表「应用」,与演员技艺层(actor_self.md)是两回事。
    try:
        with open(os.path.join(HERE, "SKILL.md"), encoding="utf-8") as f:
            for line in f:
                if line.startswith("version:"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


def agent_user_id():
    """墨在 ClawChat 里的身份 id(usr_…)——「找墨复盘」深链 clawchat://u/{id}?chat=1 用。
    env 优先(dev/测试);容器里从 hermes config.yaml 文本扫描 `user_id: usr_…`
    (锚定行首键名,不撞 owner_user_id;不引 yaml 依赖,保持纯 stdlib)。拿不到返回
    空串,reader 会隐藏复盘入口——本地 dev 无容器 config 是常态,不算错。"""
    envv = os.environ.get("TAVERN_AGENT_USER_ID", "").strip()
    if envv:
        return envv
    try:
        with open("/opt/data/config.yaml", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("user_id:"):
                    v = s.split(":", 1)[1].strip().strip("'\"")
                    if v.startswith("usr_"):
                        return v
    except OSError:
        pass
    return ""


# ---------- 演员卡聚合（actor-card surface，见 docs/design/actor-card.md）----------
# 纯聚合读现有 state，零新后端。词汇 canon（liveware-frontend §术语表）：
# 戏路 = 演过的角色数（不是"搭档"）；搭档 = 你；亲密度由 轮数 + 权重×年表条数 驱动。
INTIMACY_W = int(os.environ.get("ACTOR_INTIMACY_W", "8"))
# 阶梯（名, 分阈值）。env 后续可覆盖；先常量。
INTIMACY_LADDER = [("初见", 0), ("相识", 15), ("搭档", 40), ("默契", 100), ("知己", 250)]
INTIMACY_BLURB = {"初见": "刚认识，还在摸你的脾气", "相识": "演过几场，记住了你几样",
                  "搭档": "有默契雏形，接得住你的球", "默契": "一个眼神就懂，越演越顺",
                  "知己": "最懂你怎么玩的那个演员"}
# 级名/blurb 的多语言表(locale contract:reader 带 ?lang= 来取——它们是 UI 标签,不是内容;
# 中文名是 canonical(技艺层/CLI 用),其他语言只在下发时映射)。
# 给二创墨的「加语言」入口②:reader 的 STRINGS 加完,在这两张表加同 code 的项(全量 5 级),
# 缺表回落 en。①在 reader/i18n.js,教程见 SKILL.md「帮用户加界面语言」。
INTIMACY_LEVEL_I18N = {
    "en": {"初见": "First Meeting", "相识": "Acquainted", "搭档": "Partners",
           "默契": "In Sync", "知己": "Confidant"},
}
INTIMACY_BLURB_I18N = {
    "en": {"初见": "Just met — still learning your rhythms",
           "相识": "A few scenes in — noted a few of your tastes",
           "搭档": "Early chemistry — I can catch what you throw",
           "默契": "One glance is enough — smoother every scene",
           "知己": "The actor who knows exactly how you play"},
}


def _sections(md):
    """把 actor_self.md 按 '# ' 一级标题切成 {标题: [正文行]}。"""
    secs, cur = {}, None
    for line in md.splitlines():
        if line.startswith("# "):
            cur = line[2:].strip()
            secs[cur] = []
        elif cur is not None:
            secs[cur].append(line)
    return secs


def _bullets(lines):
    return [s[2:].strip() for s in (ln.strip() for ln in lines) if s.startswith("- ")]


def parse_actor_self(md):
    """从技艺层拆出：tagline（底色）、口味（我对你的了解，合并档）、年表（成长记，累计）。"""
    secs = _sections(md)

    def find(key):
        for k, v in secs.items():
            if key in k:
                return v
        return []

    tagline = ""
    for line in find("我是谁"):
        if "演员" in line and "——" in line:
            after = line.split("——", 1)[1]
            if "而是" in after:
                after = after.split("而是", 1)[1]
            tagline = after.strip().strip("。").lstrip("那个").strip()
            break
    knows = [b for b in _bullets(find("我对你的了解")) if not b.startswith("（")]
    timeline = []
    for b in _bullets(find("成长记")):
        if b.startswith("（"):
            continue
        has_date = len(b) >= 10 and b[4] == "-" and b[7] == "-"
        date = b[:10] if has_date else ""
        rest = (b[10:] if has_date else b).strip()
        if "→" in rest:
            reason, change = rest.split("→", 1)
            timeline.append({"date": date, "reason": reason.strip(), "change": change.strip()})
        else:
            timeline.append({"date": date, "reason": "", "change": rest})
    return tagline, knows, timeline


def _intimacy(score, lang="zh"):
    cur, cur_thr = INTIMACY_LADDER[0]
    nxt, nxt_thr = None, None
    for i, (name, thr) in enumerate(INTIMACY_LADDER):
        if score >= thr:
            cur, cur_thr = name, thr
            if i + 1 < len(INTIMACY_LADDER):
                nxt, nxt_thr = INTIMACY_LADDER[i + 1]
            else:
                nxt, nxt_thr = None, None
    lvl_map = INTIMACY_LEVEL_I18N.get(lang) or INTIMACY_LEVEL_I18N["en"]
    blurb_map = INTIMACY_BLURB_I18N.get(lang) or INTIMACY_BLURB_I18N["en"]

    def loc(name):  # 级名本地化(zh 是 canonical,其他查表;缺表/缺项回落 en/原名)
        return name if lang == "zh" or name is None else lvl_map.get(name, name)
    blurb = (INTIMACY_BLURB if lang == "zh" else blurb_map).get(cur, "")
    if nxt_thr is None:  # 已到顶
        return {"level": loc(cur), "score": score, "next": None, "to_next": 0, "progress": 1.0,
                "blurb": blurb}
    span = nxt_thr - cur_thr
    prog = 0.0 if span <= 0 else max(0.0, min(1.0, (score - cur_thr) / span))
    return {"level": loc(cur), "score": score, "next": loc(nxt), "to_next": nxt_thr - score,
            "progress": round(prog, 3), "blurb": blurb}


def actor_card_data(lang="zh"):
    """演员卡聚合数据（/api/actor_card?lang=）。全部从现有 state 算，无写、无新事件。
    lang 只影响 server 下发的 UI 标签（级名/blurb/name 兜底）；内容层（口味/年表/tagline）
    是墨写的东西，不翻。"""
    prods = _list("productions")
    total_turns, total_words, role_ids, debut = 0, 0, set(), None
    roles_played = {}  # card_id -> 轮数（v1.1 角色名录）
    for p in prods:
        story = p.get("story", [])
        ca = p.get("created_at")
        if ca and (debut is None or ca < debut):
            debut = ca
        cid = p.get("card_id")
        if cid:
            role_ids.add(cid)
        uturns = 0
        for i, m in enumerate(story):
            if m.get("role") == "user":
                uturns += 1
            elif i > 0:  # 排除 story[0] 开场白（first_mes 是卡作者写的，非墨生成）
                total_words += len(m.get("text") or "")
        total_turns += uturns
        if cid:
            roles_played[cid] = roles_played.get(cid, 0) + uturns
    debut_days = 0 if debut is None else max(0, (int(time.time()) - int(debut)) // 86400)
    tagline, knows, timeline = parse_actor_self(actor_self_text())
    intim = _intimacy(total_turns + INTIMACY_W * len(timeline), lang)
    intim["turns"] = total_turns
    intim["log"] = len(timeline)
    cards = {c["id"]: c for c in _list("cards")}
    roles = sorted(({"name": (cards.get(cid) or {}).get("name") or "角色", "turns": t}
                    for cid, t in roles_played.items()), key=lambda r: -r["turns"])
    specs = []
    for cid in role_ids:  # 擅长题材 = 各卡 tags 聚合（v1.1）
        for t in (cards.get(cid) or {}).get("tags", []) or []:
            if t not in specs:
                specs.append(t)
    return {
        # name/tagline 兜底:zh 之外统一 en 写法(加语言时通常不用动——名字/tagline 是内容层)
        "name": "墨" if lang == "zh" else "Mo",
        "tagline": tagline or ("能钻进任何角色里的人"
                               if lang == "zh" else "The actor who can step into any role"),
        "career": {"debut_days": debut_days, "productions": len(prods),
                   "turns": total_turns, "words": total_words, "roles": len(role_ids)},
        "intimacy": intim,
        "knows": knows,
        "timeline": list(reversed(timeline)),  # 最近在前
        "specialties": specs[:8],
        "roles_played": roles,
        "version": liveware_version(),
        "actor_url": (f"https://{_actor_host()}/" if _actor_host() else ""),  # 演员卡活件公网地址
    }


def _actor_host():
    """演员卡活件 app 的域名（第二个活件卡入口）。存 state/actor_host.txt，重启/bringup 不丢；
    env TAVERN_ACTOR_HOST 兜底。为空 = 没注册第二个 app（`/` 一律控制台）。"""
    try:
        with open(os.path.join(STATE, "actor_host.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return os.environ.get("TAVERN_ACTOR_HOST", "").strip()


def load_card(cid):
    return _read(os.path.join(STATE, "cards", cid + ".json"))


def load_worldbook(wid):
    return _read(os.path.join(STATE, "worldbooks", wid + ".json"))


def load_production(pid):
    return _read(os.path.join(STATE, "productions", pid + ".json"))


def save_production(p):
    _write(os.path.join(STATE, "productions", p["id"] + ".json"), p)


def _list(sub):
    d = os.path.join(STATE, sub)
    out = []
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            out.append(_read(os.path.join(d, fn)))
    return out


def _msg(role, text):
    return {"id": secrets.token_hex(4), "role": role, "text": text,
            "ts": int(time.time()), "alts": [text], "active_alt": 0}


# ---------- event handlers ----------
def _store_card(card, source=""):
    # source = 导入渠道(出处):chub=导入真卡 / agent=原创。creator(卡作者)仍透传,
    # 信息面板优先显 creator,无 creator 才回落 source(Task 2 角色卡出处)。
    if source:
        card["source"] = source
    _write(os.path.join(STATE, "cards", card["id"] + ".json"), card)
    # 卡内嵌世界书 → 落成独立 worldbook
    if card.get("character_book"):
        wb = {"id": "wb_" + card["id"], "name": card["character_book"].get("name") or card["name"],
              "entries": card["character_book"].get("entries", [])}
        _write(os.path.join(STATE, "worldbooks", wb["id"] + ".json"), wb)
    return {"card": card}


def ev_import_card(ev):
    # PNG 路径：吃一张 V2/V3 角色卡 PNG（base64）。真实卡走这条，编码天然正确。出处=chub。
    return _store_card(card_import.import_card_b64(ev["png_base64"]), "chub")


def ev_import_card_json(ev):
    # JSON 路径：吃一份卡 JSON（V1/V2/V3 形态，带 data 包或裸 obj 都行）。
    # 给 agent「原创/自造」角色卡用——不手搓 PNG，绕开 btoa(UTF-8) 把中文搞乱码的坑。出处=agent。
    return _store_card(card_import.normalize_card(ev["card"]), "agent")


def ev_import_worldbook(ev):
    wb = ev["worldbook"]
    wb.setdefault("id", "wb_" + secrets.token_hex(4))
    _write(os.path.join(STATE, "worldbooks", wb["id"] + ".json"), wb)
    return {"worldbook": wb}


def ev_attach_worldbook(ev):
    # 把一本独立世界书挂到现有剧组（卡内嵌的世界书在 create_production 时已自动挂）。
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    wid = ev["worldbook_id"]
    if not load_worldbook(wid):
        raise ValueError("worldbook not found: " + wid)
    if wid not in p["worldbook_ids"]:
        p["worldbook_ids"].append(wid)
        save_production(p)
    return {"production": p}


def ev_create_production(ev):
    card = load_card(ev["card_id"])
    if not card:
        raise ValueError("card not found: " + ev["card_id"])
    pid = "prod_" + secrets.token_hex(4)
    wbs = ev.get("worldbook_ids")
    if wbs is None and card.get("character_book"):
        wbs = ["wb_" + card["id"]]
    greeting = ev.get("first_mes") or card.get("first_mes") or ""
    p = {"id": pid, "name": ev.get("name") or card.get("name"),
         "card_id": card["id"], "worldbook_ids": wbs or [],
         "persona_id": ev.get("persona_id"), "created_at": int(time.time()),
         "status": "active", "story": [_msg("char", greeting)] if greeting else []}
    save_production(p)
    _set_active(pid)
    return {"production": p}


# Q_C：切走剧组时后台自动复盘（达阈值才做），不阻塞切换、不靠墨自觉（结构性 > 软性）。
AUTO_REFLECT_MIN = int(os.environ.get("ACTOR_AUTO_REFLECT_MIN", "4"))      # 至少这么多轮才值得复盘
AUTO_REFLECT_EVERY = int(os.environ.get("ACTOR_AUTO_REFLECT_EVERY", "6"))  # 距上次复盘再攒这么多轮


def _maybe_auto_reflect(pid):
    p = load_production(pid)
    if not p:
        return
    uturns = sum(1 for m in p.get("story", []) if m.get("role") == "user")
    done = p.get("reflected_at_turns", 0)
    if uturns < AUTO_REFLECT_MIN or uturns - done < AUTO_REFLECT_EVERY:
        return
    try:
        _reflect_production(p)
        p2 = load_production(pid) or p
        p2["reflected_at_turns"] = uturns
        save_production(p2)
    except Exception:
        pass  # 后台尽力而为，失败不影响任何前台操作


def ev_switch_loadout(ev):
    prev = _get_state().get("active_production_id")
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    _set_active(p["id"])
    if prev and prev != p["id"]:  # Q_C：离开一场戏 = 复盘它的自然时机（后台线程，不阻塞切换）
        threading.Thread(target=_maybe_auto_reflect, args=(prev,), daemon=True).start()
    return {"production": p}


def ev_delete_production(ev):
    # 删一个剧组(连同它的故事线 story)——不可逆,前端走二次确认(Task 4)。
    # 删的若是当前活跃剧组,active 切到剩下的第一个、没有则清空。
    pid = ev["production_id"]
    if not load_production(pid):
        raise ValueError("production not found")
    path = os.path.join(STATE, "productions", pid + ".json")
    try:
        os.remove(path)
    except OSError:
        pass
    new_active = _get_state().get("active_production_id")
    if new_active == pid:
        remaining = [x for x in _list("productions") if x]
        new_active = remaining[0]["id"] if remaining else None
        _set_active(new_active)
    return {"deleted": pid, "active": new_active}


def _loadout(p):
    """一回合演出要喂的料:卡 + 世界书 + 人设 + 作者注释(本剧组的临场导演提示)。"""
    card = load_card(p["card_id"])
    wbs = [load_worldbook(w) for w in p.get("worldbook_ids", [])]
    wbs = [w for w in wbs if w]
    persona = _read(os.path.join(STATE, "persona.json"), {})
    note = p.get("author_note", "")
    return card, wbs, persona, note


def _perform_into(p):
    card, wbs, persona, note = _loadout(p)
    return actor.perform(card, actor_self_text(), wbs, persona, p["story"], note,
                         model=_active_model())  # 用户自配大模型;None=墨自带


def ev_send_message(ev):
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    p["story"].append(_msg("user", ev["text"]))
    reply = _perform_into(p)
    m = _msg("char", reply)
    p["story"].append(m)
    save_production(p)
    return {"reply": reply, "message": m, "production_id": p["id"]}


def ev_append_turn(ev):
    # 早停专用:把「用户这一句 + 已流式生成的半截回复」一起落盘。
    # 流式中途客户端断开时 server 不落盘(见 _stream_send),所以早停由前端拿着已收的
    # 增量调这条补存,既保住半截、又不和正常流式路径重复落盘。
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    p["story"].append(_msg("user", ev.get("user_text", "")))
    m = _msg("char", (ev.get("char_text") or "").strip())
    p["story"].append(m)
    save_production(p)
    return {"message": m, "production_id": p["id"]}


def ev_regenerate(ev):
    p = load_production(ev["production_id"])
    if not p or not p["story"]:
        raise ValueError("nothing to regenerate")
    # 砍掉最后一条 char，重演（保留为 alt）
    last = p["story"][-1]
    if last["role"] != "char":
        raise ValueError("last message is not the actor's")
    trimmed = p["story"][:-1]
    saved_story = p["story"]
    p["story"] = trimmed
    reply = _perform_into(p)
    last["alts"].append(reply)
    last["active_alt"] = len(last["alts"]) - 1
    last["text"] = reply
    p["story"] = saved_story
    save_production(p)
    return {"message": last, "production_id": p["id"]}


def ev_swipe(ev):
    # 在已有备选回复(alts)间切换 active_alt(非破坏性,dir ∈ -1/+1,边界夹住)。
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    for m in p["story"]:
        if m["id"] == ev["message_id"]:
            alts = m.get("alts") or [m.get("text", "")]
            cur = m.get("active_alt", 0)
            nxt = max(0, min(len(alts) - 1, cur + int(ev.get("dir", 0))))
            m["active_alt"] = nxt
            m["text"] = alts[nxt]
            save_production(p)
            return {"message": m}
    raise ValueError("message not found")


def ev_edit_message(ev):
    p = load_production(ev["production_id"])
    for m in p["story"]:
        if m["id"] == ev["message_id"]:
            m["text"] = ev["text"]
            m["alts"][m.get("active_alt", 0)] = ev["text"]
            save_production(p)
            return {"message": m}
    raise ValueError("message not found")


# ---------- Q_B：合并写入 + 生涯年表审计 ----------
# 越演越懂你的引擎：learn/reflect 不再尾部堆流水账,而是①把新学到的**合并进「我对你的了解」**
# (有界、去重、精化——actor.merge_knows)②在「成长记」记一行审计(生涯年表的资产)。
# 「我对你的了解」注入每场生成 + 展示演员卡口味栏;「成长记」只上演员卡年表、不进 prompt(Q_B 瘦身)。
KNOWS_PLACEHOLDER = "- （还不了解你。等我们演几场，我会把你的口味记到这里。）"


def _write_actor_self(md):
    rt = os.path.join(STATE, "actor_self.md")
    tmp = rt + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(md if md.endswith("\n") else md + "\n")
    os.replace(tmp, rt)


def _replace_section(md, key, body_lines):
    """把 md 中标题含 key 的一级段落正文替换为 body_lines（保留标题 + 前后空行）。"""
    lines, out, i, n, done = md.splitlines(), [], 0, len(md.splitlines()), False
    while i < n:
        line = lines[i]
        if not done and line.startswith("# ") and key in line:
            out += [line, ""] + list(body_lines)
            i += 1
            while i < n and not lines[i].startswith("# "):
                i += 1
            if i < n:
                out.append("")
            done = True
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _merge_into_knows(addition):
    """把新学到的并进「我对你的了解」段（合并、去重、有界），写回，返回合并后清单。"""
    md = actor_self_text()
    merged = actor.merge_knows(parse_actor_self(md)[1], addition)
    body = ["- " + k for k in merged] if merged else [KNOWS_PLACEHOLDER]
    _write_actor_self(_replace_section(md, "我对你的了解", body))
    return merged


def _append_growth(meta, change, ts=None):
    """在「成长记」尾追加**一行**生涯年表审计（成长记是最后一段，追加到尾即落在它下面）。
    change 可能是多行（reflect 蒸馏出多条）——折成一行（`；` 连、去 bullet），否则年表会裂成多条、掉日期。"""
    stamp = time.strftime("%Y-%m-%d", time.localtime(ts or time.time()))
    change = "；".join(s.strip().lstrip("-•").strip()
                       for s in str(change).splitlines() if s.strip())
    meta = " ".join(str(meta).split())
    line = f"- {stamp} {meta} → {change}"
    _write_actor_self(actor_self_text().rstrip() + "\n" + line + "\n")
    return line


def ev_actor_grow(ev):
    """learn：把对用户的了解/演法调整**合并进「我对你的了解」** + 记一笔生涯年表（带人话理由）。Q_B。"""
    change = ev.get("change", "")
    merged = _merge_into_knows(change)
    audit = _append_growth(ev.get("reason", "") or "(无理由)", change, ev.get("ts"))
    return {"ok": True, "knows": merged, "appended": audit}


def _reflect_production(p):
    """复盘一场戏 → 蒸馏偏好 → **合并进「我对你的了解」** + 记生涯年表。explicit + auto 共用。"""
    story = p.get("story", [])
    if sum(1 for m in story if m.get("role") == "user") < 2:
        return {"learned": None, "reason": "戏太短，没什么可学的"}
    card = load_card(p["card_id"]) or {}
    learned = actor.reflect_on_play(card, story, actor_self_text(), model=_active_model())
    if not learned:
        return {"learned": None, "reason": "这场没看出明显偏好"}
    merged = _merge_into_knows(learned)
    _append_growth(f"（复盘「{p.get('name', '')}」）", learned)
    return {"learned": learned, "knows": merged, "production": p.get("name")}


def ev_reflect(ev):
    """复盘一场戏（显式触发）→ 蒸馏 + 合并进技艺层。「越演越懂你」的结构化触发（不靠 agent 临场）。"""
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    return _reflect_production(p)


def ev_set_persona(ev):
    persona = {"name": ev.get("name", "我"), "description": ev.get("description", "")}
    _write(os.path.join(STATE, "persona.json"), persona)
    return {"persona": persona}


def ev_set_note(ev):
    """设/清本剧组的作者注释(导演提示)——临场语气/格式杠杆,注入贴近生成点。
    结构化的「跟搭子说一句就长期生效」:agent 识别『回复短点/别用现代词』→ set_note。
    设计 canon:不暴露 UI 旋钮,由对话/agent 设。空串=清除。"""
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    p["author_note"] = (ev.get("note") or "").strip()
    save_production(p)
    return {"production_id": p["id"], "author_note": p["author_note"]}


# ---------- 大模型配置（docs/design/model-config.md）----------
# 用户自配的大模型（OpenAI-compatible 一种协议）。添加只走「对墨说」→ CLI → 这里的 event；
# reader 界面只做管理（选中/删除）+ 教育。key 只落 server 端 state 文件（0600），
# 任何读端点一律脱敏——bridge「creds 只在 server 端，页面永不见」原则的延伸。
MODELS_PATH = os.path.join(STATE, "model_configs.json")


def _models_state():
    return _read(MODELS_PATH, {"configs": [], "active": "builtin"})


def _save_models(s):
    _write(MODELS_PATH, s)
    try:
        os.chmod(MODELS_PATH, 0o600)  # 存明文 key,别让同机其他用户读
    except OSError:
        pass


def _active_model():
    """当前生效的 override {base,key,model}；None = 墨自带（env 路径，actor 模块常量）。
    每回合现读文件（_actor_host 同款范式）：CLI/事件写入即生效、重启不丢。"""
    s = _models_state()
    aid = s.get("active") or "builtin"
    if aid == "builtin":
        return None
    for c in s["configs"]:
        if c["id"] == aid:
            return {"base": c["base"], "key": c["key"], "model": c["model"]}
    return None  # active 悬空(配置已删) → 回落墨自带


def _mask_key(k):
    return ("**" + k[-4:]) if len(k or "") >= 8 else "**"


def _public_models():
    """脱敏配置列表（reader / CLI list 用）。墨自带恒在首位、不可删。"""
    s = _models_state()
    builtin = {"id": "builtin", "name": "墨自带", "model": actor.MODEL_NAME,
               "builtin": True, "key_set": bool(actor.MODEL_KEY)}
    configs = [builtin] + [{"id": c["id"], "name": c["name"], "model": c["model"],
                            "base": c["base"], "key_masked": _mask_key(c.get("key")),
                            "added_at": c.get("added_at")} for c in s["configs"]]
    aid = s.get("active") or "builtin"
    if aid != "builtin" and not any(c["id"] == aid for c in s["configs"]):
        aid = "builtin"  # 悬空同 _active_model 的回落语义
    return {"configs": configs, "active": aid}


def _ping_or_raise(ov):
    """实测一份配置，失败转成人话错误（CLI/reader 直接给用户看）。"""
    try:
        return actor.ping(ov)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        hint = {401: "（key 无效或没权限）", 404: "（base_url 或 model 名不对）",
                429: "（限流/欠费）"}.get(e.code, "")
        raise ValueError(f"实测失败 HTTP {e.code}{hint}：{body}")
    except Exception as e:  # noqa: BLE001 — DNS/超时/拒连等,统一转人话
        raise ValueError(f"实测失败：{e}")


def ev_model_add(ev):
    """加一份用户自配模型：先实测（1 次极小请求），通了才落盘并自动切换。
    同名 = 更新（墨「再配一次」= 换 key/model，id 不变）。"""
    name = (ev.get("name") or "").strip()
    base = (ev.get("base") or "").strip().rstrip("/")
    model_name = (ev.get("model") or "").strip()
    key = (ev.get("key") or "").strip()
    if not (name and base and model_name and key):
        raise ValueError("缺参数：name / base / model / key 都要")
    if name == "墨自带":
        raise ValueError("这个名字留给内置配置了，换一个")
    ms = _ping_or_raise({"base": base, "key": key, "model": model_name})
    s = _models_state()
    cfg = next((c for c in s["configs"] if c["name"] == name), None)
    if cfg:
        cfg.update({"base": base, "model": model_name, "key": key})
    else:
        cfg = {"id": "m_" + secrets.token_hex(3), "name": name, "base": base,
               "model": model_name, "key": key, "added_at": int(time.time())}
        s["configs"].append(cfg)
    s["active"] = cfg["id"]
    _save_models(s)
    return {"config": {"id": cfg["id"], "name": name, "model": model_name,
                       "key_masked": _mask_key(key)},
            "active": cfg["id"], "latency_ms": ms}


def _find_config(s, ref):
    """按 id 或名字找配置（CLI 让墨用名字，reader 用 id）。"""
    return next((c for c in s["configs"] if c["id"] == ref or c["name"] == ref), None)


def ev_model_use(ev):
    ref = ev.get("id") or ""
    s = _models_state()
    if ref in ("builtin", "墨自带"):
        s["active"] = "builtin"
        _save_models(s)
        return {"active": "builtin", "name": "墨自带"}
    cfg = _find_config(s, ref)
    if not cfg:
        raise ValueError("没有这份配置：%s" % ref)
    s["active"] = cfg["id"]
    _save_models(s)
    return {"active": cfg["id"], "name": cfg["name"]}


def ev_model_delete(ev):
    ref = ev.get("id") or ""
    if ref in ("builtin", "墨自带"):
        raise ValueError("墨自带是内置配置，删不得")
    s = _models_state()
    cfg = _find_config(s, ref)
    if not cfg:
        raise ValueError("没有这份配置：%s" % ref)
    s["configs"] = [c for c in s["configs"] if c["id"] != cfg["id"]]
    if s.get("active") == cfg["id"]:
        s["active"] = "builtin"  # 删掉在用的 → 回落墨自带
    _save_models(s)
    return {"deleted": cfg["id"], "name": cfg["name"], "active": s["active"]}


def ev_model_test(ev):
    """实测某份已存配置（或 builtin）。返回耗时；失败走统一人话错误。"""
    ref = ev.get("id") or "builtin"
    if ref in ("builtin", "墨自带"):
        ov = None
    else:
        s = _models_state()
        cfg = _find_config(s, ref)
        if not cfg:
            raise ValueError("没有这份配置：%s" % ref)
        ov = {"base": cfg["base"], "key": cfg["key"], "model": cfg["model"]}
    ms = _ping_or_raise(ov)
    return {"latency_ms": ms, **actor.model_info(ov)}


EVENTS = {
    "import_card": ev_import_card, "import_card_json": ev_import_card_json,
    "import_worldbook": ev_import_worldbook, "attach_worldbook": ev_attach_worldbook,
    "create_production": ev_create_production, "switch_loadout": ev_switch_loadout,
    "delete_production": ev_delete_production,
    "send_message": ev_send_message, "append_turn": ev_append_turn,
    "regenerate": ev_regenerate,
    "swipe": ev_swipe, "edit_message": ev_edit_message, "actor_grow": ev_actor_grow,
    "reflect": ev_reflect, "set_persona": ev_set_persona, "set_note": ev_set_note,
    "model_add": ev_model_add, "model_use": ev_model_use,
    "model_delete": ev_model_delete, "model_test": ev_model_test,
}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", CONTENT_TYPES[".json"])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path):
        if not os.path.isfile(path):
            return self._json(404, {"error": "not found"})
        ext = os.path.splitext(path)[1]
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        # reader 是活件页面、随 agent 迭代频繁更新——禁缓存,否则 WKWebView/WebView2 可能
        # serve 旧 app.js,改动不生效(反馈 2026-06-30「还是不行」的头号嫌疑)。
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def _serve_html(self, name, assets):
        # 注入版本化资源引用破 relay 缓存:clawling relay/CDN 把 .js/.css 强制缓存成
        # `public, max-age=2592000, immutable`(30天,覆盖源站 no-store)→ 改动不生效。
        # html 自身是 no-store(relay 透传)永远新,所以给资源 URL 挂 ?v=<token>,
        # token 取资源 mtime → 每次部署自动变 → 新 URL = relay 缓存未命中 = 取到新文件。
        try:
            with open(os.path.join(READER, name), encoding="utf-8") as f:
                html = f.read()
        except OSError:
            return self._json(404, {"error": "not found"})
        token = 0
        for fn in (name,) + tuple(assets):
            try:
                token ^= int(os.path.getmtime(os.path.join(READER, fn)))
            except OSError:
                pass
        v = format(token & 0xFFFFFF, "x")
        for a in assets:
            html = html.replace(a + '"', a + "?v=" + v + '"')
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES[".html"])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            # model_info 传 active override → health 反映当前实际生效的模型
            return self._json(200, {"ok": True, "dry_run": False, **actor.model_info(_active_model())})
        if path == "/api/models":
            # 大模型配置列表(脱敏,key 永不出 server)——reader 管理面 + CLI model list 共用
            return self._json(200, _public_models())
        if path == "/api/cards":
            return self._json(200, {"cards": _list("cards")})
        if path == "/api/worldbooks":
            return self._json(200, {"worldbooks": _list("worldbooks")})
        if path == "/api/productions":
            return self._json(200, {"productions": _list("productions"),
                                    "active": _get_state().get("active_production_id")})
        if path == "/api/actor":
            # 演员技艺层(actor_self.md,会随演出/复盘积累的富提示词) + 活件版本(应用发版号)
            # + 墨的 ClawChat 身份(「找墨复盘」深链用;拿不到为空,reader 隐入口)。
            return self._json(200, {"actor_self": actor_self_text(), "version": liveware_version(),
                                    "agent_user_id": agent_user_id()})
        if path == "/api/actor_card":
            # 演员卡聚合(生涯数值/亲密度/口味/年表)——纯聚合读,见 docs/design/actor-card.md。
            # ?lang= 只换 UI 标签(级名/blurb);非 zh 一律走 en 表(回落链对齐 reader)。
            q = parse_qs(urlparse(self.path).query)
            lang = (q.get("lang", ["zh"])[0] or "zh")[:2].lower()
            return self._json(200, actor_card_data(lang))
        # static reader（*.html 走版本化注入,破 relay 的 immutable 缓存）
        rel = path.lstrip("/") or "index.html"
        if rel == "index.html":
            # 一台 server 服务两个活件 app（同 :8799，靠 tunnel 透传的 X-Forwarded-Host 分流）：
            # 控制台 app 的 / → index；演员卡 app（第二个活件卡入口）的 / → actor.html。
            fwd = self.headers.get("X-Forwarded-Host", "") or self.headers.get("X-Original-Host", "")
            ah = _actor_host()
            if ah and ah in fwd:
                return self._serve_html("actor.html", ("console.css", "i18n.js", "actor.js"))
            return self._serve_html("index.html", ("console.css", "i18n.js", "bridge.js", "app.js"))
        if path == "/actor" or rel == "actor.html":  # 直达路径也保留（任一 app 域名 + /actor 都能开）
            return self._serve_html("actor.html", ("console.css", "i18n.js", "actor.js"))
        return self._file(os.path.join(READER, rel))

    def _read_body(self):
        # Content-Length path (direct calls + most proxies).
        cl = self.headers.get("Content-Length")
        if cl is not None:
            try:
                return self.rfile.read(int(cl))
            except Exception:
                return b""
        # The liveware gRPC relay re-chunks POST bodies and drops Content-Length,
        # so a Content-Length-only read returns 0 bytes (type=None). Read the
        # chunked stream when that header is present.
        te = (self.headers.get("Transfer-Encoding") or "").lower()
        if "chunked" in te:
            chunks = []
            while True:
                size_line = self.rfile.readline().strip()
                if not size_line:
                    break
                try:
                    size = int(size_line.split(b";")[0], 16)
                except ValueError:
                    break
                if size == 0:
                    self.rfile.readline()  # consume trailing CRLF
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.readline()  # CRLF after each chunk
            return b"".join(chunks)
        return b""

    def _sse(self, obj):
        """写一条 SSE 事件并 flush。客户端断开(早停/关页)返回 False → 停止生成。"""
        line = "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"
        try:
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False

    def _stream_send(self):
        """流式 send_message:逐 token 推 SSE,末尾推 {done, message}。
        只在成功生成后落盘——客户端中途断开则不残留(reader 回退阻塞式时不会重复)。"""
        try:
            ev = json.loads(self._read_body() or b"{}")
        except Exception:
            return self._json(400, {"error": "bad json"})
        if ev.get("type") != "send_message":
            return self._json(400, {"error": "stream only supports send_message"})
        p = load_production(ev.get("production_id"))
        if not p:
            return self._json(404, {"error": "production not found"})
        p["story"].append(_msg("user", ev.get("text", "")))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")  # 防中间层缓冲(尽力而为)
        self.end_headers()
        card, wbs, persona, note = _loadout(p)
        chunks = []
        try:
            for delta in actor.perform_stream(card, actor_self_text(), wbs, persona, p["story"], note,
                                              model=_active_model()):
                chunks.append(delta)
                if not self._sse({"delta": delta}):
                    return  # 客户端断开 → 不落盘
        except Exception as e:
            self._sse({"error": str(e)})
            return
        m = _msg("char", "".join(chunks).strip())
        p["story"].append(m)
        save_production(p)
        self._sse({"done": True, "message": m, "production_id": p["id"]})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/stream":
            return self._stream_send()
        if path != "/api/event":
            return self._json(404, {"error": "unknown endpoint"})
        try:
            ev = json.loads(self._read_body() or b"{}")
        except Exception:
            return self._json(400, {"error": "bad json"})
        fn = EVENTS.get(ev.get("type"))
        if not fn:
            return self._json(400, {"error": "unknown event type: %s" % ev.get("type")})
        try:
            return self._json(200, {"ok": True, **fn(ev)})
        except Exception as e:
            return self._json(500, {"ok": False, "error": str(e)})


def main():
    port = 8799
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    elif os.environ.get("TAVERN_PORT"):
        port = int(os.environ["TAVERN_PORT"])
    host = os.environ.get("TAVERN_HOST", "127.0.0.1")
    print("酒馆演员运行时 → http://%s:%d  (model=%s, key=%s)" % (
        host, port, actor.MODEL_NAME, "set" if actor.MODEL_KEY else "MISSING"))
    ThreadingHTTPServer((host, port), H).serve_forever()


if __name__ == "__main__":
    main()
