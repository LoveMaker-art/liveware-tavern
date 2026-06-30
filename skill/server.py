"""server — 酒馆演员运行时的同源 server（stdlib http.server，仿 digest）。

serve 控制台静态页(reader/) + /api/*（同源，浏览器同源策略天然满足，模型 creds 留 server 端）。
状态全落 state/ 下 JSON 文件，永不写能力服务器/member-backend。

跑：TAVERN_MODEL_KEY=... python3 server.py [--port 8799]
"""
import json
import os
import secrets
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

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


def ev_switch_loadout(ev):
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    _set_active(p["id"])
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
    return actor.perform(card, actor_self_text(), wbs, persona, p["story"], note)


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


def ev_actor_grow(ev):
    """复杂功能→对话+成长：把演法/对你的了解的变化追加进 actor_self.md（带人话理由）。"""
    rt = os.path.join(STATE, "actor_self.md")
    actor_self_text()  # ensure exists
    stamp = time.strftime("%Y-%m-%d", time.localtime(ev.get("ts") or time.time()))
    line = f"\n- {stamp} {ev.get('reason','(无理由)')} → {ev.get('change','')}"
    with open(rt, "a", encoding="utf-8") as f:
        f.write(line)
    return {"ok": True, "appended": line.strip()}


def ev_reflect(ev):
    """复盘一场戏 → 模型蒸馏「对用户的 RP 偏好」→ 追加进技艺层 actor_self。
    「越演越懂你」的结构化触发：不靠 agent 临场总结，服务端模型抽，落跨剧组共享层。"""
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    story = p.get("story", [])
    if sum(1 for m in story if m.get("role") == "user") < 2:
        return {"learned": None, "reason": "戏太短，没什么可学的"}
    card = load_card(p["card_id"]) or {}
    learned = actor.reflect_on_play(card, story, actor_self_text())
    if not learned:
        return {"learned": None, "reason": "这场没看出明显偏好"}
    rt = os.path.join(STATE, "actor_self.md")
    stamp = time.strftime("%Y-%m-%d", time.localtime())
    with open(rt, "a", encoding="utf-8") as f:
        f.write(f"\n- {stamp}（复盘「{p.get('name', '')}」）→ {learned}")
    return {"learned": learned, "production": p.get("name")}


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


EVENTS = {
    "import_card": ev_import_card, "import_card_json": ev_import_card_json,
    "import_worldbook": ev_import_worldbook, "attach_worldbook": ev_attach_worldbook,
    "create_production": ev_create_production, "switch_loadout": ev_switch_loadout,
    "delete_production": ev_delete_production,
    "send_message": ev_send_message, "append_turn": ev_append_turn,
    "regenerate": ev_regenerate,
    "swipe": ev_swipe, "edit_message": ev_edit_message, "actor_grow": ev_actor_grow,
    "reflect": ev_reflect, "set_persona": ev_set_persona, "set_note": ev_set_note,
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

    def _serve_index(self):
        # 注入版本化资源引用破 relay 缓存:clawling relay/CDN 把 .js/.css 强制缓存成
        # `public, max-age=2592000, immutable`(30天,覆盖源站 no-store)→ 改动不生效。
        # index.html 自身是 no-store(relay 透传)永远新,所以给资源 URL 挂 ?v=<token>,
        # token 取资源 mtime → 每次部署自动变 → 新 URL = relay 缓存未命中 = 取到新文件。
        try:
            with open(os.path.join(READER, "index.html"), encoding="utf-8") as f:
                html = f.read()
        except OSError:
            return self._json(404, {"error": "not found"})
        token = 0
        for fn in ("app.js", "bridge.js", "console.css", "index.html"):
            try:
                token ^= int(os.path.getmtime(os.path.join(READER, fn)))
            except OSError:
                pass
        v = format(token & 0xFFFFFF, "x")
        for a in ("console.css", "bridge.js", "app.js"):
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
            return self._json(200, {"ok": True, "dry_run": False, **actor.model_info()})
        if path == "/api/cards":
            return self._json(200, {"cards": _list("cards")})
        if path == "/api/worldbooks":
            return self._json(200, {"worldbooks": _list("worldbooks")})
        if path == "/api/productions":
            return self._json(200, {"productions": _list("productions"),
                                    "active": _get_state().get("active_production_id")})
        if path == "/api/actor":
            # 演员技艺层(actor_self.md,会随演出/复盘积累的富提示词) + 活件版本(应用发版号)。
            return self._json(200, {"actor_self": actor_self_text(), "version": liveware_version()})
        # static reader（index.html 走版本化注入,破 relay 的 immutable 缓存）
        rel = path.lstrip("/") or "index.html"
        if rel == "index.html":
            return self._serve_index()
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
            for delta in actor.perform_stream(card, actor_self_text(), wbs, persona, p["story"], note):
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
