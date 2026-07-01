# 酒馆 — 下一轮迭代 kickoff（2026-06-30）

你的任务：继续迭代「酒馆（agent 角色扮演）」。**先和我讨论方向、对齐文档状态，再动手——没把方向和文档 clarify 清楚之前不要编辑业务代码**（最多 grep / Read / Explore 摸现状）。中文行文。

## 0. 先 orient（读完再动手）

项目 `~/projects/clawchat-tavern/`（独立 git 仓，2 提交 `a1d4330`→`26b77bc`，本地无 remote，分支 `main`）：

- `skill/` 演员运行时：
  - `server.py` 同源 `/api/event` + serve 控制台；事件：import_card / **import_card_json** / import_worldbook / attach_worldbook / create_production / switch_loadout / send_message / regenerate / edit_message / actor_grow / **reflect** / set_persona。GET：/api/health|cards|worldbooks|productions|actor。
  - `actor.py` 拼 prompt + DeepSeek（`perform`）+ **`reflect_on_play`**（复盘整场→蒸馏「对用户的 RP 偏好」）。
  - `card_import.py` V2/V3 PNG 解析（**已修 latin-1 中文乱码**：还原原始字节→判 base64→统一 utf-8）。
  - `reader/` 沉静感控制台 UI。
  - `SOUL.md` 墨人格 + 硬指引（找卡/导卡走 CLI、读戏 recall、学习 learn/reflect、两层记忆边界）。
  - `SKILL.md` agent 工具面（注册到容器 `skills/creative/tavern/`）。
  - `tools/tavern_cli.py` 墨的 CLI：`search` / `add <fullPath>`（Chub 真卡）/ `add-original <json|->`（原创纯 JSON）/ `add-worldbook` / `list` / **`recall <剧组>`**（读酒馆对戏）/ **`learn "<…>" [--reason]`**（手写技艺层）/ **`reflect <剧组>`**（服务端蒸馏→写技艺层）。
  - `tools/bringup.sh` 容器重启后恢复 Loop B。`actor_self.md` 技艺层种子。`state/`（运行时，gitignored）。
- `docs/design/v1-build-spec.md` = 权威实现规范（事件表 / CLI / 记忆桥接 / 「结构性 > 软性」教训）；`docs/design/surfaces-and-features.md`；`docs/research/`。跑法见 `skill/README.md`。
- preview：clawchat 仓 `.claude/launch.json` 的 `tavern` 配置 → preview_start。

## 1. 现状（已跑通，别重造）

- agent = 容器 **`hermes-clean`**（usr_01KW8SQPTXECF8E4XHYXF7708B，nickname「墨」，SOUL 在 `~/.hermes-clean/SOUL.md`，DeepSeek 基座）。**账号支持多 agent**（干净 config + 新连接码→新 usr_，已实锤）。
- **Loop A** 控制台入戏生成 ✅；**Loop B** liveware tunnel → 公网 `app-02dd46427910ed17.apps.clawling.io` → ClawChat 活件卡 + Windows 独立容器窗 ✅。
- **找卡/导卡** ✅（Chub.ai 来源，`api.chub.ai/search` + `avatars.charhub.io/avatars/<fullPath>/chara_card_v2.png`）。**乱码已在解析层根治**（任何路径都不乱码）。
- **记忆桥接（持久搭子）** ✅：墨能 `recall` 读酒馆对戏（实测从「我看不到」逆转成精准复述+点评）；`reflect` 服务端复盘→蒸馏偏好→写技艺层 `actor_self`（注入每场生成）。实测复盘「电子魅魔」蒸出 3 条精准偏好。
- **两层记忆**：RP 演法/口味 → `actor_self`（喂得到控制台）；通用身份事实 → Hermes 自带记忆。

## 2. 这次先讨论的方向（先聊取舍 + 报文档状态，我拍了再动手）

