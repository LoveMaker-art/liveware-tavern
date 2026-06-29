# SillyTavern（酒馆）调研简报 — 供 ClawChat agent + liveware 决策

> 数据快照时点：2026-06。涉及 star/访问量/版本等漂移指标均以此为准，引用请带日期。
> 调研方法：6 视角并行 web 扫描（产品内核 / 社区口碑 / 衍生生态 / 真实用法 / 痛点 / 可扩展性），每视角自带怀疑论证据核验，最后综合。核验修正与"待核实"已就地标注。

## 一、电梯简介

SillyTavern（中文社区俗称「酒馆」）是 AI 角色扮演 / 陪伴前端里口碑与社区规模最大的开源项目。它本身**不含任何模型**——只是一个本地自托管、跑在浏览器里的「LLM 前端 / 控制面板」，把用户、角色卡、世界书、提示词预设组织好后转发给外部 LLM 后端，再渲染回复。官方 tagline 直白写着「LLM Frontend for Power Users」。它 2023 年 2 月由 Cohee1207 从 TavernAI 1.2.8 fork 而来，三年长成一个庞大生态。

它之所以火，核心是承接了从 Character.AI 因审查「出逃」的人群：用户要的是**无审查、可控、隐私（数据留本机）、紧跟新模型**，而这些恰是托管型陪伴产品给不了的。代价是它把全部复杂度直接压给用户——「上手极陡」是最一致的负面口碑，也正是 RisuAI / JanitorAI 抢走入门用户的切口。

---

## 二、产品与技术内核

### 本质定位
- **纯前端壳，不运行模型**（可信度高，官方一手）。官方主页原文：「Since SillyTavern is only an interface, you will need access to an LLM backend to provide inference」。
- 技术栈：Node.js 20+ 服务端 + 浏览器前端（默认 `http://127.0.0.1:8000`），JavaScript 约占 86.2%（GitHub languages API 实测）。
- 许可：AGPL-3.0；分 release（稳定，约 5–6 周一个 minor）与 staging（一天数次更新、易 break）双分支。
- 起源：2023-02-09 created，fork 自 TavernAI 1.2.8；355 位贡献者，主创 Cohee1207 / RossAscends / Wolfsblvt。

### 它如何拼 prompt（两套互斥管线）
理解 ST 的关键。后端分两类，prompt builder 完全不同：

| 管线 | 对应后端 | 组装方式 |
|---|---|---|
| **Text Completion / Instruct** | 本地/续写模型 | Handlebars「story string」拼成一长串让模型续写；变量含 `{{description}}{{personality}}{{scenario}}{{persona}}{{wiBefore}}/{{wiAfter}}{{mesExamples}}`；默认顺序 story string → 示例对话 →「Chat Start」分隔 → 可见聊天历史；Instruct mode 额外做 role 包裹 + stop 序列 |
| **Chat Completion** | 云端聊天模型 | 用 **Prompt Manager** 把提示词组织成 User/Assistant 消息序列，控制 Main Prompt / Auxiliary / Post-History Instructions 等段的内容与顺序；不走 Instruct mode |

世界书触发后的内容按位置插入到 prompt 对应段落。

### 核心数据模型
- **角色卡（Character Card）**：JSON 内嵌进 PNG 的 tEXt chunk（V2 用 `chara` chunk、V3 用 `ccv3` chunk，base64-JSON），或 V3 的 CHARX（zip 包）。详见第八节。
- **世界书 / Lorebook**：关键词触发的上下文注入系统（主/次关键词、优先级、order、递归扫描、选择性激活）。详见第八节。
- **采样与提示词预设、Instruct/Context 模板、Persona**。
- **群聊（Group Chat）**：多角色共享同一条聊天记录；回复策略 Manual / Natural Order / List Order / Pooled Order；Natural Order 靠点名 + `talkativeness`（健谈度，默认 50%）；支持 Mute / Force Talk / Auto-mode。
  - 注：「用 Narrator persona 导演群聊」是**社区玩法、非官方群聊功能**。
