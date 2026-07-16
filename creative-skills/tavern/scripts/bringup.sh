#!/bin/sh
# bringup — 容器重启后恢复酒馆 Loop B（控制台 server + liveware tunnel）。
#
# 职责边界：这里**只管重启恢复**——起进程、重登、重绑。建 app / register 是
# provision.sh 的一次性职责。首跑先执行 provision.sh 建两个 app、写
# state/apps.json 并完成注册，再执行本脚本。此后每次容器重启只需重跑本脚本。
#
# 为什么需要：server.py 走 setsid、tunnel-agent 是 liveware 起的子进程，两者都不在
# 容器 startup 里，docker restart 后都没了。这脚本补齐（持久化 v1.1 兜底）。
# /opt/data 是 mount（持久，含 state/），/root/.clawling 易失（每次重登）。
#
# app ID 不再写死：从 state/apps.json 读（由 provision.sh 首跑写入）。
# 两个活件 app 同一 server（:8799），靠 tunnel 透传的 X-Forwarded-Host 分流：
#   console（酒馆）→ / = 控制台      actor（故事档案）→ / = 故事档案
#
# 跑：sh /opt/data/skills/creative/tavern/scripts/bringup.sh
set -u
TAVERN_SKILL=/opt/data/skills/creative/tavern
TAVERN_APP=/opt/data/apps/tavern-runtime
TAVERN_STATE=/opt/data/tavern-state
LW_DIR=/opt/data/clawchat/liveware
LW_BIN="${LIVEWARE_BIN:-}"
if [ -z "$LW_BIN" ]; then
  if command -v liveware >/dev/null 2>&1; then
    LW_BIN="$(command -v liveware)"
  else
    LW_BIN="$LW_DIR/liveware"
  fi
fi
TUNNEL_AGENT_BIN="${TUNNEL_AGENT_BIN:-}"
if [ -z "$TUNNEL_AGENT_BIN" ]; then
  if command -v tunnel-agent >/dev/null 2>&1; then
    TUNNEL_AGENT_BIN="$(command -v tunnel-agent)"
  else
    TUNNEL_AGENT_BIN="$LW_DIR/tunnel-agent"
  fi
fi
if [ ! -x "$LW_BIN" ]; then
  echo "✗ liveware command not found: $LW_BIN" >&2
  exit 1
fi
if [ ! -x "$TUNNEL_AGENT_BIN" ]; then
  echo "✗ tunnel-agent command not found: $TUNNEL_AGENT_BIN" >&2
  exit 1
fi
PLUGIN=/opt/data/plugins/clawchat
PY=/opt/hermes/.venv/bin/python
PORT="${TAVERN_PORT:-8799}"
APPS="$TAVERN_STATE/apps.json"

# 0. 读 app ID / 故事档案域名（provision.sh 首跑写入）
if [ ! -f "$APPS" ]; then
  echo "✗ 未找到 $APPS —— 这看起来是首跑。" >&2
  echo "  先跑：/opt/data/skills/creative/tavern/scripts/provision.sh（建 app + 写 apps.json + register），再跑本脚本。" >&2
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
  echo "✗ $APPS 缺 console/actor 的 app_id —— 重跑 provision.sh 修复。" >&2
  exit 1
fi

