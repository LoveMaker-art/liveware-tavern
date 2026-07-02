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
8. **app 质感（是 liveware，不是网页；反馈 2026-07-02）**：原则 6 管**输入**（别学原生手势），这条管**手感**——别露网页马脚。已落地且**加新东西必须延续**的一揽子：UI 家具不可选中（`body user-select:none`，正文/输入白名单恢复 `text`）、禁用户缩放（viewport `maximum-scale=1` + `touch-action:manipulation`，两页 `.html` 同款）、页面不橡皮筋露底（`overscroll-behavior:none`，滚动区 `contain`）、无 tap 高亮（`-webkit-tap-highlight-color:transparent`）、按压有反馈（触屏没有 hover，交互件都有 `:active` 态）、弹层/toast 带浮现缓动、composer 垫 `env(safe-area-inset-bottom)`（键盘在场时 `body.kbd` 收掉）、抽屉**全高覆盖**（`top:0`，不给顶栏留缝）、移动输入字号 ≥16px（防 iOS 聚焦自动放大）、滚动条暖纸化（`::-webkit-scrollbar` 8px 细条 + `--line2` thumb，系统黑块不许出现；autosize 输入框未到 max-height 保持 `overflow-y:hidden`，真超限才开滚——防 1px 误差冒常驻滚动条）。

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
| `--radius` / `--radius2` | `14px` / `10px` | 大块圆角（卡/弹层/气泡/编辑框）/ 控件圆角（按钮/列表项/toast） | 就这两档 + 胶囊 `999px`/正圆 `50%` 字面值；别的档位（如 composer 的 18px 胶囊输入）必须行内注释豁免 |
| `--scrim` | 半透黑背板 | 抽屉背板 + 弹层背板共用 | 别再写第二个 rgba 黑 |
| `--shadow` / `--shadow2` | 大柔阴影 / 无方向环影 | 弹层投影 / 抽屉侧影（左右抽屉共用一个无方向值） | 弹层用前者、抽屉用后者，别滥用 |
| `--serif` | 宋体族 | **叙事体** | 只用于叙述/入戏/thinking，别用于 UI |
| `--sans` | 系统 sans | **界面体** | 一切 UI 家具 |

---

## 3. 组件词汇表（按 surface 分，每个一句用途）

**布局骨架**（`index.html`）：`#topbar`（顶栏：`✦ + 剧组名`**绝对居中** `.topTitle`/`.tline`/`.prodName`/`.prodSub`——两侧按钮数随断点变，flex 配不平——+ 抽屉开关 `.iconbtn`，图标一律**内联细描边 SVG**，与 app.js 图标同族，别用 ☰/ⓘ 类字符）· `#layout` = `#rail`（左栏剧组）｜`#stage`（中舞台）｜`#panel`（右信息面板）· overlays `#scrim`（`.show` 渐显）/`#modal`/`#toast`。**断点两段收纳**：`≤1020px` 右 `#panel` 先收成抽屉（保住 486 阅读栏）+ ⓘ 现身；`≤760px` 左 `#rail` 也收，进移动全屏舞台。抽屉（`.open`）= **全高覆盖**（`top:0` 盖过顶栏，内衬 safe-area，原则 8）。

**左栏 · 剧组（rail，前缀 `prod*`）**：`.prodList`>`.prodItem`（`.active` = 左 accent 竖条 + 淡橙底）· `.prodName2`/`.prodMeta`（名 + 数值行）· `.prodDel`（删除 = 可点 trash，非长按）· `.railacts`>`.btn`（**唯一主按钮 = 导入角色卡**）+ `.railsub`（次级一行小字链接：粘贴卡 JSON · 从已有卡新建——旁路/复用路不配常驻大按钮）· `.pastePanel`/`.cardPicker`（导入旁路）。

**中栏 · 舞台（stage）**：`.convo`>`.thread`（窄栏居中 486px 阅读宽；**回合节奏** = 同回合内「我的话→墨的回复」14px 收紧、回合间 30px 放松——段落 vs 场景的呼吸层次）· `.turn`（`.char` 干净文本块 / `.user` 后退气泡）· `.body`/`.nar`（叙述 = serif 斜体 muted）· `.ctl`（渐进披露控制条；触屏热区用 padding+负 margin 撑到 ~28px，视觉行高不变）· `.swipe`（`‹ i/n ›` 备选回复）· `.editbox`/`.editacts`（行内编辑）· `.composer`>`textarea`+`.sendbtn`（`.empty` 静默 / `.stop` 早停；**空态整体隐藏**——没开戏没处发，导入引导是唯一动作）· `.empty`/`.emptyMark`（空态）· `.thinking`（生成中）。