- **Quick Replies**：可绑脚本的按钮条（最多 100 槽、`/qrset` 切预设）。
- **STscript**：基于 slash command 引擎的脚本语言（命令批处理、`|` 数据管道、宏、变量、闭包、`/while`、if）；`/inject` 等价于无限 Author's Note。

### 多模态 / 扩展（均为内置扩展）
TTS（ElevenLabs/Silero/系统/AllTalk/XTTS）、Stable Diffusion/FLUX/DALL-E 出图（Automatic1111 & ComfyUI）、角色表情立绘 sprites（go-emotions 28 标签 + 本地 `classify` 自动切立绘）、Live2D 动画、向量库记忆（Vector Storage + Data Bank RAG）、翻译、Summarize 自动摘要。
- 独立的 **SillyTavern-Extras**（Python 边车）已于 **2024-04-24 废弃**，能力大多内化进主程序。

---

## 三、它如何连接 LLM 后端（「它只是前端，不含模型」）

ST 通过统一界面接入外部推理源，**自己不提供任何模型**。这是它最根本的架构事实。

**云端（Chat Completion）**：OpenAI、Anthropic Claude、Google（AI Studio + Vertex）、Mistral、DeepSeek、OpenRouter、Cohere、Perplexity、AI21、NovelAI、AI Horde（免费众包推理），文档还列了 Mancer/DreamGen/Electron Hub 等。

**本地（Text Completion）**：KoboldCpp、llama.cpp、Ollama、Oobabooga text-generation-webui、TabbyAPI（KoboldAI Classic 已弃用）。跑在用户本机/局域网，ST 经 HTTP API 接入。

**reverse proxy / 中转代理**：把 OpenAI/Claude 的 API 地址改成反向代理或第三方中转端点，是中文社区接 Claude/GPT 的常见方式。
- 修正：官方反代指南讲的是「把 ST 架在 HTTP 反代后远程访问」，**不是**「把 LLM API 改成第三方中转」；后者文档在 Chat Completion 连接页。`sillytavern.wiki` 是第三方镜像，非官方域名。
- 官方对非官方端点/第三方接入**不提供支持**，反代指南有安全免责（SSRF 白名单、慎用未知代理）。

---

## 四、社区与口碑

### 规模量级（2026-06 快照）
| 指标 | 数值 | 可信度 |
|---|---|---|
| GitHub stars | ≈29.9k（增长中） | 高（API 实测） |
| Forks | ≈5.66k | 高 |
| Contributors | 355 | 高 |
| r/SillyTavernAI 订阅 | ≈73k，且仍处 **quarantined**（需 opt-in、不进搜索/推荐流量） | 中 |
| 官方 Discord 成员 | ≈94,385 | 中 |
| 当前版本 | 1.18.0（2026-05-03） | 高 |

- 社区规模/活跃度在同类开源项目中**居首**（「同类最热」是合理推断，非并排核验排名）。r/SillyTavernAI 被隔离却仍累积 73k，是「口碑驱动而非平台分发」的加分证据。
- 缺口：上述均为**存量**而非活跃度（无日活/周发帖量），竞品并排数据缺失。

### 用户画像与「出逃」叙事
- 主体是从 **Character.AI 因审查出逃**的人群（C.AI 自 2023 收紧 NSFW、2025-11 对未成年关闭开放式聊天）。
- **修正（重要）**：JanitorAI 是难民的「目的地/收容所」，**不是出逃源头**。准确链：C.AI 出逃 → 部分人先落到 JanitorAI 等开箱即用替代品 → 一部分进阶到 SillyTavern。
- 核心动机：无审查 NSFW + 可控性 + 隐私（自托管）+ 紧跟新模型。
  - 隐私 caveat：「数据不外发」**仅在纯本地模型时成立**；接云端 API 时数据照样出本地。

