#!/bin/sh
# bringup — 容器重启后恢复酒馆 Loop B（控制台 server + liveware tunnel）。
#
# 职责边界：这里**只管重启恢复**——起进程、重登、重绑。建 app / register 是
# 一次性的 install 关注点，已挪到 provision.sh（见 install.sh）。首跑请先跑
# host 侧 `tools/install.sh <容器>`，它会建两个 app、写 state/apps.json、register，
# 再调本脚本把 Loop B 拉起来。此后每次 `docker restart` 只需重跑本脚本。
#
# 为什么需要：server.py 走 setsid、tunnel-agent 是 liveware 起的子进程，两者都不在
# 容器 startup 里，docker restart 后都没了。这脚本补齐（持久化 v1.1 兜底）。
# /opt/data 是 mount（持久，含 state/），/root/.clawling 易失（每次重登）。
#
# app ID 不再写死：从 state/apps.json 读（由 provision.sh 首跑写入，缺则报错指向 install）。
# 两个活件 app 同一 server（:8799），靠 tunnel 透传的 X-Forwarded-Host 分流：
#   console（酒馆）→ / = 控制台      actor（演员卡）→ / = 演员卡
#
# 跑：docker exec <容器> sh /opt/data/tavern/tools/bringup.sh
set -u
TAVERN=/opt/data/tavern
LW=/opt/data/clawchat/liveware
PLUGIN=/opt/data/plugins/clawchat
PY=/opt/hermes/.venv/bin/python
PORT="${TAVERN_PORT:-8799}"
APPS="$TAVERN/state/apps.json"

# 0. 读 app ID / 演员卡域名（provision.sh 首跑写入；无则这是首跑，指向 install）
if [ ! -f "$APPS" ]; then
  echo "✗ 未找到 $APPS —— 这看起来是首跑。" >&2
  echo "  先在 host 侧跑：tools/install.sh <容器>（建 app + 写 apps.json + register），再由它调本脚本。" >&2
  exit 1
fi
eval "$("$PY" - "$APPS" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
c = d.get("console", {}); a = d.get("actor", {})
print("APP_ID=%s" % c.get("app_id", ""))
print("ACTOR_APP_ID=%s" % a.get("app_id", ""))
print("ACTOR_HOST=%s" % a.get("domain", ""))
PY
)"
if [ -z "$APP_ID" ] || [ -z "$ACTOR_APP_ID" ]; then
  echo "✗ $APPS 缺 console/actor 的 app_id —— 重跑 install.sh 或 provision.sh 修复。" >&2
  exit 1
fi

# 1. 控制台 server.py（setsid 完全脱离，docker exec 返回也不被杀）
if ! curl -fsS "127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
  setsid sh -c "cd $TAVERN && exec python3 server.py --port $PORT" \
    > "$TAVERN/server.log" 2>&1 < /dev/null &
  i=0; while [ $i -lt 8 ]; do curl -fsS "127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break; sleep 1; i=$((i+1)); done
fi
echo "console: $(curl -fsS "127.0.0.1:$PORT/api/health" 2>/dev/null || echo DOWN)"

# 1b. 演员卡分流域名（server 每请求读 state/actor_host.txt；/opt/data 持久，幂等确保）
printf '%s' "$ACTOR_HOST" > "$TAVERN/state/actor_host.txt"
echo "actor_host: $ACTOR_HOST"

# 2. liveware 登录（token 从 plugin profile config 解析；/root/.clawling 易失，每次重登）
cd "$PLUGIN" && HERMES_HOME=/opt/data "$PY" -c \
  "import asyncio,sys; sys.path.insert(0,'.'); from clawchat_gateway import tools; print('login:', asyncio.run(tools.liveware_login()))"

# 3. 绑定两个 app 的 upstream 到同一 server（幂等）
for a in "$APP_ID" "$ACTOR_APP_ID"; do
  "$LW/liveware" tunnel bind "$a" "http://127.0.0.1:$PORT" >/dev/null 2>&1 \
    && echo "bound: $a -> 127.0.0.1:$PORT" || echo "bind $a: (skipped/failed)"
done

# 4. tunnel-agent（裸跑：默认生产 relay + control-url，token 读 ~/.clawling/liveware.json）
if ! pgrep -f tunnel-agent >/dev/null 2>&1; then
  setsid sh -c "exec $LW/tunnel-agent" \
    > /root/.clawling/tunnel-agent.boot.log 2>&1 < /dev/null &
  sleep 3
fi
echo "tunnel-agent pid: $(pgrep -f tunnel-agent | head -1 || echo NONE)"

echo "公网: https://$APP_ID.apps.clawling.io/  (酒馆)"
echo "公网: https://$ACTOR_HOST/  (演员卡)"
