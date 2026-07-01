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
#   TAVERN_CONSOLE_APP_NAME（默认 墨的酒馆）  TAVERN_ACTOR_APP_NAME（默认 墨的演员卡）
#
# 前置：容器已激活（hermes clawchat activate）+ 装了 clawchat 插件（带 liveware 二进制）。
# 跑：docker exec <容器> sh /opt/data/tavern/tools/provision.sh（通常由 install.sh 调）
set -eu
TAVERN=/opt/data/tavern
LW=/opt/data/clawchat/liveware/liveware
PLUGIN=/opt/data/plugins/clawchat
PY=/opt/hermes/.venv/bin/python
CONSOLE_NAME="${TAVERN_CONSOLE_APP_NAME:-墨的酒馆}"
ACTOR_NAME="${TAVERN_ACTOR_APP_NAME:-墨的演员卡}"
APPS="$TAVERN/state/apps.json"
mkdir -p "$TAVERN/state"

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

def ensure(name):
    a = find(name, app_list())
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

con = ensure(console_name)
act = ensure(actor_name)
data = {
    "console": {"name": console_name, "app_id": con["appId"], "domain": con["domain"]},
    "actor":   {"name": actor_name,   "app_id": act["appId"], "domain": act["domain"]},
}
json.dump(data, open(apps_path, "w"), ensure_ascii=False, indent=2)
print("  wrote", apps_path)
PY

# 3. register 进 member-backend（幂等；才进活件入口 launcher 瓦片。已注册则容错跳过）
echo "== register apps =="
cd "$PLUGIN" && HERMES_HOME=/opt/data "$PY" - "$APPS" <<'PY'
import asyncio, json, sys
sys.path.insert(0, '.')
from clawchat_gateway import tools
d = json.load(open(sys.argv[1]))
async def go():
    for key in ("console", "actor"):
        e = d[key]
        url = "https://%s/" % e["domain"]
        try:
            await tools.register_app(name=e["name"], app_id=e["app_id"], url=url)
            print("  registered:", e["name"])
        except Exception as ex:
            print("  register", e["name"], "(skip):", ex)
asyncio.run(go())
PY

echo "== provision done. apps.json: =="
cat "$APPS"
