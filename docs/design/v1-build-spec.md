# 酒馆 v1 Build Spec（工程能照着搭，纯 agent 侧）

> 第一份"照着做"的文档。承接 `surfaces-and-features.md`（功能/特性 + 覆盖契约）+ `../research/feasibility-liveware-agent-channel.md`（通路绿灯）。
> **全部 grounded 在 digest 真实代码**：`clawchat-newsdesk/hermes/skills/digest/reader/bridge.js`(84 行) + `server.py`(652 行)。
> 状态：草案 2026-06-28。

## 0. 范围与铁律护栏

- **纯 agent 侧**：一个新 skill，目录布局仿 digest。**ClawChat 客户端零改、零新后端接口（铁律 B 不触发）。**
- **状态只落 agent 侧文件**，永不写能力服务器 / member-backend。
- **复用 V2 角色卡 + 世界书格式**（保留未知 `extensions` 键——V2 铁律），**不 fork / 不内嵌 ST**。
- **演员模型 creds 只在 server 侧**，页面永不见（照 digest 的 newsdesk-token 隐私墙）。

## 1. 架构总览：两个"agent 角色"

| 角色 | 是什么 | v1 焦点 |
|---|---|---|
| **演员运行时（actor runtime）** | 酒馆 skill 的 `server.py` + 一个 LLM client。管状态 + 拼 prompt（卡+世界书+故事+技艺）+ **入戏生成**。控制台同源只跟它说话 | **v1.0 主体** |
| **搭子会话 agent** | IM 联系人「墨」= 现有 hermes agent。出戏/试戏/主动冒泡在这 | v1.1 |

> **关键架构决定**：入戏生成跑在**演员运行时自己的 server 里（持一个模型 client）**，所以控制台聊天是**同步请求-响应**（POST → 拼 prompt → 调模型 → 返回回复 → 当场渲染），不绕异步 agent drain。这既让控制台像真聊天一样跟手，又把核心闭环**焊在最稳的同源 req/resp 上**（feasibility ①②④ 全绿那条），与有风险的 ③「主动推 IM」彻底解耦。

## 2. 代码骨架（仿 digest）

```
skills/tavern/
  server.py            # http.server，do_GET/do_POST，路由按 path（digest server.py:545）
  reader/              # 控制台 web UI（沉静感对话 + master-detail/全屏舞台）
    index.html  app.js  bridge.js  console.css  md.js
  card_import.py       # 吃 V2 PNG（chara chunk base64-JSON）→ card json
  actor.py             # 拼 prompt + 调模型 + 两层记忆喂法
  SKILL.md             # 演员 playbook（出厂行为、安全收敛）
  data-contract.md     # 状态文件契约
  state/               # 见 §3
```

## 3. 数据模型（状态文件，patch-merge JSON，仿 digest read/write_subscriptions:179-208）

```
state/
  cards/<card_id>.json + <card_id>.png   # 解析后的角色卡 + 原图（头像/立绘源）
  worldbooks/<wb_id>.json                # 世界书 entries[]
  productions/<prod_id>.json             # 剧组 = loadout + 故事线 + 故事记忆（隔离）
  actor_self.md                          # ★演员的「活·自画像」prompt（我们独有，跨剧组共享，会成长）
  actor_self.meta.json                   # 版本 / 更新时间 / 可回滚快照（成长纪律）
  persona.json                           # 用户人设
  state.json                             # { active_production_id, ... }
```

**card json**（V2 派生，保留未知键）：
```json
{ "id":"…","spec":"chara_card_v2",
  "name":"…","description":"…","personality":"…","scenario":"…",
  "first_mes":"…","mes_example":"…","alternate_greetings":["…"],
  "system_prompt":"…","post_history_instructions":"…",
  "tags":["…"],"creator":"…","character_version":"…",
  "avatar":"cards/<id>.png",
  "extensions":{ "__原样保留未知键__":true } }
```

**worldbook json**（机制字段存着，默认 agent 解释触发、不暴露 UI）：
```json
{ "id":"…","name":"…","entries":[
  { "keys":["水","雨"],"content":"凛怕水，一碰到就紧张","enabled":true,
    "insertion_order":10,"constant":false,"selective":false,"secondary_keys":[],
    "position":"before_char","source":"agent|import|user" } ] }
```

