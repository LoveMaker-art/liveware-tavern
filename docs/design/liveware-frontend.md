# 活件前端设计语言（reader design system）

> **为什么这份存在**：tavern 活件的前端（`skill/reader/`）**不是一次雕死的成品，是墨（agent）会自行二创的底料**——「活件 = 活的软件，前端 agent 可自行修改」。这份把设计**规范 / 命名 / 意图**标清楚，让 agent 后续改得对、不破坏设计语言。
> **权威范围**：`skill/reader/` 的**所有页面**（控制台 `console` + 演员卡 `actor-card`）的视觉/命名/交互底座。**承接**：`surfaces-and-features.md §B`（沉静感 / 空气感 / 渐进披露）、`conversation-surface.md`（对话手感）。那两份定**有哪些功能 / 怎么对话**，这份定**长什么样、类怎么命名、怎么安全改**。
> **状态**：2026-07-01 起。

---

## 0. 给二创 agent 的一句话

你在改一个 **暖纸质感、单一品牌橙、serif 叙事、渐进披露** 的**沉静阅读**界面。动手前先读第 1–3 节（原则 / token / 组件）。**加东西一律先复用既有 token 和组件类**：别引入新色、别加第二种字体族、别用原生手势（长按/侧滑）。加一个新 surface（如演员卡）= 新 `.html` 复用 `console.css` 的 token 与组件 + 在第 5 节登记 + 写对应 spec。

---

## 1. 设计原则（canon，改动必须守）

承接 `surfaces-and-features.md §B` + `conversation-surface.md`，落成前端可执行的 7 条：

1. **暖纸质感（warm paper）**：底色是暖白（`--bg #f6f3ec`），不是纯白/纯灰。整体像书页，不像"聊天 app"。
2. **单一品牌橙强调**：`--brand` 是**唯一**强调色（活件 ✦ 同源）。要强调用它，**别引入第二强调色**。
3. **serif 叙事 vs sans 界面**：入戏的**叙述**文本用 `--serif` 斜体 muted（`.nar`）；一切 **UI 家具**用 `--sans`。这个反差是"书页感"的来源，别混用。
4. **沉静 · 空气感**：留白大、chrome 克制、让叙事呼吸。新增控件先问"能不能不常驻"。
5. **渐进披露**：控制项默认隐/ghost，**桌面 hover 显、触屏常驻低透明**（`.ctl` / `.prodDel` 已是范式）。触屏无 hover 通道，**别把控件藏在 `:hover` 后面就完事**。
6. **web reader ≠ 原生 app**：reader 是 webview 里的**网页**。用**看得见、可点**的控件；**别用长按 / 侧滑 / 3D touch**（在 webview 里被浏览器占用 = 文字选择/放大镜，且用户不对网页长按）。详见 `surfaces-and-features.md`「web reader ≠ 原生 app」。
7. **明暗镜像**：每个色 token 在 `@media (prefers-color-scheme:dark)` 有对应值。**改一个色 = 改亮暗两处**，否则暗色漂移。

---

## 2. Design tokens（`:root`，角色 + 二创守则）

**唯一色/字体/尺寸来源就是 `console.css` 的 `:root`。改样式先看这里有没有现成 token；缺了先加 token 再用，别在规则里硬编码色值**（对齐 ClawChat「消费 token，不用裸值」的精神）。

| token | 亮 / 暗 | 角色 · 用途 | 二创守则 |
|---|---|---|---|
| `--bg` | `#f6f3ec` / `#15140f` | 页面底 = 暖纸 | 大面积底色只用它 |
| `--surface` | `#fffdf8` / `#1d1b15` | 抬起面（顶栏/栏/卡/弹层） | 需要"浮起一层"就用它 |
| `--ink` / `--ink2` | 主文 / 次文 | 正文两级 | 标题用 `--ink`，正文/次要用 `--ink2` |
| `--muted` | 弱文 | 副标题/元信息/叙述 | 最低对比的文字（时间戳、`.nar`、`.pHead`） |
| `--line` / `--line2` | 细线 / 略重线 | 分隔/描边 | 分区用 `--line`，输入框/标签描边用 `--line2` |
| `--brand` / `--brandink` | 品牌橙 / 橙墨 | **唯一强调色** / 橙文字 | 强调、✦、active、主按钮。`--brandink` 是可读的橙文字 |
| `--brandtint` / `--brandtint2` | 橙淡底 | active 背景/徽标底 | 需要"淡橙一片"用它，别用半透明硬调 |
| `--danger` / `--dangerink` | 危险红 | 删除/破坏性 | 仅破坏性动作 |
| `--userbg` | 用户气泡底 | 用户输入后退弱化 | 只给 `.user .body` |
| `--radius` | `14px` | 标准圆角 | 卡/大块用它；小控件可 9–11px |
| `--shadow` | 大柔阴影 | 浮层投影 | 弹层/抽屉用，别滥用 |
| `--serif` | 宋体族 | **叙事体** | 只用于叙述/入戏/thinking，别用于 UI |
| `--sans` | 系统 sans | **界面体** | 一切 UI 家具 |