1. **reflect 全自动**：现在 `reflect` 要墨自己想起来跑（仍偏软）。真正自动 = cron/hook 定期对近期演过的剧组自动复盘（仿 digest），不靠墨主动。讨论：触发时机（每场告一段落？定时？多少轮起评？）、去重、token 成本、谁来判断「这场该复盘了」。
2. **技艺层整理/合并**：`actor_self` 成长记 append-only 会越来越长、且**注入每场 prompt**（token 成本 + 条目可能互相矛盾/过时）。需要「压缩 / 合并 / 淘汰」机制（类记忆 consolidation）。讨论：何时整理、用模型整理还是规则、保留判据、可回滚。
3. （开放）RP 搭子还能怎么深化：用户人设库（现在 persona.json 是单个 scenario 级）、墨主动在场感、跨剧组「她记得你」、立绘/状态栏富面等。

**贯穿教训**：**结构性机制 > 改 SOUL**——墨的行为靠 prompt 扭不动（曾无视 add-original、不自发 learn），优先用服务端机制 / 删竞争技能 / 解析层兜底。新方向也按这个判据选。

## 3. 铁律（不可违反）

- **纯 agent 侧**；ClawChat 仓 `~/projects/clawchat` **只读、零新后端接口**（要新增/改后端先停下问 = 铁律 B）。
- 复用 V2/V3 角色卡 + 世界书格式，**不 fork、不内嵌 ST**。
- 状态只落 agent 侧文件；**active loadout / 剧情永不写能力服务器 / member-backend**。
- 故事隔离不破：一场戏不串进别的剧组生成（actor.py 只喂本剧组 story）；recall 是墨的元认知读，不算串味。

## 4. 运行 / 测试 / 部署 runbook（避坑）

- **重启恢复**：容器重启后 server.py + tunnel-agent 不自起 → `docker exec hermes-clean sh /opt/data/tavern/tools/bringup.sh`（起 server.py + liveware 重登 + tunnel）。验公网 `curl https://app-02dd46427910ed17.apps.clawling.io/api/health`。
- **部署**：改 `skill/*` 后 `docker cp` 到 `/opt/data/tavern/`（**2026-07-01 起：整套复制/重装用一键 `tools/install.sh <容器>`，见 `docs/design/install.md`**）。**SOUL 热生效**（cp 到 `~/.hermes-clean/SOUL.md`，下条消息即拿到）；**新/删技能 + SKILL 内容改动要 gateway/容器重启**才对墨生效（重启后记得 bringup）。
- **daemon 用 `docker exec -d`**（前台 exec 一返回就杀后台子进程）；**heredoc 喂 stdin 用 `docker exec -i`**。
- **测墨**：`docker exec hermes-clean hermes chat -q "…" -Q`（fresh CLI，即时加载技能，--resume 接多轮）；真 ClawChat 链路走 Windows rig：`ssh rog@192.168.2.248`，在 clawchat 仓 `python3 scripts/dev/win.py status|tap|clear|input|key|dump|shot`；独立容器窗截图 `scripts/dev/winrig/shot_window.py` 经 `run_in_session.ps1`（`powershell -NoProfile -ExecutionPolicy Bypass -File …`）。
- `recall`/`reflect` 也可直接在容器 `python3 /opt/data/tavern/tools/tavern_cli.py …` 验。
- `reflect_on_play` 的「别重复」context 只喂「我对你的了解+成长记」段，**别灌整个 actor_self**（会让模型误判已知→NONE）。
- 容器日志 UTC（+8=北京）。`hermes skills uninstall` 只管 hub 技能；local 技能直接 `rm` 目录。模型 key 在容器 `/opt/data/.env` 的 `DEEPSEEK_API_KEY`。

## 5. 提交

tavern 独立仓，提交到 `main`（无 remote、不 push；「不动 main」那条铁律是 ClawChat 仓专属，不适用这里）。「提交吧」= commit。`state/` 已 gitignore。提交信息结尾带 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。
