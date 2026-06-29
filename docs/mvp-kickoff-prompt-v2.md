# 酒馆 MVP — 新窗口 kickoff 提示词 v2（用干净号继续）

> 整段粘进一个新 Claude Code 窗口。自包含(新会话没有上下文)。这是 **接着干**:MVP 的硬骨头(Loop A 控制台 + 角色卡→prompt→DeepSeek 生成)上一会话已跑通验证,本轮用「干净号」把链条补完。

---

你的任务:继续把「酒馆(agent 角色扮演)」MVP 跑通 —— 导入角色卡 + 世界书 → 拼完整 prompt → 生成入戏回复 → **既能 chat 试戏、又能在 liveware 控制台沉浸演出**。这次用**干净号**(容器 `hermes-clean`)当酒馆 agent。

## 0. 先 orient(读完再动手)

设计 + 实现都在 `~/projects/clawchat-tavern/`:
- `skill/` — **已建好的演员运行时**:`server.py`(同源 http.server + `/api/*` + serve 控制台)、`actor.py`(拼 prompt + DeepSeek urllib)、`card_import.py`(解析 V2/V3 PNG 角色卡)、`actor_self.md`(演员「墨」自画像)、`SOUL.md`(chat 侧墨人格)、`reader/`(沉静感控制台 UI)、`tools/`(make_test_card / smoke)、`state/`(运行时)。跑法见 `skill/README.md`。
- `agentchat/chat_server.py` — 网页版多 agent 聊天台(自动发现 hermes-* 容器,`hermes chat` 后端)。
- `docs/design/` — surfaces-and-features.md(两面功能 + 覆盖契约 + 沉静感)、v1-build-spec.md(工程契约)。
- `docs/research/` — feasibility-liveware-agent-channel.md(通路绿灯)、agent-liveware-opportunities.md(演员模型/两层记忆)。
- 铁律:纯 agent 侧;ClawChat 客户端(`~/projects/clawchat`)**只读不改**、**零新后端接口**(要新接口先停下问);复用 V2 卡格式不 fork ST;状态只落 agent 侧。

## 1. ✅ 已验证可用(别重造,直接复用)

**Loop A(MVP 心脏)已跑通**:`skill/server.py` 在 Mac 裸跑(DeepSeek,**与 ClawChat agent 无关**)→ 导入 V2 卡(`tools/make_test_card.py` 生成的「凛·雨夜侦探」)+ 世界书 → 拼完整 prompt(角色卡 × actor_self.md × 世界书 × 本剧组隔离故事线)→ DeepSeek 入戏生成(世界书心结触发✓、故事线连续✓)→ 控制台沉浸渲染(桌面 master-detail / 移动全屏 / 明暗自适应)+ 重生成/编辑/切换。preview 三态截图验过。
跑:`.claude/launch.json`(在 clawchat 仓)已有 `tavern` 配置 → preview_start;或 `python3 skill/server.py --port 8799`。模型 key 自动从 `~/.hermes-*/​.env` 读。

## 2. 干净号 = 容器 `hermes-clean`

上一会话挖出真凶(见 §4 gotcha ①):之前所有 tavern 容器都因复制了带身份的 config.yaml 而继承同一个旧 agent `usr_01KW0YR6`。`hermes-clean` 是**第一个真正身份干净**的容器(config 剔除了 clawchat 段、全 home 零 `01KW0YR6`、唯一 `CLAWCHAT_DEVICE_ID=hermes-clean-uniq-20260629`、clawchat 插件已装)。

**第一步**:先把干净号激活成 ClawChat 酒馆 agent。
1. 跟用户要一个**全新连接码**:ClawChat → 联系人 → 注册 Agent → Hermes → 复制连接码。
2. `docker exec hermes-clean hermes clawchat activate <连接码>` → 看打印的 `usr_XXXX`:
   - **≠ usr_01KW0YR6** → 终于是新 agent,账号支持多 agent;继续。
   - **= usr_01KW0YR6** → 那才是真·账号级单 agent 的干净证据,记录、告诉用户(这条之前因 config 污染一直没干净测过)。