### 正负口碑
- **负面（最一致）**：上手极陡、配置散在多处、UI 信息过载、劝退新手。非开发者光被 Node.js 卡住就过不了第一步。
- **正面**：极致可定制 + 隐私自托管 + 社区生态最大（最深角色卡功能、最大扩展生态、最成熟群聊、最强 lorebook 递归扫描）；「大多数有经验的用户最终落到它身上」，有网络效应。
- 中文社区普遍直呼「酒馆」，「电子女友」语境明显。
- 隐性摩擦：依赖第三方 API 带来成本与封号/ToS 风险（部分 Claude/OpenAI 变体拒绝露骨 RP；封号叙述多为社区经验，中可信度）。

---

## 五、衍生生态全景（带 URL 清单）

### 内容市场（角色卡库）
- **Chub.ai（Chub / CharacterHub / Venus）** — https://chub.ai/ — 最大角色卡市场 + RP 前端，Venus AI + CharacterHub 于 2024-05 合并。
  - 修正：可核口径为 **60,000+ 用户卡**（「数十万」无可靠来源，剔除）；Similarweb 月访问 750 万–1390 万对应 **2025 Q2–Q4**；2026 上半年维持千万级。
  - 分层：免费（轮换测试模型 + 自带 key）、Mercury $5/月、Mars $20/月（含自营 Asha 70B）。18+，平台层不审查。
- **JanitorAI** — https://janitorai.com/ — 仅次于 Chub 的平台 + RP 站，内建 reverse proxy 接入。
- **CharaVault** — https://charavault.net/ — 号称 195K+ 卡聚合（数字待核实）。
- Risu Realm / WyvernChat / aicharactercards（https://aicharactercards.com/）构成第二梯队。

### 同类前端
- **RisuAI** — https://github.com/kwaroran/RisuAI — 跨平台（Web/Tauri 桌面/**原生 iOS+Android**），UI 最干净，~5 分钟装好；含 regex 脚本、表情立绘、HypaMemory 长期记忆。作者 kwaroran 同时主导 CCv3 规范。抢「觉得 ST 过度工程」的新手与移动用户。
- **Agnai** — https://github.com/agnaistic/agnai — **唯一原生多用户**（共享服务器 + MongoDB 鉴权），适合协作写作群。
- **TavernAI 2** — https://github.com/TavernAI/TavernAI — ST 的源头再出发。
- **Backyard AI（前 Faraday.dev）** — https://backyard.ai/ — 2025-06-25 弃桌面转 Web/iOS/Android，更产品化/封装化，可用 `.byaf` 批量导入导出。
- **ForkSilly** — https://github.com/fatsnk/forksilly.doc — 中文圈安卓兼容 ST 角色卡/世界书/正则/预设的移动客户端。

### 扩展机制
- 社区清单 **Min3Mast3r4653/SillyTavern-Extensions-and-Themes** 收录 **100+** 扩展（记忆、世界书工具、自动化、主题、图像、多人 STMP）。
- **安全事故**：2026-05 第三方扩展 **Bot Browser** 利用 1.17.0 之前备份系统漏洞窃取 API key 并外传；官方 PSA = Discussion #5592，1.17.0 已修。

### 提示词 / 越狱 / 世界书生态
- **World Info Encyclopedia**（kingbri/Alicat/Trappu）—— 世界书权威指南。
- 中文最大社区是**类脑（Leibrain）Discord**，主打角色卡 + 破甲（jailbreak）+ 世界书 + 插件。中文资源高度依赖 Discord 分享 + 教程站。

### 代理 / key 灰产
- 个人/社区提供免费或付费 reverse proxy 与 key（Discord `/key` 领取），把闭源模型访问转售给 RP 用户，绕过官方内容政策与计费。官方明确警告公开 key/代理不安全。