---

## 3. 组件词汇表（按 surface 分，每个一句用途）

**布局骨架**（`index.html`）：`#topbar`（顶栏：`✦ + 剧组名`居中 `.topTitle`/`.tline`/`.prodName`/`.prodSub` + 移动抽屉开关 `.iconbtn`）· `#layout` = `#rail`（左栏剧组）｜`#stage`（中舞台）｜`#panel`（右信息面板）· overlays `#scrim`/`#modal`/`#toast`。桌面三栏并排，`≤760px` 时 `#rail`/`#panel` 变抽屉（`.open`）。

**左栏 · 剧组（rail，前缀 `prod*`）**：`.prodList`>`.prodItem`（`.active` = 左 accent 竖条 + 淡橙底）· `.prodName2`/`.prodMeta`（名 + 数值行）· `.prodDel`（删除 = 可点 trash，非长按）· `.railacts`>`.btn`（`.ghost` = 次级）· `.pastePanel`/`.cardPicker`（导入旁路）。

**中栏 · 舞台（stage）**：`.convo`>`.thread`（窄栏居中 486px 阅读宽）· `.turn`（`.char` 干净文本块 / `.user` 后退气泡）· `.body`/`.nar`（叙述 = serif 斜体 muted）· `.ctl`（渐进披露控制条）· `.swipe`（`‹ i/n ›` 备选回复）· `.editbox`/`.editacts`（行内编辑）· `.composer`>`textarea`+`.sendbtn`（`.empty` 静默 / `.stop` 早停）· `.empty`/`.emptyMark`（空态）· `.thinking`（生成中）。

**右栏 · 信息面板（panel，前缀 `p*`）**：`.pSection`/`.pHead`（分区 + 小标题）· 角色：`.cname`/`.prov`（来源出处）/`.cdesc`/`.ctags`>`.tag` · 世界书：`.lore`/`.lk` · **演员墨技艺层**：`.actorHd`/`.lvBadge`/`.knowHd`/`.knowList`/`.growRow`/`.actorMore`（"我对你的了解"+"成长记 N 条"+展开手记）· `.lwFoot`（活件版本 footer）。

**弹层**：`.modal`>`.modalCard`（二次确认：`.modalActs`/`.mBtnCancel`/`.mBtnDanger`）· `.sheetCard`（大卡如演员手记）· `.md`（渲染 markdown：`.mh`/`.mp`/`.mli`）· `.hidden` 通用隐藏。

> **代码里已在做的**：每个组件块 CSS 上方有一行注释写**用途 + 链回它落实的 doc 段**（如 `conversation-surface §3.1`）。**二创时延续这个习惯**——加块就加这行注释，是给下一个 agent 的路标。

---

## 4. 命名约定（加新东西照这个来）

- **按 surface 前缀**：剧组 = `prod*`、演员卡 = `ac*`、面板基元 = `p*`、手记 markdown = `m*`。新 surface 起一个短前缀，别和现有撞。
- **BEM-lite 小驼峰**：块 + 元素扁平命名（`.actorHd`/`.knowList`），不堆多级。
- **状态类固定词**：`.active`（选中）/`.open`（抽屉开）/`.hidden`（隐）/`.empty`（无内容静默）/`.stop`（发送中）/`.ghost`（次级）/`.dragging`（拖入高亮）。复用这套，别新造同义词。
- **id 给唯一节点，class 给样式/复用**：JS 抓取用 `#id`，视觉用 `.class`。

---

## 5. 页面清单（surface registry — 加/改 surface 必须更新这张表）

| surface | 路由 | 是什么 | 命名前缀 | 权威 spec |
|---|---|---|---|---|
| **console** | `/` | 剧组管理台（导卡/切换/沉浸对话/角色·世界书·演员面板） | `prod*` `p*` | `surfaces-and-features.md` + `conversation-surface.md` |
| **actor-card** | `/actor` | 墨的**演员卡**（养成感 surface：生涯数值/亲密度/我对你的了解/生涯年表） | `ac*` | `actor-card.md`（待建） |

