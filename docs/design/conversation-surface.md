# 对话表面规格（conversation-surface）

> 承接 `surfaces-and-features.md`（功能/覆盖契约）+ `v1-build-spec.md`（事件/数据）。
> 那两份定了**有哪些功能**，这份定**对话怎么进行**——输入、键盘、回合控制、流式、失败兜底。
> 状态：2026-06-30 起。**「体验达标」的可执行规格就住这里。**

## 0. 为什么单立这份

`surfaces-and-features.md §B` 定了控制台**长什么样**（沉静感 / 空气感 / 渐进披露），但从没定它**怎么对话**。结果是基础对话体验出现一批洞：拼音回车误发、移动端键盘盖输入框、触屏点不出控制条、macOS 容器里 `prompt()` / 文件选择器是死的、长局会撞上下文上限。这些不是「看起来」的问题，是「用起来」的问题，必须有规格。

**验收哲学**：v1 不追 ST 的功能海，对标 **RisuAI / ST 共有的「核心对话环」**——一个酒馆用户坐下来就靠肌肉记忆用的最小集合。被简化的复杂旋钮仍按覆盖契约「换成跟搭子说一句」，但**核心对话环本身必须手感达标**，不能用「跟 agent 说」搪塞（流式、swipe 不是复杂度，是基本手感）。

## 1. 文本输入

| 规则 | 实现 |
|---|---|
| **Enter 发送，仅在「不在输入法合成中」时**（含 macOS WKWebView/WebKit 修正） | 三重守卫:① `e.isComposing \|\| e.keyCode === 229`(Chromium 合成中) ② `imeComposing` 标志(compositionstart/end 自己跟踪,挡「合成期间」的 keydown) ③ `imeEndedAt` 时间窗(刚 compositionend 120ms 内的 Enter 也挡)。**为什么要 ②③**:WebKit(macOS 容器 + Safari)把 `compositionend` 排在「确认候选词」那个 Enter 的 `keydown` **之前** → 那 keydown 的 `isComposing` 已 false、`keyCode=13`,光靠 ① 在 macOS 漏发(实测 2026-06-30)。三条任一命中即不发、绝不 `preventDefault`(吞候选确认)。默认受众中文(`lang="zh-CN"`),硬规则。 |
| **Shift+Enter = 换行** | 不发送。 |
| 自增高 | `autoGrow`，上限 140px。 |
| 移动端输入提示 | textarea 带 `enterkeyhint="send"`；多行场景不强制 `inputmode`。 |

## 2. 移动端键盘与触屏

**宿主已配合**：ClawChat 移动宿主 `UrlViewerPage` 用 `resizeToAvoidBottomInset` 默认值、webview 占满 body，键盘弹起时**已把 webview 压到键盘上方**（`code/lib/features/viewer/presentation/mobile/url_viewer_page.dart` 注释明载）。所以键盘避让的责任**在 reader 自己的 CSS 跟不跟随**，不需要改客户端。

| 规则 | 实现 |
|---|---|
| 布局高度跟随可视视口 | `interactive-widget=resizes-content`（viewport meta）+ 用 `100dvh` 而非 `100%/vh`。 |
| 老 WebView 兜底 | `visualViewport` 监听 `resize`/`scroll`，把根容器高度/位移贴到可视视口（给不认 `interactive-widget` 的旧 iOS WKWebView）。 |
| **触屏能点出控制条** | 控制条原来 `:hover` 才显——触屏无 hover 通道 = 死的。`@media (hover:none)` 下常驻低透明（`.55`），保证拇指可达。桌面维持 hover 渐进披露。 |
| **发送后不抢键盘**（移动） | 发送即 `input.blur()` 收键盘（别盖住正在生成的回复），回复完成也**不回焦**，留给用户阅读；桌面（`hover:hover`）维持续焦点方便接着打。`isTouch()` = `matchMedia("(hover:none)")`（反馈 2026-06-30）。 |

> 注：真 IME / 软键盘行为只能真机验（Android 我自动、桌面走 winrig、macOS 协作）；preview 只验布局与 JS 无错。

## 3. 回合控制（重生成 / swipe / 编辑 / 阅读定位）

落「渐进披露」：控制条默认 ghost 态，hover（桌面）/ 常驻低透明（触屏）显。

### 3.0 回复后定位到「消息头」（双端，反馈 2026-06-30）

AI 回复就位后（send 完成 / regenerate / swipe）把该消息的**头**滚到接近视口顶部（`top-16px`），而非旧的 `scrollDown()`（贴尾）——长回复用户能从头完整读。流式期间也是头钉顶、内容往下生长（不跟尾）。**关键**：末条消息下方无内容、本来滚不到顶 → 给 `.thread` 动态垫 `padding-bottom = max(0, 视口高 - 末条高 - 24)`，短回复也能把头顶到位（`scrollTurnToTop` 只对 `lastElementChild` 垫，中间消息不垫；`renderStage` 重建 thread 会清掉旧值）。

### 3.1 swipe = 非破坏性备选回复（核心手感）

- **数据契约**：每条 char 消息持有 `alts[]` + `active_alt`（`_msg` 已建）。
- **重生成不再覆盖**：`regenerate` 在服务端 append 进 `alts`、`active_alt` 指向新条；前端**整条替换** message（保留 alts），不再只改 `.text`。一次更差的重生成不毁原版。
- **swipe 切换**：char 消息 `alts.length > 1` 时显 `‹ i/n ›`；左右切 `active_alt`，走新事件 `swipe {production_id, message_id, dir}` 落盘。`dir` ∈ `-1/+1`，到边界夹住。
- 这是酒馆第一肌肉记忆（roll 几次挑最好）。**curation 本身就是「同模型文笔更好」的一大半来源。**

