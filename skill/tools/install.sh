#!/usr/bin/env bash
# install — 把这套 tavern 复制到一个「已激活的 hermes 容器」，一键就位。
#
#   ./install.sh <容器名> [--skill-dir <路径>] [--place-only]
#
# 一次性做四件事（全幂等，可重跑）：
#   1. 两处放置（今天靠手动 docker cp 两趟、漏一处技能就形同不存在，这里合一）：
#        · 运行时  → /opt/data/apps/tavern-runtime/                （排除 state/，绝不覆盖运行数据）
#        · 技能注册 → /opt/data/skills/creative/tavern/ （gateway 只扫这里的 SKILL.md）
#        · SOUL    → /opt/data/SOUL.md                （chat 侧若棠人格，热生效）
#   2. 竞争产物卫生：删 agent 自发造的诱导反模式游离产物
#        · skills/creative/sillytavern-character-cards（PNG 生成器，诱手搓）
#        · skills/creative/tavern/references/browser-injection-*（手搓 PNG 注入手册）
#   3. 模型 creds 自检：容器里有 DEEPSEEK_API_KEY / TAVERN_MODEL_KEY 吗？
#      缺 → 警告（Loop A 生成会失败），但不阻断放置，也**绝不写死**任何 key。
#   4. 首跑 provision（建/复用两个 app + 写 apps.json + register）→ bringup（起 Loop B）。
#
# 前置（C 侧 bootstrap，本脚本不做——见 docs/design/install.md）：
#   容器已 docker run + 装 clawchat 插件（带 liveware 二进制）+ hermes clawchat activate。
# 重启恢复用 bringup.sh，不必重跑 install。
set -euo pipefail

# ---- 参数 ----
CONTAINER="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"   # tools/ 的父目录 = 仓库 skill/
PLACE_ONLY=0
shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    --place-only) PLACE_ONLY=1; shift ;;   # 只放置+卫生+creds 自检，跳过 provision/bringup
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

if [ -z "$CONTAINER" ]; then
  echo "用法：$0 <容器名> [--skill-dir <路径>] [--place-only]" >&2
  echo "  --place-only：只放置代码/卫生/creds 自检（激活码还没到时先落地），跳过建 app + 起 Loop B。" >&2
  exit 2
fi
if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "✗ 容器「$CONTAINER」未在运行（docker ps 无此名）。" >&2
  exit 1
fi
if [ ! -f "$SKILL_DIR/SKILL.md" ] || [ ! -f "$SKILL_DIR/server.py" ]; then
  echo "✗ $SKILL_DIR 不像 tavern skill 目录（缺 SKILL.md / server.py）。用 --skill-dir 指定。" >&2
  exit 1
fi

echo "▶ 安装 tavern 到容器：$CONTAINER"
echo "  源：$SKILL_DIR"

# ---- 1. 两处放置 ----
echo "== 1/4 放置 =="
# 运行时（排除 state/ 运行数据、__pycache__、日志）——tar 管道进容器，docker cp 不支持 exclude
docker exec "$CONTAINER" mkdir -p /opt/data/apps/tavern-runtime /opt/data/skills/creative/tavern
tar -C "$SKILL_DIR" \
  --exclude='./state' --exclude='./__pycache__' --exclude='*.pyc' --exclude='*.log' \
  -cf - . | docker exec -i "$CONTAINER" tar -C /opt/data/apps/tavern-runtime -xf -
echo "  · 运行时 → /opt/data/apps/tavern-runtime/（已排除 state/）"
# 技能注册：gateway 只扫 skills/<分类>/<名>/，放 SKILL.md 一个文件即可
docker cp "$SKILL_DIR/SKILL.md" "$CONTAINER:/opt/data/skills/creative/tavern/SKILL.md"
echo "  · 技能注册 → /opt/data/skills/creative/tavern/SKILL.md"
# SOUL：chat 侧若棠人格，落 HERMES_HOME 根（热生效）
docker cp "$SKILL_DIR/SOUL.md" "$CONTAINER:/opt/data/SOUL.md"
echo "  · SOUL → /opt/data/SOUL.md"

# ---- 2. 竞争产物卫生 ----
echo "== 2/4 竞争产物卫生 =="
docker exec "$CONTAINER" sh -c '
  rm -rf /opt/data/skills/creative/sillytavern-character-cards
  rm -f  /opt/data/skills/creative/tavern/references/browser-injection-*.md
  echo "  · 已清 sillytavern-character-cards 技能 + references/browser-injection-*"
'

# ---- 3. 模型 creds 自检（不写死任何 key）----
echo "== 3/4 模型 creds 自检 =="
docker exec "$CONTAINER" sh -c '
  if [ -n "${TAVERN_MODEL_KEY:-}" ] || [ -n "${DEEPSEEK_API_KEY:-}" ] \
     || grep -qs "DEEPSEEK_API_KEY\|TAVERN_MODEL_KEY" /opt/data/.env; then
    echo "  ✓ 检到模型 key（DEEPSEEK_API_KEY / TAVERN_MODEL_KEY）。"
  else
    echo "  ⚠ 未检到模型 key —— Loop A 入戏生成会失败。"
    echo "    在容器 /opt/data/.env 填 DEEPSEEK_API_KEY=...，或用 TAVERN_MODEL_BASE/MODEL/KEY 指向本地 ollama。"
  fi
'

if [ "$PLACE_ONLY" -eq 1 ]; then
  echo ""
  echo "✅ 放置完成（--place-only）。激活后跑 provision.sh + bringup.sh，或重跑不带 --place-only 的 install。"
  exit 0
fi

# ---- 4. provision（建/复用 app + register）→ bringup（起 Loop B）----
echo "== 4/4 provision + bringup =="
docker exec \
  ${TAVERN_CONSOLE_APP_NAME:+-e TAVERN_CONSOLE_APP_NAME="$TAVERN_CONSOLE_APP_NAME"} \
  ${TAVERN_ACTOR_APP_NAME:+-e TAVERN_ACTOR_APP_NAME="$TAVERN_ACTOR_APP_NAME"} \
  "$CONTAINER" sh /opt/data/skills/creative/tavern/scripts/provision.sh
docker exec "$CONTAINER" sh /opt/data/skills/creative/tavern/scripts/bringup.sh

echo ""
echo "✅ 安装完成。"
echo "   技能要进 ClawChat 会话需重启 gateway：docker restart $CONTAINER（会自动丢 server/tunnel，"
echo "   重启后重跑 bringup.sh 恢复 Loop B）。SOUL 已热生效，下条消息即拿到。"