两个 surface 由**同一个 `server.py` 服务、共享 `console.css` 的 token 与组件**，但**各注册为一个独立 liveware app**（`liveware app create` ×2：`墨的酒馆` → console、`墨的演员卡` → actor-card），所以活件入口**看到两张卡**。

**两 app 一 server 的分流机制**：两个 app 的 tunnel 都 `bind` 到同一个 `http://127.0.0.1:8799`，server 靠 relay 透传的 **`X-Forwarded-Host`**（原始 app 域名；`Host` 被 relay 改成 `127.0.0.1`）在 `/` 上分流——演员卡 app 域名的 `/` → `actor.html`，否则 → `index.html`。演员卡 app 域名存在 `state/actor_host.txt`（`_actor_host()` 每请求读，重启/bringup 不丢）；两个 app 的 ID/域名则由 `provision.sh` 首跑写入 `state/apps.json`（bringup 读它拿 app ID、不再写死；安装/复制流程见 `install.md`）。任一 app 域名 + `/actor` 直达路径也保留。墨拿演员卡链接：`tavern_cli.py card` 末尾的 `演员卡活件：https://…`（来自 `/api/actor_card` 的 `actor_url`）。

---

## 6. 二创工作流（agent 怎么安全改前端）

1. **改样式**：只动 `:root` token 或既有类；缺 token 先加 token（第 2 节），**别在规则里写裸色值**。改色记得亮暗两处（原则 7）。
2. **加 surface**：新 `.html` + 复用 `console.css` 的 token/组件 + 起 `ac*` 式前缀 + **在第 5 节登记** + 写/更新它的 spec doc。
3. **加控件**：先问能不能走渐进披露（原则 4/5）；触屏要可达（`@media (hover:none)` 常驻）；别用原生手势（原则 6）。
4. **改功能 = 活件发版**：升 `SKILL.md` 的 `version`（reader footer `.lwFoot` 会显），这是**应用层**版本，**与演员技艺层（`actor_self.md`）的成长是两回事**——别混（见 `v1-build-spec.md §3`）。
5. **部署坑**：relay 对 `.js/.css` 强缓存 → `server.py` 已做**版本化资源 URL**（`?v=<mtime-token>`）；改 reader 后走部署 runbook，别用 `?v=时间戳` 手测自欺（详见 `project_tavern_experience_gaps` runbook）。

---

## 术语表（词汇 canon —— 二创/文案不许混用）

演员模型的词很容易混，混了就出逻辑 bug（如把"演过的角色数"错叫"搭档数"）。**这几个词的意思钉死**：

| 词 | 指 | 不是 |
|---|---|---|
| **演员 / 墨** | 那个能钻进任何角色的持久身份 | 不是某个角色 |
| **角色 / 戏路** | 墨出演的角色卡（凛、林夏…）；"戏路 N" = 演过 N 个角色 | **不是"搭档"** |
| **搭档 / 对手戏** | **用户**（跟墨演对手戏的人，`persona` 是 ta 在戏里的身份） | 不是角色卡 |
| **口味 / 我对你的了解** | `actor_self.md`「我对你的了解」段：**合并、有界**的偏好档 | 不是流水账 |
| **生涯年表 / 成长记** | `actor_self.md`「成长记」段：**append-only 累计**的调整记录 | 不是"我对你的了解" |
| **亲密度** | 墨与**你（搭档）**的关系深度，由 `轮数 + 8×年表条数` 驱动 | 不由"口味条数"驱动（那个有界会饱和） |
| **技艺层 / 演员成长** | `actor_self.md` 整份（底色+口味+签名+年表），跨剧组注入生成 | ≠ **活件版本**（app 发版号，`SKILL.md version`） |

> 一句话记忆：**墨（演员）演角色（戏路），陪你（搭档）演；越演越懂你的口味，一路的调整记进年表，年表越长你俩越亲密。**

## 7. 头像 / 品牌标记（占位与二创边界）

- **✦（品牌橙星）= 活件归属标记**，launcher 瓦片 / 活件卡 / reader 顶栏 / 演员卡同一个 ✦，`--brand` 着色。**这是锚，别替换**。
- **墨的"演员肖像"暂用 ✦ 占位**。未来由**墨（agent）自己**决定——可能改成它自己的 ClawChat 头像，交给 agent + 用户定。二创时：肖像是**可换的皮**，✦ 品牌标记是**不可换的锚**，别把两者搞混。
