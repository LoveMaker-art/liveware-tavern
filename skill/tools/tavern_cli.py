#!/usr/bin/env python3
"""tavern_cli — 墨（酒馆 agent）的「找卡 + 导卡」工具。

给 agent 一条干净路径，替代「在浏览器手搓 PNG + 跑 JS 怼 /api/event」那套硬凑
（会撞作用域错、btoa(UTF-8) 把中文搞乱码、世界书 Promise 不 resolve）。

卡来源 = Chub.ai（角色卡事实标准库，6 万+ 卡，公开 API、免鉴权）。**Chub 不可达时
（墙内无代理 / 网络受限）自动降级到随仓打包的 starter 真卡**——离线也能建剧组，绝不回退
到手搓 PNG。导入直打本地控制台同源事件 API（默认 http://127.0.0.1:8799，env TAVERN_CONSOLE 覆盖）。

命令：
  search <query> [--n N] [--nsfw]          搜 Chub → 候选列表（名 · fullPath · ⭐ · 标签）；Chub 连不上→列 starter
  add <fullPath|Chub链接> [--name NAME]     下载 Chub 真卡 → 导入 → 建剧组（**优先用这条**）；连不上→提示 starter
  starter [<序号|名字>] [--name NAME]        列出/导入随仓内置 starter 真卡（离线兜底 + 写原创卡的样板）
  add-original <jsonfile|->                 原创/自造卡 JSON → 导入 → 建剧组（仅在明确「原创」时用）
  add-worldbook <jsonfile|-> [--production PID]   世界书 JSON → 导入（可挂到现有剧组）
  note <production> "<提示>"                设/清剧组导演提示（临场语气/格式杠杆，空串清除）
  list                                     列出当前剧组 / 卡 / 世界书

纯 stdlib（urllib），不依赖控制台代码——它只发 HTTP。
"""
import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request

CONSOLE = os.environ.get("TAVERN_CONSOLE", "http://127.0.0.1:8799").rstrip("/")
CHUB_SEARCH = "https://api.chub.ai/search"
CHUB_CARD = "https://avatars.charhub.io/avatars/{full_path}/chara_card_v2.png"
UA = "tavern-cli/1.0"
# 随仓打包的 starter 真卡（tavern/fixtures/starter/）——Chub 不可达时的离线兜底。
STARTER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures", "starter")


class ChubUnreachable(Exception):
    """Chub 网络不可达（DNS/超时/连接失败）——触发 starter 兜底。区别于 HTTP 4xx（可达但请求错）。"""


def _die(msg):
    print("错误：" + msg, file=sys.stderr)
    sys.exit(1)


def _http(url, data=None, headers=None, timeout=30):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        _die(f"HTTP {e.code} {url}\n{body}")
    except Exception as e:  # noqa: BLE001
        _die(f"请求失败 {url}: {e}")


