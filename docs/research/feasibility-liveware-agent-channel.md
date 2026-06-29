# 可行性裁决：酒馆核心闭环 ×（liveware ↔ agent 通道）

> 方法：3 路只读侦察（容器能力面 / digest 先例真实代码 / agent 消息通路），跨 ClawChat 仓 + clawchat-newsdesk(digest) 仓，codegraph + Grep + Read 交叉验证（不照文档口号）。2026-06-28。
> 核心闭环：控制台(liveware) 切角色卡/世界书 → 写回 agent → agent 在 IM 以 first_mes 主动开场 → 用户在 IM 接着聊。

## 一句话裁决

**Yes —— 核心闭环能用 ClawChat 现有管线搭起，不需要把容器桥（bridge.md，未启动）提前做。** 四跳里三跳全绿（同源写回 / agent 存 loadout / 用户↔agent 聊），唯一一跳（agent→IM 主动开场）靠 digest 已跑通的「同源 server + cron/webhook 唤醒」hack，是 agent 侧部署问题、不是 ClawChat 缺能力。**全程零新增后端接口/字段（铁律 B 不触发）、ClawChat 客户端零必改。**

> 限定词「部分」只用在一个意义上：第 ③ 跳能跑但靠 hack 而非桥提供的干净 proactive-send 原语。能力上闭环成立，工程上那一跳不优雅。

## 闭环每一跳：信号 → 通路 → 谁的活

| # | 跳 | 信号 | 走的现成机制（通路） | 谁的活 | 状态 |
|---|----|------|------|------|------|
| ① | 控制台(liveware) → agent server | 用户切角色卡/世界书 | 同源 `fetch('/api/event')` POST。容器域锁只拦顶层导航，fetch/XHR 子资源明确放行（`LivewareWindowController.swift:371-384` / `liveware_window.cpp:606-615`）；digest 的 `reader/bridge.js` 已端到端验证同款写回 | 纯 agent 侧 skill（控制台页 + bridge.js 加一个 `switch_loadout` 事件） | 现成可用 |
| ② | agent server 存 active loadout | 收到 `switch_loadout` 事件 | server.py `handle_event → event_to_newsdesk` 加一个 type 分支 + 一个状态文件（与 `subscriptions.json` 同形）。creds 只在 server 侧，页面永不直连 | 纯 agent 侧 skill | 现成可用（同构扩展） |
| ③ | agent → IM 主动开场(first_mes) | loadout 切换 / 唤醒触发 | agent 在 gateway 进程内 emit 一条 `message.send`（协议 C↔S 对称，server 回填 sender，无前序用户消息门控 —— `ws-protocol.md:291,312,405-440`）。客户端 `onReceive` 无条件追加成对方气泡（`message_provider.dart:1125-1133`）。触发靠 hermes cron/webhook 唤醒 agent drain —— 独立进程 `hermes send` 报 No live adapter | agent 侧部署（cron/webhook + gateway 进程内投递） | 需补（非桥，是 digest 同款 hack）／有风险 |
| ④ | 用户 → agent 聊 + agent 读 loadout | 用户在 IM 回消息 | 普通 `message.send` uplink 到同一条 `cnv_…`（配对即 materialize，`agent_repository.dart:96-99`）；agent 处理时从自己 state 读 active loadout 拼 prompt（prompt 分层是 agent 运行时的事，`chat.md:84-89`） | 既有会话通路（客户端零改）＋ agent 侧读 state | 现成可用 |

## 影响面（铁律 D）

- **纯 agent 侧 skill 的活（不碰 ClawChat）**：①②③④ 核心逻辑全在独立仓 `clawchat-newsdesk` / `clawchat-liveware-skills` —— 控制台页面、bridge.js 加 `switch_loadout`、server.py 存 loadout、cron/webhook 唤醒、agent emit first_mes、读 loadout 拼 prompt。
- **要动 ClawChat 客户端**：**无必改**。agent 发的 `message.send` 走现有 incoming 管线（`ws_notifier → ChatMessageEventSink → MessageNotifier.onReceive`）当普通气泡渲染，含 `*.apps.clawling.io` 链接自动渲染成活件卡（`LivewareCardBlock`），双端共用现成路径。控制台窗口走现成 `openMarkdownLink → LivewareWindowService`（桌面）/ `UrlViewerPage`（移动）。
- **新后端接口/字段（铁律 B）**：**无，不触发。** 复用既有 `message.send` / 既有 1:1 会话 / 既有 `GET /v1/agents/:id/apps` / 既有 incoming 管线。`switch_loadout` 状态全落 agent 侧状态文件。**红线**：active loadout 不要写进能力服务器端点或 member-backend —— 那会触发铁律 B；它是纯 agent 侧状态。

