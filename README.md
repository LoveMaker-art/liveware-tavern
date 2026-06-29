# clawchat-tavern

把 **agent + liveware** 与开源 AI 角色扮演前端 **SillyTavern（"酒馆"）** 的生态结合，探索一个"更好的酒馆体验"。

> 独立孵化项目，**不进 ClawChat 仓库**（类比 `clawchat-newsdesk` / `clawchat-liveware-skills`）。
> 当前处于**调研 + 概念讨论**阶段，尚未写任何产品代码。

## 现状

- **阶段**：Phase 0 — 生态调研 + 可能性讨论
- **不做的事**：不抄 SillyTavern 代码、不假设新增 ClawChat 后端接口、不碰 ClawChat 客户端

## 目录

- `docs/research/sillytavern-ecosystem.md` — 酒馆生态调研简报（产品 / 口碑 / 用法 / 衍生项目 / 社区 / 痛点）
- `docs/research/agent-liveware-opportunities.md` — agent+liveware 对酒馆生态的创新可能性（讨论稿）

## 背景指针（ClawChat 侧已有能力）

- liveware = 沙箱容器窗口（非浏览器），域锁 + 不注入登录态 + 能力默认关
- agent 自托管页面与 agent 同源、由 agent 调能力服务器（先例：资讯日报 digest liveware + newsdesk 能力服务器）
- 详见 ClawChat 仓库 `docs/liveware/`