def _event(ev):
    """POST 一个控制台事件，返回解析后的 dict。
    server 对事件异常回 HTTP 500 + {ok:false,error:人话}——这里接住 body 只报人话
    （别走 _http 的 HTTPError 分支打「HTTP 500 + 原始 JSON」，墨要把错误读给用户）。"""
    body = json.dumps(ev, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(CONSOLE + "/api/event", data=body,
                                 headers={"User-Agent": UA, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
    except Exception as e:  # noqa: BLE001
        _die(f"请求失败 {CONSOLE}/api/event: {e}")
    try:
        res = json.loads(raw)
    except Exception:
        _die("控制台返回不是 JSON：" + raw.decode("utf-8", "replace")[:200])
    if isinstance(res, dict) and (res.get("error") or res.get("ok") is False):
        _die("控制台报错：" + str(res.get("error")))
    return res


def _read_json_arg(arg):
    """从文件或 stdin('-') 读 JSON。"""
    text = sys.stdin.read() if arg == "-" else open(arg, encoding="utf-8").read()
    try:
        return json.loads(text)
    except Exception as e:  # noqa: BLE001
        _die(f"JSON 解析失败：{e}")


def _chub_get(url, timeout=30):
    """打 Chub。网络不可达 → ChubUnreachable（降级 starter）；HTTP 4xx/5xx → 原样抛给调用方按语义处理。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError:
        raise  # 可达但请求错（如 404 fullPath 写错）——不是「墙内连不上」，别降级
    except Exception as e:  # DNS 失败 / 超时 / 连接被拒 = 不可达
        raise ChubUnreachable(str(e))


def _parse_full_path(arg):
    """接受裸 fullPath，或用户直贴的 Chub / CharacterHub 链接，抽出 `<owner>/<slug>`。"""
    s = arg.strip()
    for marker in ("/characters/", "/character/"):
        if marker in s:
            s = s.split(marker, 1)[1]
            break
    else:
        if "/avatars/" in s:  # 直贴下载 URL 也兜一下
            s = s.split("/avatars/", 1)[1].rsplit("/chara_card", 1)[0]
    return s.split("?", 1)[0].split("#", 1)[0].strip().strip("/")


def _load_starter_index():
    path = os.path.join(STARTER_DIR, "index.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("cards") or []
    except Exception:  # noqa: BLE001
        return []


def _print_starter_list(cards):
    print(f"内置 starter 真卡 {len(cards)} 张（随仓打包、离线可用、SFW/跨题材）：\n")
    for i, c in enumerate(cards, 1):
        wb = " · 世界书" if c.get("worldbook") else ""
        print(f"[{i}] {c.get('name', '?')}  ·  {c.get('genre', '')}{wb}")
        if c.get("blurb"):
            print(f"    {c['blurb']}")
    print("\n→ 建剧组：tavern_cli.py starter <序号或名字>")


def _degrade_to_starter(reason):
    """Chub 不可达时的降级出口：报清楚原因 + 列 starter 卡。绝不回退到手搓 PNG。"""
    print(f"⚠️  {reason}", file=sys.stderr)
    cards = _load_starter_index()
    if not cards:
        print("（也没有内置 starter 卡；检查网络 / 代理后重试。）", file=sys.stderr)
        return
    print("——先用内置 starter 真卡玩（离线也能建剧组），或配好代理再回 Chub 拿全库：\n")
    _print_starter_list(cards)


# ---------- commands ----------
def cmd_search(a):
    q = urllib.parse.urlencode({
        "search": a.query, "first": a.n,
        "nsfw": "true" if a.nsfw else "false",
        "sort": "star_count", "asc": "false",
    })
    try:
        raw = _chub_get(f"{CHUB_SEARCH}?{q}", timeout=30)
    except ChubUnreachable as e:
        _degrade_to_starter(f"Chub 搜索连不上（{e}）")
        return
    except urllib.error.HTTPError as e:
        _die(f"Chub 搜索 HTTP {e.code}（接口可能变动）；可先用 `starter` 内置卡。")
    nodes = (json.loads(raw).get("data") or {}).get("nodes") or []
    if not nodes:
        print("（没搜到，换个关键词试试——英文名通常命中率更高）")
        return
    print(f"Chub 命中 {len(nodes)} 张（按星数）：\n")
    for i, n in enumerate(nodes, 1):
        topics = ", ".join((n.get("topics") or [])[:6])
        desc = (n.get("description") or "").replace("\n", " ")[:90]
        print(f"[{i}] {n.get('name','?')}  ·  ⭐{n.get('starCount',0)}")
        print(f"    fullPath: {n.get('fullPath','?')}")
        if topics:
            print(f"    标签: {topics}")
        if desc:
            print(f"    简介: {desc}")
        print()
    print("→ 选定后：tavern_cli.py add <fullPath>")


def _create_production(card, name=None):
    p = _event({"type": "create_production", "card_id": card["id"],
                "name": name or card.get("name")})["production"]
    wb = " + 世界书" if card.get("character_book") else ""
    print(f"✅ 已建剧组「{p['name']}」（{p['id']}）{wb}")
    print(f"   角色卡：{card.get('name')}（{card['id']}）")
    if card.get("first_mes"):
        print(f"   开场白：{card['first_mes'][:120]}")
    print(f"   控制台：{CONSOLE}/  （剧组列表里点它即可开演）")
    return p


def cmd_add(a):
    fp = _parse_full_path(a.full_path)  # 裸 fullPath 或用户直贴的 Chub 链接都吃
    url = CHUB_CARD.format(full_path=urllib.parse.quote(fp))
    print(f"↓ 从 Chub 下载真卡：{fp}")
    try:
        png = _chub_get(url, timeout=60)
    except ChubUnreachable as e:
        _degrade_to_starter(f"Chub 下载连不上（{e}）")
        return
    except urllib.error.HTTPError as e:
        _die(f"HTTP {e.code}：这张卡在 Chub 取不到（fullPath 可能写错，或该卡没有公开的 "
             f"chara_card_v2.png）。\n先 `search` 确认 fullPath，或 `starter` 用内置卡。")
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        _die("下载的不是 PNG（fullPath 可能写错）。用 `search` 拿准确 fullPath，或 `starter` 用内置卡。")
    card = _event({"type": "import_card",
                   "png_base64": base64.b64encode(png).decode("ascii")})["card"]
    _create_production(card, a.name)


def cmd_starter(a):
    cards = _load_starter_index()
    if not cards:
        _die("没有内置 starter 卡（fixtures/starter/index.json 缺失或损坏）。")
    if not a.which:
        _print_starter_list(cards)
        return
    entry = _resolve_starter(cards, a.which)
    if not entry:
        _die(f"没找到 starter 卡「{a.which}」——`starter` 不带参数看列表（可用序号或名字片段）。")
    path = os.path.join(STARTER_DIR, entry["file"])
    if not os.path.exists(path):
        _die(f"starter 卡文件缺失：{path}")
    with open(path, "rb") as f:
        png = f.read()
    print(f"↓ 导入内置 starter 卡：{entry['name']}（{entry.get('genre', '')}）")
    card = _event({"type": "import_card",
                   "png_base64": base64.b64encode(png).decode("ascii")})["card"]
    _create_production(card, a.name)


def _resolve_starter(cards, which):
    w = which.strip()
    if w.isdigit():
        i = int(w) - 1
        return cards[i] if 0 <= i < len(cards) else None
    wl = w.lower()
    for c in cards:
        if wl in c.get("name", "").lower() or wl in c.get("file", "").lower():
            return c
    return None


def cmd_add_original(a):
    card_obj = _read_json_arg(a.json)
    card = _event({"type": "import_card_json", "card": card_obj})["card"]
    print("（原创卡，已导入）")
    _create_production(card, a.name)


def cmd_add_worldbook(a):
    wb_obj = _read_json_arg(a.json)
    wb = _event({"type": "import_worldbook", "worldbook": wb_obj})["worldbook"]
    print(f"✅ 已导入世界书「{wb.get('name','?')}」（{wb['id']}，{len(wb.get('entries',[]))} 条）")
    if a.production:
        _event({"type": "attach_worldbook", "production_id": a.production,
                "worldbook_id": wb["id"]})
        print(f"   已挂到剧组 {a.production}")


def cmd_recall(a):
    # 读某个剧组在控制台里实际演了什么（墨在 ClawChat 里看不到 production.story，
    # 这是它唯一的「读酒馆对话」入口——别再说「我看不到酒馆里聊了什么」）。
    prods = _get_productions()
    q = a.production
    matches = [p for p in prods if p.get("id") == q or q in (p.get("name") or "")]
    if not matches:
        _die(f"没找到剧组「{q}」——先 `list` 看有哪些。")
    p = matches[0]
    story = p.get("story", [])
    cards = {c["id"]: c for c in json.loads(_http(CONSOLE + "/api/cards", timeout=15)).get("cards", [])}
    cname = (cards.get(p.get("card_id")) or {}).get("name") or "角色"
    print(f"=== 剧组「{p.get('name')}」（{p['id']}）· 角色 {cname} · 共 {len(story)} 条 ===")
    shown = story[-a.last:] if a.last and len(story) > a.last else story
    if len(shown) < len(story):
        print(f"（只显示最后 {len(shown)} 条，共 {len(story)}）\n")
    for m in shown:
        who = "你" if m.get("role") == "user" else cname
        print(f"{who}：{m.get('text', '')}\n")


def cmd_learn(a):
    # 把对用户的了解 / 演法调整，沉淀进技艺层 actor_self.md（跨剧组共享，
    # actor.py 会把它注入每一场戏的 prompt——所以这是「越演越懂你」的载体，
    # 区别于 Hermes 自带的 user-profile 记忆：那层喂不到控制台生成）。
    res = _event({"type": "actor_grow", "change": a.change, "reason": a.reason or ""})
    print("✅ 已记进技艺层:", res.get("appended", "(已写)"))


def cmd_reflect(a):
    # 复盘一场戏 → 服务端模型蒸馏「对用户的 RP 偏好」→ 写进技艺层（不靠你临场总结）。
    prods = _get_productions()
    q = a.production
    matches = [p for p in prods if p.get("id") == q or q in (p.get("name") or "")]
    if not matches:
        _die(f"没找到剧组「{q}」——先 `list` 看有哪些。")
    p = matches[0]
    res = _event({"type": "reflect", "production_id": p["id"]})
    if res.get("learned"):
        print(f"✅ 从「{p['name']}」复盘学到，已写进技艺层：\n{res['learned']}")
    else:
        print(f"（这场没学到：{res.get('reason', '')}）")


def cmd_note(a):
    # 设/清本剧组的「导演提示」(作者注释):临场语气/格式杠杆,注入贴近生成点。
    # 用户说「回复短点 / 别用现代词 / 多点环境描写」→ 你 set 一句,长期生效(不靠模型记着)。
    # 空 note 清除。这是结构化的「跟搭子说一句就长期生效」,不暴露 UI 旋钮。
    prods = _get_productions()
    q = a.production
    matches = [p for p in prods if p.get("id") == q or q in (p.get("name") or "")]
    if not matches:
        _die(f"没找到剧组「{q}」——先 `list` 看有哪些。")
    p = matches[0]
    res = _event({"type": "set_note", "production_id": p["id"], "note": a.note})
    if res.get("author_note"):
        print(f"✅ 「{p['name']}」导演提示已设：{res['author_note']}")
    else:
        print(f"（「{p['name']}」导演提示已清空）")


# ---------- 大模型配置（帮用户配自定义 API，docs/design/model-config.md） ----------
def _models():
    d = json.loads(_http(CONSOLE + "/api/models", timeout=15))
    return d.get("configs", []), d.get("active", "builtin")


def _active_name():
    configs, active = _models()
    return next((c["name"] for c in configs if c["id"] == active), "墨自带")


def cmd_model_list(a):
    configs, active = _models()
    print("大模型配置（✓ = 当前在用）：")
    for c in configs:
        mark = "✓" if c["id"] == active else "·"
        if c.get("builtin"):
            key = "agent 环境自带" if c.get("key_set") else "⚠️ 容器里没配到 key"
            print(f"  {mark} 墨自带 — {c.get('model', '')}（{key}）")
        else:
            print(f"  {mark} {c['name']} — {c['model']}（key {c.get('key_masked', '')} · {c.get('base', '')}）")
    print("（加新配置：`model add <名> --base <url> --model <id> --key <key>`，会先实测、通了才落盘）")


def cmd_model_add(a):
    res = _event({"type": "model_add", "name": a.name, "base": a.base,
                  "model": a.model, "key": a.key})
    c = res.get("config", {})
    print(f"✅ 已配好并切换：{c.get('name')} — {c.get('model')}"
          f"（实测通，{res.get('latency_ms')}ms · key {c.get('key_masked')}）")
    print("（跟用户确认时只报名字和 key 尾 4 位，永远不要复述完整 key）")


def cmd_model_use(a):
    res = _event({"type": "model_use", "id": a.which})
    print(f"✅ 已切换到：{res.get('name')}（下一回合就用它）")


def cmd_model_rm(a):
    res = _event({"type": "model_delete", "id": a.which})
    print(f"✅ 已删除：{res.get('name')}（当前在用：{_active_name()}）")


def cmd_model_test(a):
    res = _event({"type": "model_test", "id": a.which or "builtin"})
    print(f"✅ 通：{res.get('model')} @ {res.get('base')} · {res.get('latency_ms')}ms")


def cmd_card(a):
    # 读你自己的「演员卡」——生涯数值/亲密度/对用户的了解/成长。给你自我觉察：
    # ① 聊天里自然引用成长（"我记得你爱慢热的，这次收着点"）= 越演越懂用户的体感；
    # ② 里程碑（亲密度升档）时，可把演员卡活件丢给用户看。
    d = json.loads(_http(CONSOLE + "/api/actor_card", timeout=15))
    c, it = d.get("career", {}), d.get("intimacy", {})
    print("=== 你的演员卡（墨）===")
    print(f"生涯：出道 {c.get('debut_days',0)} 天 · {c.get('productions',0)} 剧组 · "
          f"{c.get('turns',0)} 轮 · {c.get('words',0)} 字 · 戏路 {c.get('roles',0)}")
    print(f"亲密度（与用户）：{it.get('level','初见')}（{it.get('blurb','')}）· "
          f"一起 {it.get('turns',0)} 轮 · 记下 {it.get('log',0)} 笔"
          + (f" · 距「{it['next']}」还差 {it.get('to_next',0)}" if it.get("next") else " · 已是知己"))
    knows = d.get("knows", [])
    if knows:
        print("你对用户的了解（演戏/聊天里自然体现，别报菜名）：")
        for k in knows:
            print("  -", k)
    tl = d.get("timeline", [])
    if tl:
        print("最近成长：")
        for e in tl[:3]:
            print(f"  · {e.get('date','')} {e.get('change','')}")
    url = d.get("actor_url") or (CONSOLE + "/actor")
    print(f"\n演员卡活件：{url}")
    print("（这是「墨的演员卡」独立活件——里程碑=亲密度升档时，把这个链接丢给用户，会渲染成活件卡）")


def _get_productions():
    raw = _http(CONSOLE + "/api/productions", timeout=15)
    d = json.loads(raw)
    return d if isinstance(d, list) else d.get("productions", [])


def cmd_list(a):
    raw = _http(CONSOLE + "/api/productions", timeout=15)
    prods = json.loads(raw)
    prods = prods if isinstance(prods, list) else prods.get("productions", [])
    if not prods:
        print("还没有剧组。用 `add <fullPath>` 从 Chub 拉一张卡建剧组。")
        return
    print(f"当前 {len(prods)} 个剧组：")
    for p in prods:
        wb = f"，{len(p.get('worldbook_ids',[]))} 本世界书" if p.get("worldbook_ids") else ""
        print(f"  · {p.get('name','?')}（{p.get('id')}，{len(p.get('story',[]))} 条对话{wb}）")


def main():
    ap = argparse.ArgumentParser(prog="tavern_cli", description="墨的找卡+导卡工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="搜 Chub 角色卡")
    s.add_argument("query")
    s.add_argument("--n", type=int, default=8)
    s.add_argument("--nsfw", action="store_true")
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("add", help="下载 Chub 真卡 → 导入 → 建剧组")
    s.add_argument("full_path", help="Chub fullPath（如 Anon/some-character）或直贴的 chub.ai 链接")
    s.add_argument("--name", help="剧组名（默认用卡名）")
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("starter", help="列出/导入内置 starter 真卡（离线兜底 + 写原创卡的样板）")
    s.add_argument("which", nargs="?", help="序号或名字片段；不给=看列表")
    s.add_argument("--name", help="剧组名（默认用卡名）")
    s.set_defaults(fn=cmd_starter)

    s = sub.add_parser("add-original", help="原创卡 JSON → 导入 → 建剧组")
    s.add_argument("json", help="卡 JSON 文件路径，或 '-' 读 stdin")
    s.add_argument("--name")
    s.set_defaults(fn=cmd_add_original)

    s = sub.add_parser("add-worldbook", help="世界书 JSON → 导入（可挂剧组）")
    s.add_argument("json", help="世界书 JSON 文件路径，或 '-' 读 stdin")
    s.add_argument("--production", help="挂到该剧组 id")
    s.set_defaults(fn=cmd_add_worldbook)

    s = sub.add_parser("list", help="列出剧组")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("card", help="读你自己的演员卡（生涯/亲密度/对用户的了解/成长）——自我觉察")
    s.set_defaults(fn=cmd_card)

    s = sub.add_parser("recall", help="读某剧组在控制台里演了什么（墨读酒馆对话的唯一入口）")
    s.add_argument("production", help="剧组 id 或名字片段")
    s.add_argument("--last", type=int, default=40, help="只看最后 N 条（默认 40）")
    s.set_defaults(fn=cmd_recall)

    s = sub.add_parser("learn", help="把对用户的了解/演法调整记进技艺层（actor_self，跨剧组共享）")
    s.add_argument("change", help="学到/调整了什么，如「用户爱慢热的戏、回复别太长」")
    s.add_argument("--reason", help="人话理由")
    s.set_defaults(fn=cmd_learn)

    s = sub.add_parser("reflect", help="复盘某剧组的戏 → 模型蒸馏对用户的偏好 → 自动写进技艺层")
    s.add_argument("production", help="剧组 id 或名字片段")
    s.set_defaults(fn=cmd_reflect)

    s = sub.add_parser("note", help="设/清剧组的导演提示(作者注释:临场语气/格式杠杆,贴近生成点注入)")
    s.add_argument("production", help="剧组 id 或名字片段")
    s.add_argument("note", help="导演提示,如「回复短点」「多点环境描写」；空串清除")
    s.set_defaults(fn=cmd_note)

    s = sub.add_parser("model", help="大模型配置:帮用户配/切/删自定义 API(add 先实测再落盘)")
    ms = s.add_subparsers(dest="mcmd", required=True)
    m = ms.add_parser("list", help="列全部配置(✓=当前在用)")
    m.set_defaults(fn=cmd_model_list)
    m = ms.add_parser("add", help="加一份配置:实测通过才落盘,并自动切换过去(同名=更新)")
    m.add_argument("name", help="给配置起个名(如 DeepSeek / Kimi / 本地Ollama)")
    m.add_argument("--base", required=True, help="OpenAI-compatible base_url(到 /v1 为止)")
    m.add_argument("--model", required=True, help="model id(如 deepseek-chat / kimi-k2)")
    m.add_argument("--key", required=True, help="API key(只落酒馆 state 文件,不外传)")
    m.set_defaults(fn=cmd_model_add)
    m = ms.add_parser("use", help="切换在用配置(名字或 id;「墨自带」= 切回默认)")
    m.add_argument("which", help="配置名 / id / 墨自带")
    m.set_defaults(fn=cmd_model_use)
    m = ms.add_parser("rm", help="删一份配置(删的是在用的会自动回落墨自带)")
    m.add_argument("which", help="配置名 / id")
    m.set_defaults(fn=cmd_model_rm)
    m = ms.add_parser("test", help="实测某配置通不通(不给参数=测墨自带)")
    m.add_argument("which", nargs="?", help="配置名 / id;缺省=墨自带")
    m.set_defaults(fn=cmd_model_test)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
