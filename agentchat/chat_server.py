"""agentchat — 一个极简网页聊天界面,跟本机 Docker 里的 Hermes agent 对话。

发现所有运行中的 hermes-* 容器(排除系统的 newsdesk),顶部可切换;每个 agent 的对话
历史由本服务器内存维护(hermes -c 续会话需预先存在,改用「每轮喂上下文」)。人格由各容器
的 SOUL.md 自动带。纯 stdlib + subprocess docker exec,无依赖。

跑:python3 chat_server.py [--port 8800]  → 浏览器开 http://127.0.0.1:8800
"""
import json
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

EXCLUDE = {"hermes-newsdesk"}
SESSION = {}   # agent_id -> hermes session_id（hermes 原生维护对话记忆）
NAME_CACHE = {}


def _run(args, timeout=180):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def list_agents():
    try:
        out = _run(["docker", "ps", "--format", "{{.Names}}"], timeout=15).stdout
    except Exception:
        return []
    agents = []
    for name in out.split():
        if not name.startswith("hermes-") or name in EXCLUDE:
            continue
        agents.append({"id": name, "name": display_name(name)})
    return agents


def display_name(cid):
    if cid in NAME_CACHE:
        return NAME_CACHE[cid]
    nm = cid.replace("hermes-", "")
    try:
        r = _run(["docker", "exec", cid, "sh", "-lc", "head -1 /opt/data/SOUL.md"], timeout=15)
        line = (r.stdout or "").strip()
        if "—" in line:
            nm = line.split("—", 1)[1].strip()
        elif "-" in line and line.startswith("#"):
            nm = line.lstrip("# ").strip()
    except Exception:
        pass
    NAME_CACHE[cid] = nm
    return nm


_SID_RE = re.compile(r"session_id:\s*(\S+)")


def _parse(out):
    """剥掉 `session_id: …` 行,返回 (干净回复, session_id)。"""
    sid = None
    lines = []
    for ln in (out or "").splitlines():
        m = _SID_RE.search(ln)
        if m:
            sid = m.group(1)
            continue
        lines.append(ln)
    return "\n".join(lines).strip(), sid


def _ask(agent_id, message, sid):
    args = ["docker", "exec", agent_id, "hermes", "chat", "-q", message, "--pass-session-id", "-Q"]
    if sid:
        args += ["--resume", sid]
    r = _run(args, timeout=180)
    reply, new_sid = _parse(r.stdout)
    return reply, new_sid, r


def chat(agent_id, message):
    valid = {a["id"] for a in list_agents()}
    if agent_id not in valid:
        raise ValueError("unknown agent: " + agent_id)
    sid = SESSION.get(agent_id)
    reply, new_sid, r = _ask(agent_id, message, sid)
    if not reply and sid:  # resume 可能失效 → 起新会话重试
        reply, new_sid, r = _ask(agent_id, message, None)
    if new_sid:
        SESSION[agent_id] = new_sid
    if not reply:
        reply = (r.stderr or "").strip() or "(无回复)"
    return reply