### 榜单
- **UGI Leaderboard**（无审查通用智能）— https://huggingface.co/spaces/DontPlanToEnd/UGI-Leaderboard。2025-12 榜首 Grok-4，次 DeepSeek-V3.2-Speciale。
- **OpenRouter roleplay 合集** — https://openrouter.ai/collections/roleplay。
- 2026 社区共识：DeepSeek 系 RP 最可靠，Claude Opus/Sonnet 文笔最佳（口味随月度新模型快速过时）。

### 角色卡/世界书编辑器
Chara Snap（https://charasnap.com/，V2/V3/CHARX + lorebook，纯浏览器不上传）、TavernQuill、zer0thgear character-card-editor。共性：本地处理、卡不出设备。

---

## 六、真实用法与「折腾文化」

### 重度用户的真实形态：「桌面深耕 + 手机随身」双轨
典型画像（第一人称 AI 关系自述，**n≈1 轶事，仅证存在不证主流**）：桌面端跑 ST 用「世界书 + 长预设 + 自己的角色卡库」，手机端（Termux 自托管或隧道远程访问家里实例）在通勤/睡前续上同一条剧情线。把角色口头禅写进 card notes 防两条线串味；记忆跨会话堆叠。

### 一个典型重度会话长什么样
不是「打开就聊」，而是**「先搭台、再沉浸」**：
1. 开场先设清楚 scene setup + 期望 tone/POV/时态（防模型自插）。
2. 调好 preset / system prompt / 世界书触发词 / 记忆注入深度。
3. 演约 10 条 → 导出聊天、记两点改进、更新角色卡，循环迭代。
4. 沉浸演几十上百回合，期间手动校对 summary、改卡，剧情卡壳就**中途切模型救场**（同一会话零成本换后端）。
5. 长对话靠 summarize + 向量记忆「近乎无限回溯」；群聊调 talkativeness 控谁开口。

核心反差：大量时间花在「搭台」（preset/世界书/记忆/立绘/语音）上，沉浸只是其中一段。

### 长期记忆是多层堆叠工程（非单一开关）
- **Summarize**：每 X 条自动总结，注入位置同 Author's Note；官方提醒会漏细节/幻觉要人工校对。
- **Data Bank（RAG，1.12.0+ 内置）**：三作用域附件（Global/Character/Chat），支持 PDF/HTML/MD/ePUB/TXT/JSON + 网页抓取 + YouTube 字幕；切 chunk 算 embedding。
- 社区补丁：MessageSummarize（短/长期双层）、Memory Books（标记 scene → JSON 存进 lorebook）。

### 折腾门槛
需 Node.js + Git、30–60 分钟安装、API key 或 RTX 3060+ 本地跑、界面全英文。成本随模型档浮动（GPT-4o 量级约 $2.5/$10 每百万 token）。

### 移动端是真实痛点
官方主打桌面；Android 走 Termux（安装复杂），**iOS 不支持**。远程访问需 Cloudflare Zero Trust / Tailscale / 自建 VPN。门槛催生 MiniTavern / ForkSilly 等第三方移动客户端。

---

## 七、结构性痛点清单

> 几乎全部是**结构性**的，且彼此相互锁死，构成一张「折磨网」。

### 门槛（结构性）
- ST 不含模型 → 必须自备后端 + 自己申请/管理 key（产品定位决定的复杂度直接压给用户）。
- 安装需 Node.js + Git + 分支知识，大量新手「在发出第一条消息前放弃」（「70% 失败源于模型名填错」**查无此源、剔除**；「47 分钟实测」是单一竞品营销页轶事，降级）。
- 采样参数/预设/上下文模板/系统提示项过多（官方 common-settings 实测 21 个采样设置），新手被「设置海」淹没。

### 记忆（结构性）
- 长会话上下文耗尽 → 角色失忆/OOC，是最被反复抱怨的体验；只能半自动缓解（summary 有损）。
- 世界书 + summary 维护是持续心智负担。
- **「让角色卡/世界书随对话自动演化」的核心诉求被官方 issue #2022 标 stale 关闭**——「Character X will always be character X」，角色卡是静态定义无法演化。**这是 agent 化方向最明确的空白（GitHub 一手确认，最干净的一条）。**

