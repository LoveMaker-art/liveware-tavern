# 酒馆 reader — UI 打磨 + 活件特性体现（kickoff，2026-06-30）

继续迭代「酒馆」(`~/projects/clawchat-tavern`)。**先和我对齐方向 + 报文档状态(铁律 G)，再动代码**；中文行文。

## 0. 动手前先读
- memory **`project_tavern_experience_gaps`（必读）**：部署 runbook + 三个血坑 ——
  ① relay/CDN 把 reader 的 `.js/.css` 强缓存成 `immutable` 30天（改了不生效），靠 `server.py._serve_index()` 给资源 URL 注 `?v=<mtime token>` 破缓存（已落地，部署即自动生效）；
  ② 重启 server.py 用 `pkill -f "[s]erver.py"`（bracket 防自匹配）+ `docker exec -d`（别用前台 setsid，会挂死）；
  ③ 验证看裸 URL 或 index.html 实际引的版本化 URL，别用 `?v=时间戳`（假阳性）。
- memory `project_tavern_liveware`（项目全貌、两层记忆、活件愿景）。
- docs：`design/surfaces-and-features.md`（ST 覆盖契约 + 沉静感/空气感/渐进披露 + 移动动线）、`design/conversation-surface.md`（已落地的对话行为）、`design/v1-build-spec.md`（事件表/数据模型）。
- 代码：`skill/reader/{index.html,app.js,bridge.js,console.css}`、`skill/server.py`（同源 `/api/event`+`/api/*`）、`skill/actor.py`、`skill/state/actor_self.md`（演员技艺/成长层，有 `/api/actor` 端点）。

## 1. 跑 / 验
- 快迭代：`.claude/launch.json` 的 `tavern` 配置 → preview_start（Chromium，本地有 model key，可真发真生成）。
- 真验：部署进容器 `hermes-clean:/opt/data/tavern/`（reader 静态热生效；server.py 改了按 runbook 重启）→ 公网 `app-02dd46427910ed17.apps.clawling.io`。**IME / 软键盘 / WebKit 必真机；macOS 协作验（别自己 `flutter run macos`）。**

## 2. 这次 5 件事（全在 reader + tavern 自托管 server —— 不碰 ClawChat 后端/客户端；改 tavern server 加事件 ≠ 触发铁律 B）

1. **UI 打磨**：让控制台更像移动 APP 的交互质感、有一点「酒馆」即视感但够简洁。对齐 surfaces-and-features 的沉静感/空气感/渐进披露。**先给视觉方向，我拍了再改。**
2. **角色卡出处**：信息面板（`app.js` renderPanel）加「来源」——有 `creator`（Chub 卡作者）就显作者/来源；Agent 原创（走 `import_card_json`）显「Agent 创作」。需在 card 数据标记来源（`card_import.normalize_card` 加 `source`）。突出出处。
3. **左侧列表数值**：剧组列表（renderRail）每个剧组显**对话轮数** + 必要数值（消息数/最近活跃等），让用户一眼看到各剧组参与量。数据已在 `production.story`。
4. **剧组可编辑（删除等）**：server 加 `delete_production` 事件 + reader UI。移动端交互范式先查 `interaction-patterns`（长按/侧滑别无脑搬，确认/不可逆动作要二次确认）。
5. **体现活件特性**：reader 缺活件版本信息。参考 liveware「活的软件 / 可被 agent 编辑发版」——显示**活件版本** + **agent 的演艺经验积累 .md**（`actor_self.md` 技艺/成长层 + `actor_self.meta.json` 版本/快照若有）。把「越演越懂你」的技艺层做成用户可见的活件特征。先报现状（meta 是否已实现），再定怎么呈现。

## 3. 铁律
- 纯 tavern 侧（reader + 自托管 server）；**零新后端接口、零 ClawChat 客户端改**。
- 设计取值走 reader 自己的 CSS 变量（`console.css` `:root`），范式对齐 surfaces-and-features / desktop-page-patterns；缺规范先问。
- 改完同步 docs（rule G，跑 `rg <符号> docs/` 逐个更新）。提交 = tavern 仓 `main`、commit **不 push**；说「提交吧」才提。
