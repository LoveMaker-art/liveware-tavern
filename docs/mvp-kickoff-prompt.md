# 酒馆 MVP — 新窗口 kickoff 提示词

> 把下面分隔线内的整段粘进一个新的 Claude Code 窗口即可开工。它是自包含的（新会话没有本轮上下文）。

---

你的任务：在本地把「酒馆（agent 角色扮演）」MVP 端到端跑通——起一个本地 Hermes agent，建一个酒馆 skill，导入一张 V2 角色卡 + 一个世界书，拼出完整 prompt 调模型生成，做到**既能在 ClawChat 聊天里试戏、也能在 liveware 控制台沉浸演出**。测试客户端用 PC（Windows rig）。

## 0. 先 orient，读完再动手（别跳过）

设计权威（`~/projects/clawchat-tavern/docs/`）：
- `design/v1-build-spec.md` — 工程契约（数据形态 / 同源事件 / 演员运行时 / 最薄切片）。**主文档。**
- `design/surfaces-and-features.md` — 两面功能 + 覆盖契约 + 沉静感线框决定。
- `research/agent-liveware-opportunities.md` — 演员模型 / 两层记忆 / `actor_self.md`（我们独有）。
- `research/feasibility-liveware-agent-channel.md` — 通路裁决（核心闭环走现有管线，绿灯）。

照抄的先例：
- digest skill `~/projects/clawchat-newsdesk/hermes/skills/digest/` — `server.py`（同源 `/api/*` + serve reader + `urllib` 调用骨架，stdlib 零依赖）、`reader/bridge.js`（同源回写，84 行）。
- liveware-app skill `~/projects/clawchat-liveware-skills/skills/liveware-app/SKILL.md`（v3.0.0）+ `references/lifecycle.md` — **新部署模型**（容器内 `liveware` CLI：login→app create→tunnel bind→clawchat_register_app）。`testbed/{run.sh,deploy_skill.sh,README.md}` — 起容器 + 部署 skill + 激活。
- localagent `~/projects/clawchat-localagent/` — `probe/probe_toolcall.py:62 chat()`（调 ollama 的可抄 LLM client 范例，纯 stdlib urllib）、`README.md`（L0/L1 体检 + 全本机变体）、`hermes/config.local.yaml`（Hermes model 块改法）。

铁律（`~/projects/clawchat/CLAUDE.md` + `CLAUDE.local.md`）：纯 agent 侧；ClawChat 客户端**只读不改**、**零新后端接口**（要新接口/字段立刻停下问，铁律 B）；每步申明影响面（铁律 D）；不主动 commit。

## 1. 架构（来自 v1-build-spec）

- **演员运行时** = 酒馆 skill 的 `server.py` + 一个 LLM client。同源 `/api/*` 收事件，拼 prompt（**角色卡=剧本 × `actor_self.md`=演员** + 世界书相关条目 + 本剧组故事线），调模型，**同步返回**回复。
- **两层记忆**：故事 per 剧组隔离；`actor_self.md` 跨剧组共享（演员的活·自画像，会成长——这是我们和酒馆的命根子）。
- **两个 loop，分阶段做**：
  - **Loop A（核心，绿，不碰 relay）**：控制台同源 `fetch('/api/event')` → server 拼 prompt → 调模型 → 同步返回渲染。**浏览器开 server 的 console URL 就能验，不需要 ClawChat 客户端。** ← MVP 心脏。
  - **Loop B（接客户端，有平台摩擦）**：tunnel bind → 公网 `app-<id>.apps.clawling.io` → ClawChat 客户端渲染活件卡 → 容器窗打开。放 Loop A 跑通之后做。

## 2. 建造顺序

**Phase 0 — 起本地 agent + 接模型**
1. 起/复用 Hermes agent 容器：镜像 `nousresearch/hermes-agent:latest`、`--network host`、独立 `HERMES_HOME`（可复用现成 `~/projects/clawchat-liveware-skills/testbed`，或新建 `~/.hermes-tavern`）。
2. **模型基座（config seam，先接一个能跑的）**——跟用户确认选哪个：
   - 本地：rig 上 ollama qwen3。**当前 ollama 没起**，先 `ssh rog@192.168.2.248 Start-ScheduledTask OllamaServe`，再 `curl --max-time 10 http://192.168.2.248:11434/api/tags` 验、列出 `qwen3:30b-a3b-instruct-2507-q4_K_M`。可选先跑 `cd ~/projects/clawchat-localagent && OLLAMA_BASE_URL=http://192.168.2.248:11434/v1 python probe/probe_toolcall.py` 体检（3/3 合格）。
   - 云端：DeepSeek（最省心、文笔好，要 `DEEPSEEK_API_KEY`）。
3. 装 clawchat 插件（`hermes plugins install clawling/clawchat-plugin-hermes-agent` → `enable clawchat` → `gateway restart`）。**跟用户要一个 ClawChat 激活码**（用户在客户端侧实时生成）→ `hermes clawchat activate <激活码>`。验 `gateway.log` 出现 `✓ clawchat connected` + 用户发消息能回 → agent 已是 ClawChat 联系人。