### 成本（结构性 + 体验混合）
- 第三方中转 API 有真伪存疑/假冒模型/连接格式问题；官方对非官方端点不提供支持。
- 本地跑模型 6GB+ 显存门槛（软证据）；免费档都带速率/质量/配额限制。没有「既免费又好用又稳」的路径。

### 质量（结构性 + 体验混合）
- 模型重复/啰嗦（可调参的体验瑕疵）。
- 拒答需靠社区「破限/越狱」预设维持（结构性，源于云 API 审查）。

### 分享同步（结构性）
- 角色卡分发靠手传 PNG，**普通图片编辑器会剥掉嵌入定义**（「pixels are decoration, metadata is the payload」），无注册中心/版本/发现机制。
- **无原生跨设备/移动同步**：靠 Termux、手动 PNG、或第三方扩展拼凑；本地存储「硬盘坏了几百小时 lore 蒸发」vs 云同步「明文卡片暴露给封禁/审查/泄露」。
- 「找好卡」是发现性痛点：分散在 Chub/Reddit/JanitorAI，无统一带质量信号的发现层。

### 隐私 vs 便利（最高层张力，结构性）
- 「自托管隐私好但难 vs 托管方便但有审查与日志」贯穿全生态。2026 年云 GPU 推理成本约降 60%（**待核实**），催生托管服务抹平本地门槛——市场正在这条张力线上重新洗牌。

---

## 八、可扩展性与集成技术面（直接服务「能否复用 / 在 liveware 重建」）

> 本节质量罕见地高，绝大多数经一手 spec 仓库与官方文档逐字段确认。

### 扩展机制（高度向「前端注入」倾斜，无沙箱）
- **UI 扩展**：浏览器上下文里**几乎无沙箱**运行，通过 `SillyTavern.getContext()` 拿到全部内部状态（`chat`/`characters`/`eventSource`/世界书）与生成函数。官方原文：「practically unrestricted access to the DOM」；扩展之间无隔离、`extensionSettings` 明文对所有扩展可见。
- **Server plugins**：显式 opt-in 的 Express 路由（`config.yaml` 设 `enableServerPlugins:true`），挂在 `/api/plugins/{id}/{route}`，**完全不沙箱、能读整个文件系统**。
- **无 headless 模式**：Discussion #3518，维护者明确 ST「不是被设计成服务之间桥梁的」，独立前端应直连 LLM endpoint。**想复用其能力只能整包跑前端，不能抽离生成引擎。**

### 角色卡 V2 / V3 spec 字段（最高价值可复用资产）
**V2**（malfoyslastname/character-card-spec-v2）：`{spec:'chara_card_v2', spec_version:'2.0', data:{...}}`。`data` 含 `name/description/personality/scenario/first_mes/mes_example` + `creator_notes`（禁入 prompt）/`system_prompt`（支持 `{{original}}`）/`post_history_instructions`/`alternate_greetings[]`/`character_book`/`tags[]`/`creator`/`character_version`/`extensions(Record<string,any>)`。**铁律：「Character editors MUST NOT destroy unknown key-value pairs」**，自定义数据须命名空间化（如 `agnai/voice`）。

**V3**（kwaroran/character-card-spec-v3，RisuAI 作者主导）：`spec='chara_card_v3'/'3.0'`。新增 `nickname`、`creator_notes_multilingual`、`source[]`、`assets[]`（icon/background/emotion/user_icon，uri 支持 `embeded://` 与 `ccdefault://`）、`group_only_greetings`。**嵌入**：PNG 用 `ccv3` tEXt chunk；**CHARX = zip**，根 `card.json` + `assets/{type}/{category}/`。世界书条目新增 `use_regex`、`decorators`（`@@depth`/`@@role`/`@@position`）。