PAGE = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent 对话</title><style>
:root{--bg:#f6f3ec;--surface:#fffdf8;--ink:#221f1a;--ink2:#5d574c;--muted:#928b7d;--line:#e6e0d4;--brand:#ff812a;--userbg:#efeae0}
@media(prefers-color-scheme:dark){:root{--bg:#15140f;--surface:#1d1b15;--ink:#ece7da;--ink2:#b3ab9a;--muted:#7d7565;--line:#2b281f;--userbg:#23211a}}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"PingFang SC",system-ui,sans-serif;display:flex;flex-direction:column}
header{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--line);background:var(--surface);flex-wrap:wrap}
.title{font-weight:600;margin-right:6px}
.tab{padding:6px 14px;border-radius:999px;border:1px solid var(--line);background:none;color:var(--ink2);cursor:pointer;font-size:14px}
.tab.on{background:var(--brand);color:#fff;border-color:var(--brand)}
.reset{margin-left:auto;border:1px solid var(--line);background:none;color:var(--muted);border-radius:8px;padding:6px 10px;cursor:pointer;font-size:13px}
#thread{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:14px}
.row{display:flex}.row.me{justify-content:flex-end}
.bub{max-width:75%;padding:9px 13px;border-radius:14px;white-space:pre-wrap;line-height:1.6}
.them .bub{background:var(--surface);border:1px solid var(--line)}
.me .bub{background:var(--brand);color:#fff}
.who{font-size:11px;color:var(--muted);margin:0 4px 3px}
.thinking{color:var(--muted);font-style:italic}
footer{display:flex;gap:9px;padding:12px 14px;border-top:1px solid var(--line);background:var(--surface)}
textarea{flex:1;resize:none;border:1px solid var(--line);border-radius:16px;padding:9px 14px;font:15px inherit;background:var(--bg);color:var(--ink);max-height:120px;outline:none}
textarea:focus{border-color:var(--brand)}
button.send{border:0;background:var(--brand);color:#fff;width:42px;border-radius:50%;font-size:18px;cursor:pointer}
button.send:disabled{opacity:.4}
.empty{margin:auto;color:var(--muted);text-align:center}
</style></head><body>
<header><span class="title">Agent 对话</span><span id="tabs"></span><button class="reset" id="reset">清空</button></header>
<div id="thread"><div class="empty">加载 agent 列表…</div></div>
<footer><textarea id="inp" rows="1" placeholder="说点什么…"></textarea><button class="send" id="send">↑</button></footer>
<script>
let agents=[],cur=null,busy=false;const E=s=>document.getElementById(s);
const threads={};
async function load(){const r=await fetch('/api/agents');agents=(await r.json()).agents;
 if(!agents.length){E('thread').innerHTML='<div class="empty">没发现运行中的 hermes-* 容器</div>';return;}
 E('tabs').innerHTML=agents.map(a=>`<button class="tab" data-id="${a.id}">${a.name}</button>`).join('');
 document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>pick(b.dataset.id));
 pick(agents[0].id);}
function pick(id){cur=id;threads[id]=threads[id]||[];
 document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('on',b.dataset.id===id));render();E('inp').focus();}
function render(){const t=threads[cur]||[];E('thread').innerHTML=t.length?t.map(m=>
 `<div class="row ${m.role==='user'?'me':'them'}"><div><div class="who">${m.role==='user'?'我':name(cur)}</div><div class="bub ${m.cls||''}">${esc(m.text)}</div></div></div>`).join('')
 :`<div class="empty">和 ${name(cur)} 开聊吧</div>`;
 E('thread').scrollTop=E('thread').scrollHeight;}
function name(id){const a=agents.find(x=>x.id===id);return a?a.name:id;}
function esc(s){return(s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
async function send(){const v=E('inp').value.trim();if(!v||busy||!cur)return;busy=true;E('send').disabled=true;
 E('inp').value='';threads[cur].push({role:'user',text:v});
 threads[cur].push({role:'assistant',text:name(cur)+' 正在想…',cls:'thinking'});render();
 try{const r=await fetch('/api/chat',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({agent:cur,message:v})});
  const d=await r.json();threads[cur].pop();
  threads[cur].push({role:'assistant',text:d.reply||('错误:'+(d.error||r.status))});}
 catch(e){threads[cur].pop();threads[cur].push({role:'assistant',text:'请求失败:'+e});}
 busy=false;E('send').disabled=false;render();E('inp').focus();}
E('send').onclick=send;
E('inp').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}};
E('reset').onclick=async()=>{if(!cur)return;await fetch('/api/reset',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({agent:cur})});threads[cur]=[];render();};
load();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _j(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/api/agents":
            return self._j(200, {"agents": list_agents()})
        b = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._j(400, {"error": "bad json"})
        if p == "/api/reset":
            SESSION.pop(body.get("agent"), None)
            return self._j(200, {"ok": True})
        if p == "/api/chat":
            try:
                return self._j(200, {"reply": chat(body["agent"], body["message"])})
            except Exception as e:
                return self._j(200, {"error": str(e)})
        return self._j(404, {"error": "not found"})


def main():
    port = 8800
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    elif os.environ.get("PORT"):
        port = int(os.environ["PORT"])
    print("Agent 对话 → http://127.0.0.1:%d" % port)
    print("发现 agent:", [a["name"] for a in list_agents()])
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    main()
