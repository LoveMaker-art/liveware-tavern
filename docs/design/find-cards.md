# 找卡：复制即用的基础能力

> 承接 `surfaces-and-features.md` §2「在 chat 里添加世界书/角色卡」与 `project_tavern_liveware` ⑥找卡+导卡。
> 这里定**「任何人复制这套 tavern agent 后，墨都能顺畅找到并导入角色卡」**这条基础能力的形态、降级策略与边界。
> 状态：2026-07-01 落地（starter 兜底 + CLI 鲁棒性）。

## 目标

找卡不能「只有配好代理的那台机器能跑」。复制到新容器 / 新用户后，墨要么能从 Chub 找到真卡，要么退到内置真卡——**永远不回退到凭记忆手搓 PNG**（那是最差路径：既不准，又丢社区卡的开场白/示例/世界书调校）。

## 找卡链路

墨在 ClawChat 说「找张 X」→ `tavern_cli.py search`（Chub）→ 报候选 → `add <fullPath>` 下真卡建剧组。`tavern_cli.py` 纯 stdlib，只发 HTTP：

- **来源 = Chub.ai**（角色卡事实标准库，6 万+ 卡，公开 API、免鉴权）。搜 `api.chub.ai/search`，下卡 `avatars.charhub.io/avatars/<fullPath>/chara_card_v2.png`。
- **导入**打本地控制台同源事件 `POST /api/event`（`import_card{png_base64}` → `create_production`）。零新 server 事件、零新后端接口。
- 卡内嵌世界书（`character_book`）随 `add` 一起带进来挂好。

## 降级策略：Chub 不可达 → 内置 starter 卡（2026-07-01 定）

Chub.ai / charhub.io 在部分网络（尤其**墙内无代理**）不可达——容器实测里找卡链路是透明借宿主 Clash 出去的，换一台没配代理的机器就断。这是「只有我这台能跑」的物理根因。

**决策 = 随仓打包一批 starter 真卡兜底**（而非「只报错引导配代理」，也非「接备用源镜像」）：

- **只报错**被否：墙内无代理的副本找卡直接瘫、墨会退回手搓 PNG。
- **备用源镜像**被否：维护重、镜像易死、多数源墙内同样被墙，可靠性最低。
- **starter 卡**入选：零网络也能建剧组，Chub 降为「扩充卡库」而非「能不能用」；**顺带堵死墨没卡就手搓的退路**——结构性地消灭动机，比靠 SOUL 软劝可靠（呼应「结构性 > 软性」）。

CLI 的降级出口 `_degrade_to_starter`：`search`/`add` 探测到 Chub **网络不可达**（DNS/超时/连接失败，区别于 HTTP 4xx = 可达但 fullPath 写错）时，不 `sys.exit` 摆烂，而是列出 starter 卡 + 提示「先用内置卡 / 配代理拿全库」。

### starter 卡集（`fixtures/starter/`）

8 张，SFW / 跨题材 / 非小众，从 Chub 拉的真卡，`creator` 归属保留，`index.json` 是 manifest：

| 卡 | 题材 | 特点 |
|---|---|---|
| Audrey | 日常 · 咖啡馆 | 开朗民谣咖啡师，慢生活 |
| Doria the android | 科幻 · 机器人搭档 | 冷面毒舌副驾，星际冒险 |
| Kû | 奇幻 · 冒险者公会 | 傲慢对手，公会 RPG（带世界书、多开场） |
| Sentōgami Reikō | 动作 · 武士宿敌 | 冷傲剑客宿敌（带世界书） |
| Medieval Knight | 奇幻 · 骑士战斗 | 恪守荣誉的硬核战斗 RPG |
| Ichitora | 推理 · 刑警 | 东京凶案组刑警，结构完整（带世界书） |
| Librarian | 知识 · 图书管理员 | 无所不知、温和健谈 |
| Yan | 温馨 · 损友搭子 | 阳光暖心大学损友，日常陪伴 |

**第二用途：这批卡是墨写原创卡（`add-original`）的结构参考样板**——照它们怎么写 `description`/`personality`/`first_mes`/`mes_example`/世界书的水准来，别拍脑袋（用户要求：这组卡兼作墨的写卡原始数据）。

选卡守则（随仓 ship 给所有人）：**工具视角、内容中立、不在 NSFW 轴站队**——跨题材、SFW-default、辨识度高、结构丰富；不迎合任何个人口味画像。

## CLI 面（`tavern_cli.py`）

- `search "<关键词>"` — Chub 搜；不可达→列 starter。
- `add <fullPath | Chub 链接>` — 下真卡建剧组；`_parse_full_path` 自动从 `chub.ai/characters/<fullPath>` 抽 fullPath，用户直贴链接也吃；下载非 PNG / HTTP 4xx 给清晰错误 + 指向 starter；网络不可达→列 starter。
- `starter [<序号|名字>]` — 不给参数=列表，给=导入建剧组（`_resolve_starter` 支持序号或名字片段）。

## 结构性反手搓（墨仍偏好手搓 PNG 的根治）

「墨仍偏好手搓 PNG」不是 prompt 问题、是结构问题。本轮两条结构性修法（> 改 SOUL 软劝）：

1. **starter 卡消灭动机**：永远有真卡可用（Chub 或内置），墨没有理由再手搓。
2. **删竞争产物**：容器 `skills/creative/tavern/references/` 下墨自写的 `browser-injection-cjk-success.md`（一份「浏览器手搓 PNG 注入」操作手册，正好反噬「绝不手搓」铁律）已删除。教训同 `sillytavern-character-cards` 技能——**agent 会自发造出诱导反模式的游离产物，靠删、不靠劝**。

解析层 `card_import.py` 的乱码硬护栏（latin-1 还原字节 → 判 base64 → utf-8）仍是最后兜底：无论走哪条路都不乱码。

## 复制即用：本轮达到 / 仍缺

- ✅ **降级地板**：starter 卡让找卡在零网络 / 墙内无代理下仍能建剧组。
- ✅ **鲁棒性**：链接直贴、下载校验、Chub 4xx vs 不可达分流、清晰错误。
- ⏳ **安装自动化（本轮不做）**：复制到新容器仍需手动 `docker cp` + 两处分离放置（skill 落 `skills/creative/tavern/`、CLI+运行时落 `tavern/`），无一键 install。`bringup.sh` 只管 Loop B（server+tunnel），不管 install。这条留后续（一键 `install.sh` 或复制 runbook）。
