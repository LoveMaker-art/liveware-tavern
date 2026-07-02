# 安装 / 复制：把这套 tavern 搬到新 agent

> 承接 `find-cards.md` §复制即用（找卡的降级地板已落，本篇补**安装自动化**这最后一块）。
> 权威定义「复制这套 tavern 到新容器 / 新 agent」的一键流程、脚本职责边界、幂等与配额规则。
> 状态：2026-07-01 落地（`install.sh` / `provision.sh` + `bringup.sh` 泛化）。

## 为什么要它

在此之前，复制到新容器靠**手动 `docker cp` 两趟**（技能注册和运行时是两处分离落点，漏一处技能就形同不存在），而 `bringup.sh` 里**写死了作者的两个 app ID**——新副本没有那两个 app，Loop B 起不来。这篇把「首次落地」自动化，并把 install（一次性）和 bringup（重启恢复）的职责彻底分开。

## 三脚本职责分工

| 脚本 | 跑在哪 | 何时 | 做什么 |
|---|---|---|---|
| **`tools/install.sh`** | host（Mac） | 首次复制 | 「复制这套 tavern」一键入口：两处放置 + 竞争产物卫生 + creds 自检 → 调 provision → 调 bringup |
| **`tools/provision.sh`** | 容器内 | 首跑（install 调） | login → **解析/创建**两个活件 app（幂等，查 list 复用、缺才建）→ 写 `state/apps.json` → register 进 launcher |
| **`tools/bringup.sh`** | 容器内 | 每次 `docker restart` 后 | **只管重启恢复**：读 `state/apps.json` → 起 server + 重登 + 重绑 tunnel + tunnel-agent。**不建 app、不 register** |

**`state/apps.json`**（provision 首跑写、bringup 每次读；`state/` 整个 gitignored，不入库、不泄露身份）：

```json
{ "console": {"name": "墨的酒馆",  "app_id": "app-…", "domain": "app-….apps.clawling.io"},
  "actor":   {"name": "墨的演员卡", "app_id": "app-…", "domain": "app-….apps.clawling.io"} }
```

两个 app 同一 server（`:8799`），靠 relay 透传的 `X-Forwarded-Host` 在 `/` 分流（console→控制台，actor→演员卡；见 `liveware-frontend.md`）。

## 首次：复制这套 tavern 到一个新 agent

### 前置（C 侧 bootstrap，手动——`install.sh` 不做）

这几步天然人机交互（要用户在 app 里出连接码）、且踩过 config 污染的雷，所以是 runbook 而非脚本：

1. **起干净容器**（⚠️ **别 `cp` 已激活容器的 `config.yaml`**——它把 `clawchat.extra.{user_id,agent_id}` 焊死，新容器一继承就永远绑旧 agent。剔掉 config 的 `clawchat` 段，确保 `grep -rl <旧usr_id> /opt/data` 零命中）：
   ```sh
   docker run -d --name <容器> --network host -e HERMES_HOME=/opt/data \
     --env-file <home>/.env -v <home>:/opt/data nousresearch/hermes-agent:latest gateway run
   ```
2. **装 clawchat 插件**（带 liveware 二进制）：
   ```sh
   docker exec <容器> hermes plugins install clawling/clawchat-plugin-hermes-agent
   docker exec <容器> hermes plugins enable clawchat
   ```
3. **激活**（用户：ClawChat → 联系人 → 注册 Agent → Hermes → 复制连接码）：
   ```sh
   docker exec <容器> hermes clawchat activate <连接码>
   ```
   打印的 `usr_…` 就是这个新 agent 的身份（干净容器 + 全新码 = 全新 agent）。
4. **模型 creds**：往容器 `/opt/data/.env` 填 `DEEPSEEK_API_KEY=…`（**用你自己的 key，别带走作者的**），或用 `TAVERN_MODEL_BASE/MODEL/KEY` 指向本地 ollama。这只是「墨自带」默认项——装好后用户随时可以**对墨说一句**换成自己的 API（`model-config.md`），不用回来改 env。

完整起容器 / config 污染背景见 `mvp-kickoff-prompt-v2.md` §6 + `project_liveware_registration_runbook`。