**Phase 1 — 酒馆 skill + Loop A 核心闭环（MVP 心脏）**
4. 建 tavern skill，目录仿 digest：`server.py / reader/{index.html,app.js,bridge.js,console.css} / card_import.py / actor.py / SKILL.md / state/`。**部署坑**：agent 的 available_skills 只扫 `$HERMES_HOME/skills/<分类>/<名>/`（不扫 plugins/），所以 rsync 到 `…/skills/clawchat/tavern/` 再 `gateway restart`。
5. `card_import.py`：吃一张真 V2 PNG 角色卡（`chara` tEXt chunk → base64 → JSON，**保留未知 `extensions` 键**）+ 一个世界书 → 落 `state/cards/` + `state/worldbooks/`。
6. `actor.py`：拼 prompt（角色卡 + `actor_self.md` + agent 选的世界书相关条目 + 本剧组故事线隔离）+ LLM client（抄 `probe_toolcall.py:62 chat()`，env 注入 `TAVERN_MODEL_BASE`/`TAVERN_MODEL`/`TAVERN_MODEL_KEY`）→ 同步生成。
7. `server.py`：同源路由 `/api/health`、`/api/event`（`switch_loadout`/`send_message`/`import_card`/`create_production`/`add_lore`/`regenerate`/`swipe`/`edit_message`/`actor_grow`）+ serve reader。跑起来。
8. `reader/` 控制台：沉静感对话面（照 surfaces-and-features 线框：serif 叙事、用户输入后退、渐进披露控制条），`bridge.js` 同源 fetch（复刻 digest 的 `send()`）。
9. **验 Loop A**：浏览器开 console URL → 导卡 → `create_production` → `first_mes` → `send_message` → 在控制台入戏对话。**这是 MVP 核心爽点，不需要 ClawChat 客户端就能证。**

**Phase 2 — 试戏 in chat + Loop B 接客户端**
10. **试戏 in chat**：在 ClawChat 里直接跟 agent 聊，让它即兴入戏（agent 的 SOUL/skill 承载）。
11. **Loop B reach**：`liveware login`（**当前绑定鉴权过期，先重登刷 mat_ token，见 lifecycle.md §A**）→ `liveware app create 酒馆 --agent-type hermes` 拿 appId → 容器内跑 server.py → `liveware tunnel bind <appId> http://host.docker.internal:<port>` → `clawchat_register_app` 或把 `https://<appId>.apps.clawling.io` 发进聊天 → ClawChat 客户端渲染活件卡、点开容器窗看沉浸演出。**若 Loop B 卡在平台 durability，别耗——Loop A 已证 MVP 核心。**

## 3. PC 测试机（Windows rig）

- rig = **192.168.2.248**（hostname DESKTOP-UQNGQCU，user rog；**不是旧 memory 的 .246**，DHCP 漂了）。`ssh rog@192.168.2.248`。同一台机既当本地模型机（ollama）又当 ClawChat Windows 客户端。
- ClawChat Windows 客户端驱动：`cd /Users/libin/projects/clawchat && python3 scripts/dev/win.py status|launch|stop|reload|dump|tap|input|logs`。**别用 `restart`（塌窗）**；改 Dart 用 `reload`，改原生用 `stop`+`launch`。
- 独立 liveware 容器窗是独立 Win32 WebView2 窗，`win.py shot` 截不到；用 `scripts/dev/winrig/shot_window.py` 经 `run_in_session.ps1` trampoline（交互桌面）：`--list` 找窗 class → `--class <C> --out C:/dev/lw.png` → `scp` 回来 Read。

## 4. MVP 验收（done = 这些都绿）

1. 本地 Hermes agent 在 ClawChat 里是联系人，发消息能回（= 试戏 in chat）。
2. 酒馆 skill 装上、`server.py` 跑起来、控制台 URL 可开。
3. 导入一张真 V2 角色卡 + 一个世界书，成功落 `state/`。
4. `send_message` 在控制台触发：拼出完整 prompt（角色卡 × `actor_self.md` × 世界书 × 故事线）+ 调模型 + 同步返回 in-character 回复 → 控制台沉浸渲染（**Loop A 闭环**）。
5. （尽力）Loop B：在 ClawChat Windows 客户端把控制台作为 liveware 活件卡打开，看到沉浸演出容器窗。

## 5. 开工第一步 & 要跟用户确认的

- **立刻跟用户要**：(a) ClawChat 激活码（现场生成）；(b) 模型基座选云端 DeepSeek（要 key）还是本地 rig ollama qwen3。
- 然后先 orient（读 §0 的 docs + 先例），再动手。每步申明影响面；遇到要新后端/接口立刻停。

## 6. 已知坑 / 别被 stale memory 误导

- rig IP = **.248 不是 .246**；ollama 当前没起，先 `Start-ScheduledTask OllamaServe`。
- relay **不再是 503 死结**（2026-06-28 实测公网 URL 200 + `/api/health` ok）；真卡点是**绑定鉴权 flapping**（`liveware app list`=unauthorized / tunnel-agent.log 刷 EOF/validation），修法=`liveware` 重登（lifecycle.md §A）。
- agent 技能注册只扫 `skills/<分类>/<名>/`，不扫 `plugins/`。
- 冷重启 tunnel durability 是平台缺口（supervisord 需 `AGENT_MANAGER_TOKEN`），MVP 别在这耗。
- 出厂 skill 安全收敛禁 agent 碰 `CLAWCHAT_TOKEN`/直跑 `liveware` CLI；手动排障可直跑，让 agent 跑要顺工具流。
- 工作区：设计 docs 在 `~/projects/clawchat-tavern`；酒馆 skill 代码建在 skill 仓（仿 digest/liveware-app）；ClawChat 客户端仓 `~/projects/clawchat` **只读**。

---