### 3.2 行内编辑（替代 `window.prompt()`）

- `prompt()` 在 **macOS 容器 WKWebView 里是死的**（`LivewareWindowController` 未实现 `runJavaScriptTextInputPanel`，直接回 null 不弹 UI），且单行、对多段 RP 文本是灾难。
- 改成**行内编辑器**：点「编辑」把该气泡 body 换成 textarea + 保存/取消，保存调 `edit_message`。纯 web，**所有宿主可用**，多段友好。

### 3.3 重生成

仅对最后一条 char 生效（不变），但走 3.1 的非破坏性语义。

## 4. 发送失败不丢输入

`send()` 在生成失败时：移除 thinking 占位、撤掉刚 push 的 user 回合、**把原文塞回输入框**（`input.value = text` + `autoGrow`），让用户能直接重发。绝不让一次网络/模型失败既吞回合又吞文字。

## 5. P1 / P2（本轮已落地，标注实现位置）

| 项 | 语义 | 状态 |
|---|---|---|
| **流式输出 + 早停** | 模型逐 token 流到气泡；发送中按钮变「■停止」，点/回车中途停 | ✅ 服务端 `actor.chat_stream`/`perform_stream`（SSE，`stream:True`）+ `POST /api/stream` + `bridge.eventStream(ev,onDelta,signal)` + reader 增量渲染；流式不可用（传输层/relay 不支持）自动**回退阻塞式**。**早停**：`AbortController` 取消 → 已生成的半截经 `append_turn` 补存（流式断开 server 不落盘）；停时无内容则当取消、还原输入。⚠️ relay（Loop B）是否透传 SSE 待容器实测（即便缓冲也优雅降级：末尾 `done` 事件带全文）。 |
| **上下文预算裁剪** | 长局只喂开场 + 预算内最新尾巴 | ✅ `actor._fit_history`（字符级，`TAVERN_CTX_CHARS`）。token 级后续。 |
| **世界书贴近生成点 + selective** | `before_char` 进系统顶（背景），其余注在故事后（steer 当前回合）；`selective` 需二级关键词同现；扫描深度走 env | ✅ `actor.select_lore` + `build_messages`。递归/位置@depth 后续。 |
| **作者注释（导演提示）** | per-剧组临场语气/格式杠杆，注入贴近生成点 | ✅ `production.author_note` + `ev_set_note` + `actor` 注入 + CLI `note`。**无 UI 旋钮**（设计 canon）——由对话/agent 设（"回复短点"→`set_note`）。结构化兜底，不靠模型记着。 |
| **反复读兜底** | 服务端 `frequency_penalty`/`presence_penalty` 默认 | ✅ `actor._payload`（env 可调）。**无 UI**——采样参数按 canon 收进自动档。 |
| `mes_example` / `post_history_instructions` 注入 | few-shot 风格锚 + 贴尾指令 | ✅ `build_messages`（解析早有，注入补上）。 |

**仍 TODO**：token 级预算（现为字符级）、世界书递归 / 位置@depth、群聊、分支 checkpoint、续写（Continue 延长上一条）。

## 6. v1「体验达标」验收清单

对标 RisuAI / ST 核心对话环。每条可勾。

- [ ] 拼音回车选词不误发；Shift+Enter 换行
- [ ] 移动端键盘弹起，输入框与最新气泡始终可见
- [ ] 触屏能点出重生成 / swipe / 编辑
- [ ] swipe 非破坏性：重生成保留旧版，可 `‹ i/n ›` 来回切
- [ ] 编辑走行内编辑器，macOS 容器可用，支持多段
- [ ] 发送失败不丢已输入文字
- [x] 角色卡的 `mes_example`（示例对白）+ `post_history_instructions`（贴尾指令）进入 prompt
- [x] 流式输出 + 早停（中途停，保留已生成）
- [x] 长局不撞上下文上限（字符级预算裁剪）
- [x] 世界书贴近生成点 + selective 二级关键词；导入不靠文件选择器（粘贴 JSON / 拖拽）
- [x] 反复读兜底（服务端 penalty，无 UI）；作者注释结构化杠杆（`set_note`，无 UI）

**分歧项标注**：群聊 / 分支 checkpoint / 正则 / 立绘 = RisuAI 与 ST 各有侧重，**不进 v1 核心环**，留覆盖契约「后续」。

## 7. 与覆盖契约的对账（收敛 v1 漂移）

本规格落地后，更新两份上游 doc：

- **swipe**：`surfaces-and-features.md` / `v1-build-spec.md §4§6` 标 v1——**现已实现**（服务端 `ev_swipe` + 前端切换），不再是「持久化了却没接的死数据」。
- **add_lore（世界书加条目）**：`surfaces-and-features.md:97` 标 v1，但 `v1-build-spec.md:114` 自注「未实现」——**明确降到 v1.1**（世界书在 v1 维持只读查看；加条目走墨对话/CLI）。两份 doc 同步改。
- **角色卡轻量改**：`surfaces-and-features.md:94` 标「v1 轻量改」，`v1-build-spec.md` 无 `edit_card` 事件、reader 只读——**v1 维持只读**（卡的改走墨对话 + `import_card_json` 重导）；UI 行内改卡降到 v1.1。把覆盖契约那格从「v1」改注「查看 v1 / 行内改 v1.1」。