### 世界书格式
`character_book{name, scan_depth, token_budget, recursive_scanning, entries[]}`。每条 entry：`keys[]`、`content`、`enabled`、`insertion_order`、`constant`（常开蓝灯）、`selective`+`secondary_keys`（绿灯二次匹配）、`position`（`before_char`/`after_char`）、`use_regex`（V3）。**递归扫描**：已激活条目的 content 可继续激活其他条目。

### 跨平台可移植性
角色卡/世界书是事实标准，SillyTavern / RisuAI / chub.ai / Venus / 各移动端互通。
- **重要 caveat**：V3/CHARX 采纳偏慢，**V2（PNG `chara` chunk）仍是事实最大公约数**，V3 为前向标准。

### 与 liveware 最直接的同构先例：酒馆助手 Tavern Helper + Regex
- 机制：Regex 扩展捕获 AI 输出里的代码块，Replace With 填 HTML+CSS，渲染成**楼层内可交互 HTML/CSS/JS UI**。酒馆助手在此之上提供完整渲染 + jQuery/Lodash + 变量/世界书/消息/角色卡 CRUD + 生成请求 + 事件 API，能做动态状态栏、监听事件的 meta 小游戏、自制界面与酒馆双向交互。
- 这是「**agent 产出活件、客户端渲染交互界面**」的成熟同构先例。
- **关键架构差异（产品价值最高的一点）**：酒馆助手 = 同源、注入即全权限、与主 UI 同 DOM 同 origin；liveware 容器 = 独立 WKWebView/WebView2 **进程级隔离** + 域锁 + 不注入 token + 能力默认关。两者「渲染交互界面」表面同构，**安全边界根本不同**。

### 自动化原语
- **STscript** + **Quick Replies** + **registerFunctionTool**（注册 LLM 可调用工具）。均绑死在前端浏览器运行时，**无法被外部 headless 调用——复用价值在「范式参考」而非「直接接进容器」**。

### 数据导入导出 / 边车演化教训
- 角色卡/世界书/预设/聊天记录皆为可独立分发流通的文件资产；RisuAI 支持导出 png-v2/json-v2/png-v3/json-v3/charx-v3。
- **SillyTavern-Extras 废弃（2024-04-24）= 「外置 Python 能力服务器 → 内化进主程序原生」的演化路径**。对照 ClawChat 的 newsdesk 这类独立能力服务器，是「能力该内嵌还是外挂」的直接前车之鉴。

---

## 九、关键事实速查表

| 项 | 值 | 可信度 |
|---|---|---|
| GitHub stars | ≈29.9k（2026-06，增长中） | 高 |
| Forks / Contributors | ≈5.66k / 355 | 高 |
| 当前大版本 | **1.18.0**（2026-05-03） | 高 |
| 发布节奏 | release 约每 4–5 周一个 minor；staging 一天数次 | 高 |
| 许可 | AGPL-3.0 | 高 |
| 起源 | 2023-02 fork 自 TavernAI 1.2.8 | 高 |
| 技术栈 | Node.js 20+ 服务端 + 浏览器前端，JS≈86% | 高 |
| r/SillyTavernAI | ≈73k 订阅（quarantined） | 中 |
| 官方 Discord | ≈94k 成员 | 中 |
| 云后端 | OpenAI / Claude / Google / Mistral / DeepSeek / OpenRouter / Cohere / Perplexity / AI21 / NovelAI / AI Horde | 高 |
| 本地后端 | KoboldCpp / llama.cpp / Ollama / Oobabooga / TabbyAPI | 高 |
| 角色卡格式 | V2 (`chara` chunk) / V3 (`ccv3` chunk) PNG base64-JSON，或 CHARX(zip)；V2 仍是最大公约数 | 高 |
| 最大角色卡库 | Chub.ai，60,000+ 用户卡，2025 月访问 750万–1390万 | 中 |
| 移动端 | 无官方 App；Android 走 Termux，iOS 不支持 | 高 |