3. 部署墨人格:`cp skill/SOUL.md ~/.hermes-clean/SOUL.md && docker exec hermes-clean hermes gateway restart`。
4. (可选)给它设好显示名:`docker exec hermes-clean sh -lc 'cd /opt/data/plugins/clawchat && HERMES_HOME=/opt/data /opt/hermes/.venv/bin/python -c "import asyncio,sys;sys.path.insert(0,\".\");from clawchat_gateway import tools;print(asyncio.run(tools.update_account_profile(nickname=\"墨\")))"'`

## 3. 跑通 MVP 的三段

1. **Loop A 控制台**(已通)— preview_start tavern,浏览器/preview 里导卡→建剧组→入戏→重生成。这段不依赖 ClawChat agent。
2. **chat 试戏** — 在 ClawChat 里跟干净号(墨)发「演个雨夜便利店店长」,看它入戏。或用 `agentchat` 网页台。
3. **Loop B(尽力)** — 把控制台经 tunnel 暴露成 `app-<id>.apps.clawling.io`,在 ClawChat **Windows 客户端**(rig)渲染成活件卡/容器窗。平台 tunnel 鉴权有摩擦,卡住别耗,Loop A 已证核心。

## 4. 本会话血泪 gotchas(务必避坑)

- **① 绝不 `cp` 已激活容器的 config.yaml** —— 它把 `clawchat.extra.{user_id,agent_id,owner_user_id}` 焊死,新容器一继承就永远绑旧 agent(这是 6+ 个码全绑 usr_01KW0YR6 的真凶,折腾了一整会话)。新容器要么生成全新 config、要么剔掉 config 的 `clawchat` 段,**确保 `grep -rl 01KW0YR6 /opt/data` 全 home 零命中**再激活。
- **② device-id 是 red herring** —— `--network host` 下所有容器同 host 指纹(hostname=docker-desktop+同 MAC → 同 device id),但 agent 身份其实在 config(见①),不在 device。`CLAWCHAT_DEVICE_ID` 可钉唯一值但不解决身份继承问题。
- **③ 容器日志是 UTC**(+8=北京);别被时间戳骗。
- **④ docker `hermes gateway restart` 双重启会卡 drain(restart_drain_timeout 180)** → 用 `docker restart <容器>` 强制干净重启。
- **⑤ skill 注册只扫 `$HERMES_HOME/skills/<分类>/<名>/`**,不扫 plugins/。
- **⑥ 起容器配方**:`docker run -d --name X --network host -e HERMES_HOME=/opt/data --env-file <home>/.env -v <home>:/opt/data nousresearch/hermes-agent:latest gateway run`;装插件 `docker exec X hermes plugins install clawling/clawchat-plugin-hermes-agent && hermes plugins enable clawchat`(容器内无 hermes 的 `npx` 安装会 ENOENT,用 `hermes plugins install`);`hermes chat -q "..." --pass-session-id -Q` 做带记忆的单轮(首轮拿 session_id,后续 `--resume`)。

## 5. PC 测试机(Loop B 用)

rig = **192.168.2.248**(不是旧记录的 .246;DHCP),`ssh rog@192.168.2.248`,同机跑本地模型(ollama,需 `Start-ScheduledTask OllamaServe`)+ ClawChat Windows 客户端。客户端驱动 `cd ~/projects/clawchat && python3 scripts/dev/win.py status|launch|stop|reload`;独立容器窗截图走 `scripts/dev/winrig/shot_window.py` 经 `run_in_session.ps1`。

## 6. 开工第一步

跟用户要一个全新连接码 → 激活 `hermes-clean` → 看 usr_ 是不是新的 → 部署墨 SOUL → 然后 preview_start tavern 把 Loop A 控制台拉起来给用户看。每步申明影响面;遇到要动后端/新接口立刻停。

---
