#!/bin/sh
set -eu
LOG=/opt/data/logs/tavern-liveware-register.log
LOCK=/opt/data/tavern-state/tavern-liveware-register.lock
PROVISION=/opt/data/skills/creative/tavern/scripts/provision.sh
BRINGUP=/opt/data/skills/creative/tavern/scripts/bringup.sh

liveware_ready() { [ -x /opt/data/clawchat/liveware/liveware ] || command -v liveware >/dev/null 2>&1; }
tunnel_agent_ready() { [ -x /opt/data/clawchat/liveware/tunnel-agent ] || command -v tunnel-agent >/dev/null 2>&1; }
resolve_clawchat_db() {
  data_root=${HERMES_HOME:-/opt/data}
  for candidate in \
    "${CLAWCHAT_DB_PATH:-}" \
    "$data_root/clawchat/clawchat.sqlite" \
    "$data_root/clawchat.sqlite"
  do
    if [ -n "$candidate" ] && [ -f "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}
clawchat_db_ready() { resolve_clawchat_db >/dev/null 2>&1; }
activation_ready() {
  db_path=$(resolve_clawchat_db) || return 1
  CLAWCHAT_DB_PATH="$db_path" /opt/hermes/.venv/bin/python - <<'PYACT'
import os
import sqlite3
from pathlib import Path

p = Path(os.environ['CLAWCHAT_DB_PATH'])
if not p.exists():
    raise SystemExit(1)
try:
    con = sqlite3.connect(str(p))
    row = con.execute("""
        SELECT 1 FROM activations
        WHERE platform = 'hermes'
          AND account_id = 'default'
          AND conversation_id IS NOT NULL
          AND conversation_id != ''
        LIMIT 1
    """).fetchone()
    raise SystemExit(0 if row else 1)
except Exception:
    raise SystemExit(1)
PYACT
}

mkdir -p /opt/data/logs /opt/data/tavern-state
{
  echo "==== $(date -Is) tavern liveware startup ensure ===="
  if ! command -v flock >/dev/null 2>&1; then
    echo "flock missing; continuing without lock"
    sh "$PROVISION"
    sh "$BRINGUP"
    exit 0
  fi
  flock -n 9 || { echo "another ensure process is running; skip"; exit 0; }
  i=0
  while [ $i -lt 40 ]; do
    if liveware_ready && tunnel_agent_ready && clawchat_db_ready && activation_ready; then
      echo "dependencies ready after $i check(s)"
      break
    fi
    echo "waiting for liveware/clawchat activation... $((i+1))/40"
    sleep 3
    i=$((i+1))
  done

  if ! liveware_ready; then
    echo "liveware command missing after wait; skip"
    exit 0
  fi
  if ! tunnel_agent_ready; then
    echo "tunnel-agent command missing after wait; skip"
    exit 0
  fi
  if ! clawchat_db_ready; then
    echo "clawchat.sqlite missing after wait; skip"
    exit 0
  fi
  if ! activation_ready; then
    echo "clawchat activation conversation missing after wait; skip"
    exit 0
  fi

  echo "clawchat database: $(resolve_clawchat_db)"
  echo "liveware command: $(command -v liveware 2>/dev/null || echo /opt/data/clawchat/liveware/liveware)"
  echo "tunnel-agent command: $(command -v tunnel-agent 2>/dev/null || echo /opt/data/clawchat/liveware/tunnel-agent)"
  sh "$PROVISION"
  sh "$BRINGUP"
  echo "==== $(date -Is) tavern liveware ensure done ===="
} 9>"$LOCK" >>"$LOG" 2>&1
