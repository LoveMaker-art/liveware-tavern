#!/bin/sh
# bringup — 容器重启后恢复酒馆 Loop B（控制台 server + liveware tunnel，两个活件 app）。
#
# 为什么需要：server.py 走 `docker exec -d`、tunnel-agent 是 liveware 起的子进程，
# 两者都不在容器 startup 里，docker restart 后都没了。这脚本补齐（持久化 v1.1 兜底）。
# /opt/data 是 mount（持久，含 state/），/root/.clawling 易失（每次重登）。
#
# 两个活件 app 同一 server（:8799），靠 tunnel 透传的 X-Forwarded-Host 分流：
#   墨的酒馆   app-02dd… → /  = 控制台      墨的演员卡 app-8942… → /  = 演员卡
# 三步注册缺一不可：app create（一次性，已建）→ tunnel bind（每次重启）→
#   clawchat_register_app（写 member-backend 才进活件入口；一次性，这里幂等重跑兜底）。
#
# 跑：docker exec hermes-clean sh /opt/data/tavern/tools/bringup.sh
set -u
TAVERN=/opt/data/tavern
LW=/opt/data/clawchat/liveware
PLUGIN=/opt/data/plugins/clawchat
PY=/opt/hermes/.venv/bin/python
PORT="${TAVERN_PORT:-8799}"
APP_ID="${TAVERN_APP_ID:-app-02dd46427910ed17}"              # 墨的酒馆（控制台）
ACTOR_APP_ID="${TAVERN_ACTOR_APP_ID:-app-8942010cf1db2004}"  # 墨的演员卡
ACTOR_HOST="$ACTOR_APP_ID.apps.clawling.io"

# 1. 控制台 server.py（setsid 完全脱离，docker exec 返回也不被杀）
if ! curl -fsS "127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
  setsid sh -c "cd $TAVERN && exec python3 server.py --port $PORT" \
    > "$TAVERN/server.log" 2>&1 < /dev/null &
  i=0; while [ $i -lt 8 ]; do curl -fsS "127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break; sleep 1; i=$((i+1)); done
fi
echo "console: $(curl -fsS "127.0.0.1:$PORT/api/health" 2>/dev/null || echo DOWN)"

# 1b. 演员卡分流域名（server 每请求读 state/actor_host.txt；/opt/data 持久，通常已在，幂等确保）
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

# 5. 注册两个 app 到 ClawChat member-backend（幂等；才会进活件入口。已注册则容错跳过）
cd "$PLUGIN" && HERMES_HOME=/opt/data "$PY" -c "
import asyncio, sys
sys.path.insert(0, '.')
from clawchat_gateway import tools
apps = [('墨的酒馆', '$APP_ID', 'https://$APP_ID.apps.clawling.io/'),
        ('墨的演员卡', '$ACTOR_APP_ID', 'https://$ACTOR_HOST/')]
async def go():
    for name, aid, url in apps:
        try:
            await tools.register_app(name=name, app_id=aid, url=url)
            print('registered:', name)
        except Exception as e:
            print('register', name, '(skip):', e)
asyncio.run(go())
" 2>&1 | sed 's/^/  /'

echo "公网: https://$APP_ID.apps.clawling.io/  (酒馆)"
echo "公网: https://$ACTOR_HOST/  (演员卡)"