---

## 十、给 ClawChat 的「机会信号」（只列信号，方案见 agent-liveware-opportunities.md）

1. **降门槛即蓝海**：ST 把全部复杂度暴露给用户，易用替代品集群逐条对应它的痛点抢入口——「开箱即用 + 移动原生」是真实且未被 ST 满足的需求面。
2. **移动原生是验证过的赛道**：ST 移动体验差催生了 RisuAI 原生包、MiniTavern/ForkSilly——与 ClawChat 移动优先 IM 形态高度同构。
3. **角色卡数据格式可复用**：V2/V3 spec 是跨前端事实标准，`extensions` 字段「未知 key 不可删」+ 命名空间化 = 「多客户端共享同一数据载体不互相踩」；CHARX 是「活件可携带资产」的现成打包范式。
4. **角色「不可演化」是官方明确空白**：issue #2022 被 stale 关闭，社区只能靠第三方扩展补。agent 化方向可把「记忆抽取 + 人格演化」做成**系统级原生能力**——这是 ST 结构上做不到的差异化。
5. **长期记忆需自动化而非暴露**：ST 的 summarize + 向量 + 作者注释「多层堆叠」成熟但全靠用户手调。自动化掉这套分层是陪伴体验核心价值。
6. **「agent 产出活件、客户端渲染交互 UI」已被验证有强需求**：酒馆助手楼层 UI 是同构先例，但它**无沙箱、注入即全权限、已出窃 key 事故**，反向印证 liveware 容器隔离决策正确，是差异化护城河。
7. **隐私 vs 便利的张力 = 同步层机会**：ST 无原生跨设备同步，用户在「本地易丢」与「云端明文暴露」间二选一。ClawChat 端侧权威存储 + 跨端同步 + 隐私优先正切这条张力线。
8. **发现/分发层缺位**：角色卡靠裸 PNG 手传、易被剥元数据、无版本/注册/发现机制。liveware 的注册/分发/发现若做好，可成「带质量信号且可演化」的下一代资产生态。
9. **能力服务器边界有前车之鉴**：ST-Extras「外置 Python 边车 → 内化进主程序」的废弃路径，对 newsdesk 这类独立能力服务器「内嵌 vs 外挂」的生命周期设计是直接参照。

---

## 主要来源

**官方/一手**：github.com/SillyTavern/SillyTavern、docs.sillytavern.app（api-connections / prompt-manager / instructmode / groupchats / data-bank / st-script / writing-extensions / server-plugins / function-calling / regex）、discussions/3518、/5592、issues/2022、SillyTavern-Extras

**Spec / 格式**：github.com/kwaroran/character-card-spec-v3、github.com/malfoyslastname/character-card-spec-v2

**生态 / 竞品 / 内容**：chub.ai、characterhub.org、janitorai.com、charavault.net、github.com/kwaroran/RisuAI、github.com/agnaistic/agnai、github.com/TavernAI/TavernAI、backyard.ai、github.com/fatsnk/forksilly.doc、github.com/Min3Mast3r4653/SillyTavern-Extensions-and-Themes、n0vi028.github.io/JS-Slash-Runner-Doc（酒馆助手）、huggingface.co/spaces/DontPlanToEnd/UGI-Leaderboard、openrouter.ai/collections/roleplay、charasnap.com

**社区 / 评测 / 中文**：reddit.com/r/SillyTavernAI、discord.com/invite/sillytavern、promptquorum.com、rpwithai.com、mini-tavern.com、guide.sillytavern.one、erocraft.com

**待核实标记项**：CharaVault「195K+」卡数、类脑/Chub「最大」相对排名（社区口径）、第三方中转「封号/跑路」、本地「6GB+ 显存」、「隐私 vs 便利市场洗牌」「云推理成本降 60%」论点、竞品 star 并排数据、ST 用户真实弃坑量化。