# 1. 控制台 server.py（setsid 完全脱离，docker exec 返回也不被杀）
# 从 Hermes config 提取 Clawling API key（容器环境可能不设 DEEPSEEK_API_KEY）
TK=$("$PY" -c "
import yaml
with open('/opt/data/config.yaml') as f:
    cfg = yaml.safe_load(f) or {}
model = cfg.get('model', {}) or {}
provider = (cfg.get('providers', {}) or {}).get('clawling', {}) or {}
k = provider.get('api_key') or model.get('api_key') or ''
b = provider.get('api') or model.get('base_url') or ''
print(k)
print(b)
" 2>/dev/null)
CONFIG_MODEL_KEY=$(echo "$TK" | head -1)
CONFIG_MODEL_BASE=$(echo "$TK" | tail -1)
MODEL_KEY=${TAVERN_MODEL_KEY:-$CONFIG_MODEL_KEY}
MODEL_BASE=${TAVERN_MODEL_BASE:-$CONFIG_MODEL_BASE}
if [ -z "$MODEL_BASE" ]; then
  echo "✗ 未配置模型服务地址：请设置 TAVERN_MODEL_BASE，或在 /opt/data/config.yaml 配置 provider api/base_url。" >&2
  exit 1
fi
TTS_BASE=${TAVERN_TTS_BASE:-$MODEL_BASE}
HEALTH=$(curl -fsS "127.0.0.1:$PORT/api/health" 2>/dev/null || true)
NEED_SERVER=0
if [ -z "$HEALTH" ]; then
  NEED_SERVER=1
else
  NEED_SERVER=$(printf '%s' "$HEALTH" | MODEL_BASE="$MODEL_BASE" TTS_BASE="$TTS_BASE" "$PY" -c "
import json, os, sys
try:
    h = json.load(sys.stdin)
except Exception:
    print(1); raise SystemExit
expected = os.environ.get('MODEL_BASE', '')
expected_tts = os.environ.get('TTS_BASE', '')
stale = (not h.get('key_set')
         or (expected and h.get('base') != expected)
         or (expected_tts and h.get('tts_base') != expected_tts))
print(1 if stale else 0)
" 2>/dev/null || echo 1)
fi
if [ "$NEED_SERVER" = "1" ]; then
  pkill -f "server.py --port $PORT" >/dev/null 2>&1 || true
  setsid sh -c "cd $TAVERN_APP && exec env TAVERN_STATE_DIR=$TAVERN_STATE TAVERN_MODEL_KEY='$MODEL_KEY' TAVERN_MODEL_BASE='$MODEL_BASE' TAVERN_TTS_BASE='$TTS_BASE' $PY server.py --port $PORT" \
    9>&- > "$TAVERN_STATE/server.log" 2>&1 < /dev/null &
  i=0; while [ $i -lt 8 ]; do curl -fsS "127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break; sleep 1; i=$((i+1)); done
fi
echo "console: $(curl -fsS "127.0.0.1:$PORT/api/health" 2>/dev/null || echo DOWN)"

# 1b. 故事档案分流域名（server 每请求读 state/actor_host.txt；/opt/data 持久，幂等确保）
mkdir -p "$TAVERN_STATE"
printf '%s' "$ACTOR_HOST" > "$TAVERN_STATE/actor_host.txt"
echo "actor_host: $ACTOR_HOST"

# 2. liveware 登录（token 从 plugin profile config 解析；/root/.clawling 易失，每次重登）
cd "$PLUGIN" && HERMES_HOME=/opt/data "$PY" -c \
  "import asyncio,sys; sys.path.insert(0,'.'); from clawchat_gateway import tools; print('login:', asyncio.run(tools.liveware_login()))"

# 3. 绑定两个 app 的 upstream 到同一 server（幂等）
for a in "$APP_ID" "$ACTOR_APP_ID"; do
  "$LW_BIN" tunnel bind "$a" "http://127.0.0.1:$PORT" >/dev/null 2>&1 \
    && echo "bound: $a -> 127.0.0.1:$PORT" || echo "bind $a: (skipped/failed)"
done

# 4. tunnel-agent（裸跑：默认生产 relay + control-url，token 读 ~/.clawling/liveware.json）
if ! pgrep -f tunnel-agent >/dev/null 2>&1; then
  setsid sh -c "exec \"$TUNNEL_AGENT_BIN\"" \
    9>&- > /opt/data/.clawling/tunnel-agent.boot.log 2>&1 < /dev/null &
  sleep 3
fi
echo "tunnel-agent pid: $(pgrep -f tunnel-agent | head -1 || echo NONE)"

echo "公网: https://$APP_ID.apps.clawling.io/  (酒馆)"
echo "公网: https://$ACTOR_HOST/  (故事档案)"