**production json**（故事线 = 这条剧组的隔离记忆）：
```json
{ "id":"…","name":"雨夜侦探事务所",
  "card_id":"…","worldbook_ids":["…"],"persona_id":"…",
  "created_at":"…","status":"active|archived",
  "story":[ {"id":1,"role":"narration|char|user","text":"…","ts":"…",
             "alts":["…"],"active_alt":0} ],
  "summary":"…" }
```

**actor_self.md**（★我们独有，ST 无等价物——它有静态 preset + 故事记忆 + 静态卡，但**没有会成长的持久演员**；见 §5 注）。演员的「活·自画像」prompt，跨剧组注入，**会成长**：
```markdown
# 我是谁（底色）
墨。话不多，爱用比喻，冷场会自己找台阶……      ← 出厂 persona = 物种基因库的种子

# 我对你的了解（个性化）
- 你喜欢短回复、留白，不爱长篇
- 偏爱悬疑/黑色，讨厌说教
- 边界：……

# 我的签名（跨角色的演法）
不管演谁，我都……                              ← 招牌手感

# 成长记（append-only，每条带人话理由）
- 2026-06-28 你说"别那么贫" → 收敛贫嘴密度
```
配套 `actor_self.meta.json`：`{version, updated_at, snapshots[]}`（可回滚）。**底色是共享基底（物种），「对你的了解 + 成长记」是你这份实例的个体进化**（liveware §两级进化）。

## 4. 同源事件协议（扩 digest 的 `bridge.js` + `server.py` 路由）

`bridge.send(event)` → POST `/api/event`，返回 `{ok, dryRun, data}`，离线优雅降级（bridge.js:78、57-74 原样复用）。`/api/health` → `{ok, dry_run}`（bridge.js:41 probe）。

| event | 语义 | server 返回 |
|---|---|---|
| `switch_loadout {production_id}` | 设 `state.active_production_id` | `production`（含 story）供渲染 |
| `send_message {production_id, text}` | 追加 user 行 → 演员运行时拼 prompt + 生成 → 追加 char 行 | `{reply, message}`（**同步**，控制台直接渲染） |
| `regenerate {production_id, message_id}` | 重生成该条，push 进 `alts` | 更新后的 message |
| `swipe {production_id, message_id, dir}` | 切 `active_alt` | message |
| `edit_message {production_id, message_id, text}` | 改文本 | message |
| `import_card {png_base64}` | 解析 V2/V3 PNG → 落 `cards/`（真实卡走这条，编码天然正确） | card |
| `import_card_json {card}` | 吃卡 JSON（V1/V2/V3 形态，**原创/结构化**导入，绕开手搓 PNG + `btoa(UTF-8)` 中文乱码坑） | card |
| `create_production {card_id, worldbook_ids?, persona_id?, name?}` | 新建 + first_mes | production |
| `import_worldbook {worldbook}` | 导入独立世界书 → 落 `worldbooks/` | worldbook |
| `attach_worldbook {production_id, worldbook_id}` | 把独立世界书挂到现有剧组（卡内嵌的在 create_production 自动挂） | production |
| `add_lore {worldbook_id?, entry}` | 加世界书单条目（**v1 计划，未实现**） | worldbook |
| `actor_grow {change, reason}` | 改写 `actor_self.md` 相应段 + 记一笔成长（带人话理由）+ 进 meta 快照 | actor_self |
| `actor_say {production_id, text}`（**v1.1**） | enqueue 进 IM 队列（仿 digest `DISCUSS_QUEUE` handle_discuss:271-279）→ 搭子 agent drain 后代发进 IM | `{queued:true}` |

读路由（GET，仿 digest read 路由）：`/api/cards`、`/api/worldbooks`、`/api/productions`、`/api/actor`。

### agent 侧「找卡 + 导卡」（`SKILL.md` + `tools/tavern_cli.py`，2026-06-29 加）