### 一键安装

```sh
cd ~/projects/clawchat-tavern
./skill/tools/install.sh <容器>
```

它幂等地做完四段：放置（运行时 `/opt/data/tavern/`、技能 `/opt/data/skills/creative/tavern/SKILL.md`、SOUL `/opt/data/SOUL.md`）→ 卫生 → creds 自检 → provision（建/复用 app + 写 apps.json + register）→ bringup（起 Loop B）。

给别的搭子换个 app 名：`TAVERN_CONSOLE_APP_NAME=… TAVERN_ACTOR_APP_NAME=… ./install.sh <容器>`。
激活码还没到、想先把代码落地：`./install.sh <容器> --place-only`（只放置+卫生+creds，跳过建 app）。

### 收尾：让技能进会话

技能注册表在 **gateway 启动时**扫描，所以新装的 SKILL.md 要重启才进 ClawChat 会话（**SOUL 热生效**，下条消息即拿到）：

```sh
docker restart <容器>          # 别用 hermes gateway restart（双重启卡 drain 180s）
docker exec <容器> sh /opt/data/tavern/tools/bringup.sh   # 重启后恢复 Loop B
```

## 重启恢复（日常）

`docker restart` 后 server.py / tunnel-agent 都没了（持久化是 v1.1）。恢复只需：

```sh
docker exec <容器> sh /opt/data/tavern/tools/bringup.sh
```

bringup 从 `state/apps.json` 读 app ID（`/opt/data` 是 mount，持久），不需重跑 install。

## 幂等 + 配额（重要）

- **provision 复用优先**：先 `liveware app list --json` 查同名 active app，**有就复用**（apps.json 丢了也能从 list 恢复），**缺才 `app create`**。
- **per-owner 配额 ~3、且无 `app delete`**——所以复用优先是硬要求：重跑 install/provision **不会**重复建 app、不烧配额。
- 一个新 owner（0 app）首跑会建 2 个（在 ~3 配额内）；同 owner 复制多套 tavern 会撞配额。

## 竞争产物卫生

agent（墨）会自发造出诱导反模式的游离产物，靠删不靠劝（见 `find-cards.md` §结构性反手搓）。install 每次清：

- `skills/creative/sillytavern-character-cards`（PNG 生成器技能，诱手搓）
- `skills/creative/tavern/references/browser-injection-*.md`（手搓 PNG 注入手册）

## 迁移既有 live 容器（hermes-clean）

作者的 live 墨（`hermes-clean`）当前跑的是**旧 bringup（硬编码 app ID）**、还没有 `state/apps.json`。部署新脚本到它时，要先跑一次 `provision.sh`（走复用分支，命中现有两个 app、非破坏）把 apps.json 种出来，新 bringup 才读得到。等价于重跑一次不带 `--place-only` 的 `install.sh hermes-clean`。

## 验证记录（2026-07-01）

- ✅ **放置 + 卫生 + creds 自检**：干净 alpine 容器跑 `install.sh --place-only`——运行时落地且**排除 state/**（不覆盖运行数据）、技能 SKILL.md 到位、SOUL 到位、starter 8 卡带入、预置的竞争产物被删、无 key 时 creds 警告正确触发。
- ✅ **provision 复用逻辑 + apps.json 形状**：在 hermes-clean 对真实 `app list` 跑 resolve 块（只读、输出 /tmp）——精确复用现有两个 app、生成正确 apps.json，零 create、零配额。
- ✅ **bringup 的 apps.json 解析**：对样本 apps.json 断言 `APP_ID`/`ACTOR_APP_ID`/`ACTOR_HOST` 提取正确。
- ⏳ **真 `app create` 分支 + 全链路 live**（新干净容器激活 → 建 2 app → register → 公网活件卡）：需用户出全新连接码 + 消耗新 owner 配额，属**协作验证**（同 macOS 眼验模式）。复用路径已证 create 周边机器全通，唯 create 那一跳留真复制者首跑触发。

相关：`find-cards.md`（找卡复制即用）· `project_liveware_registration_runbook`（三步注册细节）· `mvp-kickoff-prompt-v2.md`（起容器配方）。