**右栏 · 信息面板（panel，前缀 `p*`）**：`.pSection`/`.pHead`（分区 + 小标题）· 角色：`.cname`/`.prov`（来源出处）/`.cdesc`/`.ctags`>`.tag` · 世界书：`.lore`/`.lk` · **演员墨**（反馈 2026-07-02 收敛为两个入口——摘要/手记撤，完整呈现归演员卡）：`.pLink`（panel 通用入口行）× 2 = **找墨复盘**（深链 `clawchat://u/{id}?chat=1&draft=复盘「剧组名」这场戏` 跳与墨的会话，draft 预填进输入框给墨定位关键字、只填不发；须是真 `<a>`——移动容器只放行带手势的链接点击；拿不到墨身份时隐）+ **墨的演员卡**（同源 `/actor?from=console` 页内直达）· `.actorMore`（小字操作钮，「切换 / 管理」在用）· **大模型**（`model-config.md`）：`.mdlCur`/`.mdlModel`（当前配置一览）+ 管理 sheet `.mcItem`/`.mcName`/`.mcMeta`/`.mcCheck`/`.mcDel`（tap=切换、trash=删，`prodDel` 同款渐进披露）/`.mcHint`（教育文案 = 添加入口，**没有表单**——添加只走「对墨说」）· `.lwFoot`（活件版本 footer）。

**弹层**：`.modal`>`.modalCard`（二次确认：`.modalActs`/`.mBtnCancel`/`.mBtnDanger`；浮现带缓动 `modalIn`）· `.sheetCard`（大卡如大模型管理；**打开前先收抽屉**——别叠三层灰）· `.hidden` 通用隐藏。

**演员卡 · 数值格（`actor.html`，前缀 `ac*`，spec 待建先记这）**：`.acStatV`+`.acStatU`（值 + **单位小字**：「3 天 / 出道」连读成词，标签单看也成立——数值不许无单位裸奔，养成进度同理「还差 N 轮戏」）· 亲密度**只住自己那张卡**（`.acIntimacy`），不进数值格重复连显 · 版本 footer 文案 = `活件 · 酒馆 v<版本>`（**v 前缀两 surface 一致**，console `.lwFoot` 同款）。

> **代码里已在做的**：每个组件块 CSS 上方有一行注释写**用途 + 链回它落实的 doc 段**（如 `conversation-surface §3.1`）。**二创时延续这个习惯**——加块就加这行注释，是给下一个 agent 的路标。

---

## 4. 命名约定（加新东西照这个来）

- **按 surface 前缀**：剧组 = `prod*`、演员卡 = `ac*`、面板基元 = `p*`、大模型配置 = `mc*`/`mdl*`。新 surface 起一个短前缀，别和现有撞。
- **BEM-lite 小驼峰**：块 + 元素扁平命名（`.mcItem`/`.acKnow`），不堆多级。
- **状态类固定词**：`.active`（选中）/`.open`（抽屉开）/`.hidden`（隐）/`.empty`（无内容静默）/`.stop`（发送中）/`.ghost`（次级）/`.dragging`（拖入高亮）。复用这套，别新造同义词。
- **id 给唯一节点，class 给样式/复用**：JS 抓取用 `#id`，视觉用 `.class`。

---

## i18n（界面语言，2026-07-02）

**机制**：全部界面文案住 `reader/i18n.js` 的 `STRINGS`（纯 JS 字典，`t(key, params)` 取用）；静态节点走 `data-i18n*` 属性（`applyStatic` 填），动态节点 JS 里 `t()` 拼。语言由 **locale contract** 决定：容器打开活件时 URL 带 `?lang=<app语言>`（clawchat 仓 `docs/liveware/container.md` §语言）→ 存 sessionStorage（页内导航不丢）→ `navigator.language` 兜底（独立浏览器）→ zh；**未收录语言回落 en**（对齐 ClawChat 策略）。server 下发的 UI 标签（亲密度级名/blurb）由 `/api/actor_card?lang=` 按语言给（`INTIMACY_*_I18N` 表）。

**边界**：i18n 只管**界面家具**。墨写的东西（口味/年表内容/tagline/对话生成/角色卡）是**内容层，不翻**——内容语言跟人走，不跟界面走。

**二创守则**（墨加语言 = SKILL.md「帮用户加界面语言」）：① 加 locale = `STRINGS` 加全量 key 对象（拿 en 当模板）+ server 两张 `INTIMACY_*_I18N` 表加同 code 项；② 「Liveware」「✦」品牌锚不翻，「墨」用该语言自然写法（en=Mo）；③ `{x}` 插值占位原样保留；④ **CSS 里不写文案**（拖入提示走 `content:attr(data-drophint)`，JS 按语言设）；⑤ 不做语言切换按钮——语言选择是自动的（跟 ClawChat 设置）。

---

## 5. 页面清单（surface registry — 加/改 surface 必须更新这张表）

| surface | 路由 | 是什么 | 命名前缀 | 权威 spec |
|---|---|---|---|---|
| **console** | `/` | 剧组管理台（导卡/切换/沉浸对话/角色·世界书·演员面板） | `prod*` `p*` | `surfaces-and-features.md` + `conversation-surface.md` |
| **actor-card** | `/actor` | 墨的**演员卡**（养成感 surface：生涯数值/亲密度/我对你的了解/生涯年表；`?from=console` 时带返回钮） | `ac*` | `actor-card.md` |

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