墨在聊天里能自己找卡 / 导卡，不靠用户在控制台上传，也**不该手搓 PNG / 跑 JS 怼 /api/event**（旧硬凑法会撞作用域错、`btoa(UTF-8)` 把中文搞乱码、世界书 Promise 不 resolve）。

- **来源 = Chub.ai**（角色卡事实标准库，6 万+，公开 API 免鉴权，墙内 Clash 实测可达）：搜 `https://api.chub.ai/search?search=…`；下载真卡 `https://avatars.charhub.io/avatars/<fullPath>/chara_card_v2.png`（带 chara chunk，喂 `card_import`）。
- **CLI `tools/tavern_cli.py`**（纯 stdlib，POST 本地控制台 `/api/event`）：`search "<q>"` / `add <fullPath>`（拉真卡→`import_card`→`create_production`）/ `add-original <json>`（`import_card_json`，原创卡）/ `add-worldbook <json> [--production]`（`import_worldbook`+`attach_worldbook`）/ `list`。
- **策略**：优先真源（存在的角色一律 `search` 拉真卡，绝不凭记忆瞎编）；只有用户明确要原创才 `add-original` 并标注「这是原创」。
- 容器注册路径 `skills/creative/tavern/SKILL.md`，**gateway 启动时扫描**（新加技能要 gateway/容器重启才进 ClawChat 会话；`hermes chat` fresh CLI 即时生效）。

## 5. 演员生成契约（actor.py —— ST 的 prompt builder，但藏起来）

拼 prompt = 角色卡（name/desc/personality/scenario/[system_prompt]，= 剧本）+ 用户人设 + 本剧组相关世界书条目（**agent 选，不靠死关键词扫描**）+ **本剧组故事线（隔离，只这条）** + **`actor_self.md`（演员自画像 prompt，= 演员，跨剧组共享技艺层）** → 调演员模型生成。即「**角色 = 演员 × 剧本**」落到拼装层。

- **故事记忆隔离**：只喂 `production.story`（绝不串别的剧组）。
- **技艺共享**：`actor_self.md` 注入每一个剧组——"搭子越演越懂你"的载体。**ST 无等价物（没有持久演员，只有一次性角色实例）= 我们的护城河。**
- **复杂功能→对话 + 成长**：`send_message` 文本若是元指令（"回复短点"/"凛怕水"），演员运行时识别 → `actor_grow`（改写 `actor_self.md`，进技艺层）或 `add_lore`，而非当剧情。**成长纪律**沿用 liveware 活·软件：间断平衡、大改先提案、可回滚、每次变更用人话记一笔。**v1.0 先用显式 `actor_grow`/`add_lore` 兜底；自然语言识别 = v1.1。**

## 6. 最薄切片 v1.0（焊死这条）

1. `import_card`：吃一张 Chub V2 PNG → `cards/`。
2. `create_production`：from card → `first_mes` → `productions/`。
3. 控制台渲染 `production.story`（沉静感）。
4. `send_message` → 演员运行时生成 → 渲染。**← 核心爽点：卡变搭子，在控制台入戏。**
5. `switch_loadout` 在多剧组间切（各自故事线）。
6. `regenerate`/`swipe`/`edit_message`（liveware 覆盖的常用控制）。

IM 侧 v1.0：演员联系人「墨」存在即可。**试戏 / 存成剧组 / 主动冒泡 = v1.1**（用 `actor_say` 队列）。

## 7. 待解 / 未知（建造中拍）

- **host 形态（已收敛）**：必须 agent 自托管**常驻 server**（有 `/api/*` 收 POST）——liveware-app 的 tunnel-bind-static 纯静态**出局**。
- **平台 relay 503**（registration.md）先疏通，真实控制台才跑得起来。
- **演员模型基座**：server 持一个 LLM client（creds server-side）。用哪个模型 = config seam（RP 文笔上限，社区共识 DeepSeek 稳 / Claude 文笔好）——v1 留接口，先接一个能跑的。
- **技艺层学习**：v1.0 先存 + 显式写；**自动从对话学偏好 = v1.1+**。
- **V3 / CHARX 导入**：v1 先吃 V2 PNG（最大公约数）；V3 后续。
