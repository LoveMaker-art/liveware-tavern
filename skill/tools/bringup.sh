#!/bin/sh
# bringup — 容器重启后恢复酒馆 Loop B（控制台 server + liveware tunnel）。
#
# 为什么需要：server.py 走 `docker exec -d`、tunnel-agent 是 liveware 起的子进程，
# 两者都不在容器 startup 里，docker restart 后都没了。这脚本补齐（持久化 v1.1 兜底）。
# /opt/data 是 mount（持久），/root/.clawling 易失（每次重登）。
#
# 跑：docker exec hermes-clean sh /opt/data/tavern/tools/bringup.sh
set -u
TAVERN=/opt/data/tavern
LW=/opt/data/clawchat/liveware
APP_ID="${TAVERN_APP_ID:-app-02dd46427910ed17}"
PORT="${TAVERN_PORT:-8799}"

# 1. 控制台 server.py（setsid 完全脱离，docker exec 返回也不被杀）
if ! curl -fsS "127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
  setsid sh -c "cd $TAVERN && exec python3 server.py --port $PORT" \
    > "$TAVERN/server.log" 2>&1 < /dev/null &
  i=0; while [ $i -lt 8 ]; do curl -fsS "127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break; sleep 1; i=$((i+1)); done
fi
echo "console: $(curl -fsS "127.0.0.1:$PORT/api/health" 2>/dev/null || echo DOWN)"

# 2. liveware 登录（token 从 plugin profile config 解析；/root/.clawling 易失，每次重登）
cd /opt/data/plugins/clawchat && HERMES_HOME=/opt/data /opt/hermes/.venv/bin/python -c \
  "import asyncio,sys; sys.path.insert(0,'.'); from clawchat_gateway import tools; print('login:', asyncio.run(tools.liveware_login()))"

# 3. 绑定 upstream（幂等）
"$LW/liveware" tunnel bind "$APP_ID" "http://127.0.0.1:$PORT" >/dev/null 2>&1 \
  && echo "bound: $APP_ID -> 127.0.0.1:$PORT" || echo "bind: (skipped/failed)"

# 4. tunnel-agent（裸跑：默认生产 relay + control-url，token 读 ~/.clawling/liveware.json）
if ! pgrep -f tunnel-agent >/dev/null 2>&1; then
  setsid sh -c "exec $LW/tunnel-agent" \
    > /root/.clawling/tunnel-agent.boot.log 2>&1 < /dev/null &
  sleep 3
fi
echo "tunnel-agent pid: $(pgrep -f tunnel-agent | head -1 || echo NONE)"
echo "公网: https://$APP_ID.apps.clawling.io/"