## 取舍：容器桥提前 vs 先用同源占位

**digest 那套同源占位足以让酒馆 v1 先不等桥。** ①②（写回 + 存）的「占位」本质就是 digest 已验证的生产形态，不是临时凑合 —— 域锁天然放行同源 fetch。第 ③ 跳是唯一靠 hack 的。

**先用同源占位的代价（要等真桥才顺的体验）：**
1. **主动开场的触发延迟/语义**：cron 是定时（非即时），webhook 在 digest 里仍标「占位」且踩过坑（cron 触发出刊时容器够不到 reader → 误判挂掉，memory `reference-agent-publish-trigger-gotcha`）。**「切角色后多久 agent 开场」是 v1 最大体验不确定项。**
2. **host 用户上下文/身份**：桥未启动 → 容器不注入 token、`window.clawchat.*` 未实现，控制台拿不到「当前哪个 ClawChat 用户在操作」的干净上下文，只能靠自己同源 session（digest 即如此）。多用户/多租户会变扭。
3. **主题（dark/light）跟随**：`open(url,title,dark)` 只一次性传 dark，桥才能运行时联动 —— v1 可忍。
4. **窗口生命周期解耦**：容器窗 last-in-wins 单例、与主窗独立；切完角色可能已关控制台窗，开场白照样进 IM（设计如此），但「控制台↔IM」连贯感要等桥。
5. **实时性**：「控制台写回 → agent 实时收到」当前是 POST + agent 端处理，缺桥的「发 fragment 唤醒 agent」实时原语 —— 优化项非阻塞项。

## 下一步建议（v1 最薄切片）

**焊死（直接抄 digest）**：① 同源写回（bridge.js 复刻 `send(event)` + `switch_loadout`）；② 存 loadout（server.py type 分支 + loadout 状态文件，仿 `subscriptions.json`）；④ 读 loadout 拼 prompt + 用户↔agent 聊（复用既有 1:1 会话）。客户端**不动**，验证 agent 发的 first_mes 落成普通气泡即可。

**先占位（cron/webhook hack，标记「桥要替换」）**：③ 主动开场。

**第一个要确认的未知（按优先级）：**
1. **webhook 能否即时把 agent 拉进 gateway 进程发消息** —— 决定「切角色即开场」是秒级还是分钟级。digest 里 webhook 未坐实，v1 头号验证点。
2. **控制台 host 形态**：digest 式 agent 自托管常驻 server（有 `/api/*` 收 POST，倾向这个）vs liveware-app 的 tunnel-bind-static（纯静态、无 server 收写回，接不住 ① 跳）。
3. **平台 relay 阻塞**：`registration.md` 记录控制台上线被平台 relay 卡（503 agent not connected）。非闭环能力问题，但「让真实控制台跑起来」的现实拦路石，v1 demo 前要疏通。

## 诚实标注：unknown / 待真机验

- **③ webhook 即时唤醒**：digest 里仍占位，**未坐实**，是推断不是已证。
- **角色身份呈现（三视角未覆盖）**：1:1 会话对端身份现状是 agent 影子用户的固定 name/avatar。切角色卡后会话头像/昵称要不要跟着变，是**未评估的「身份呈现」视角** —— 可能要 agent 改自己 profile，或纯靠气泡内容承载。**v1 体验的一个真空区。**
- **平台 relay 阻塞**：`registration.md` 的 503 是已知现实阻塞，影响「真实控制台上线」，与闭环能力无关。
- **控制台 host 形态二选一**：两条都不碰 ClawChat 后端，但只有 agent 自托管 server 那条接得住同源写回 —— 倾向性是推断，需 agent 侧实测。
- **所有「现成可用」基于源码只读侦察**：digest 写回回路已端到端验证，但酒馆 `switch_loadout` 扩展本身尚未写码、未真机验。
