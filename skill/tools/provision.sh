#!/bin/sh
# provision — 首跑：把这个 agent 的两个活件 app 建好并注册（install.sh 的容器内一半）。
#
# 职责边界：这里管**一次性 install 关注点**——建/复用 app、写 state/apps.json、register
# 进 member-backend（launcher 瓦片）。起进程 / 重启恢复是 bringup.sh 的事。
#
# 幂等 + 不烧配额：先 `liveware app list` 查同名 active app，**有就复用**（apps.json 丢了
# 也能从 list 恢复），**缺才 `app create`**。per-owner 配额 ~3、且无 app delete，所以
# 复用优先是硬要求——重跑本脚本不会重复建 app。
#
# app 名可用 env 覆盖（复制给别的搭子时改名）：
#   TAVERN_CONSOLE_APP_NAME（默认 Tavern）  TAVERN_ACTOR_APP_NAME（默认 Story Profile）
#
# 前置：容器已激活（hermes clawchat activate）+ 装了 clawchat 插件（带 liveware 二进制）。
# 跑：sh /opt/data/skills/creative/tavern/scripts/provision.sh（通常由 install.sh 调）
set -eu
TAVERN_SKILL=/opt/data/skills/creative/tavern
TAVERN_APP=/opt/data/apps/tavern-runtime
TAVERN_STATE=/opt/data/tavern-state
LW_DIR=/opt/data/clawchat/liveware
LW="${LIVEWARE_BIN:-}"
if [ -z "$LW" ]; then
  if command -v liveware >/dev/null 2>&1; then
    LW="$(command -v liveware)"
  else
    LW="$LW_DIR/liveware"
  fi
fi
if [ ! -x "$LW" ]; then
  echo "✗ liveware command not found: $LW" >&2
  exit 1
fi
PLUGIN=/opt/data/plugins/clawchat
PY=/opt/hermes/.venv/bin/python
APPS="$TAVERN_STATE/apps.json"
IDENTITY="$TAVERN_STATE/app_identity.json"
mkdir -p "$TAVERN_STATE"
if [ ! -f "$IDENTITY" ]; then
  cat > "$IDENTITY" <<'JSON'
{
  "persona_name": "主理人",
  "tavern_name": "酒馆",
  "actor_name": "故事档案",
  "persona_name_en": "Curator",
  "tavern_name_en": "Tavern",
  "actor_name_en": "Story Profile"
}
JSON
fi
CONSOLE_NAME="${TAVERN_CONSOLE_APP_NAME:-$($PY -c 'import json; d=json.load(open("'$IDENTITY'",encoding="utf-8")); print((d.get("tavern_name_en") or "Tavern").strip())')}"
ACTOR_NAME="${TAVERN_ACTOR_APP_NAME:-$($PY -c 'import json; d=json.load(open("'$IDENTITY'",encoding="utf-8")); print((d.get("actor_name_en") or "Story Profile").strip())')}"

# 1. liveware 登录（token 从 plugin profile config 解析；env CLAWCHAT_TOKEN 是空壳别直接传）
echo "== login =="
cd "$PLUGIN" && HERMES_HOME=/opt/data "$PY" -c \
  "import asyncio,sys; sys.path.insert(0,'.'); from clawchat_gateway import tools; print('login:', asyncio.run(tools.liveware_login()))"

# 2. 解析或创建两个 app → 写 apps.json（python 干重活：查 list 复用 / 缺则 create / 取域名）
echo "== resolve/create apps =="
HERMES_HOME=/opt/data "$PY" - "$LW" "$APPS" "$CONSOLE_NAME" "$ACTOR_NAME" <<'PY'
import json, subprocess, sys
lw, apps_path, console_name, actor_name = sys.argv[1:5]

def app_list():
    r = subprocess.run([lw, "app", "list", "--json"], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return []

def find(name, apps):
    for a in apps:
        if a.get("name") == name and a.get("status") == "active":
            return a
    return None

def find_id(app_id, apps):
    for a in apps:
        if a.get("appId") == app_id and a.get("status") == "active":
            return a
    return None

def existing_id(key):
    try:
        with open(apps_path, encoding="utf-8") as f:
            return ((json.load(f).get(key) or {}).get("app_id") or "").strip()
    except Exception:
        return ""

def ensure(key, name):
    apps = app_list()
    old_id = existing_id(key)
    if old_id:
        a = find_id(old_id, apps)
        if a:
            print("  reuse-id:", name, a["appId"])
            return a
    a = find(name, apps)
    if a:
        print("  reuse:", name, a["appId"])
        return a
    print("  create:", name, "(app list 无同名 active，新建——会消耗 owner 配额)")
    subprocess.run([lw, "app", "create", name, "--agent-type", "hermes"], check=True)
    a = find(name, app_list())
    if not a:
        raise SystemExit("  ✗ 创建后仍未在 app list 找到 " + name)
    print("  created:", name, a["appId"])
    return a

con = ensure("console", console_name)
act = ensure("actor", actor_name)
data = {
    "console": {"name": console_name, "app_id": con["appId"], "domain": con["domain"]},
    "actor":   {"name": actor_name,   "app_id": act["appId"], "domain": act["domain"]},
}
json.dump(data, open(apps_path, "w"), ensure_ascii=False, indent=2)
print("  wrote", apps_path)
PY

# 3. register 进 member-backend（名字/URL 不一致时刷新注册；不删除 liveware app 本体）
echo "== register apps =="
cd "$PLUGIN" && HERMES_HOME=/opt/data "$PY" - "$APPS" <<'PY'
import asyncio, json, sys
sys.path.insert(0, '.')
from clawchat_gateway import tools
d = json.load(open(sys.argv[1], encoding="utf-8"))

def app_rows(payload):
    if isinstance(payload, dict):
        rows = payload.get("apps")
        return rows if isinstance(rows, list) else []
    return []

async def go():
    listed = app_rows(await tools.list_apps())
    by_app_id = {r.get("app_id") or r.get("appId"): r for r in listed if isinstance(r, dict)}
    for key in ("console", "actor"):
        e = d[key]
        url = "https://%s/" % e["domain"]
        row = by_app_id.get(e["app_id"])
        same = row and row.get("name") == e["name"] and row.get("url") == url
        if same:
            print("  registered-current:", e["name"])
            continue
        if row:
            res = await tools.unregister_app(e["app_id"])
            print("  unregistered-stale:", row.get("name"), res)
        res = await tools.register_app(name=e["name"], app_id=e["app_id"], url=url)
        print("  registered:", e["name"], res)
asyncio.run(go())
PY

echo "== provision done. apps.json: =="
cat "$APPS"
