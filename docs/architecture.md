# 项目架构

## 设计边界

Tavern 分为四层，依赖方向由外向内：

```text
ClawChat / Liveware adapter
Hermes skills and updater
Tavern HTTP runtime + browser frontend
TAVERN_STATE_DIR
```

核心运行时不知道 Agent 的人格、会话或工具协议。Hermes 技能可以驱动运行时，但运行时
不反向依赖 Hermes。ClawChat Hook 只负责生命周期和入口注册。

## 唯一源码

| 路径 | 所有权 |
| --- | --- |
| `app/backend/` | 后端运行时唯一源码 |
| `app/frontend/` | Web 前端唯一源码 |
| `app/assets/` | 内置角色模板、默认档案和音色目录 |
| `integrations/hermes/skills/creative/` | Tavern 路由技能与五个专业工作流 |
| `integrations/hermes/skills/system/` | 更新与模型 API 管理等系统工作流 |
| `integrations/hermes/AGENTS.md` | Hermes 的发布托管路由说明 |
| `integrations/hermes/SOUL.md` | Hermes 首次部署人格模板；安装后归实例所有 |
| `integrations/clawchat/` | ClawChat Hook 与 Liveware 生命周期脚本 |
| `tools/tavern_cli.py` | Hermes 技能使用的共享结构化 CLI |
| `bootstrap/` | 更新器自举 |

不要在 `app/` 下复制 Hermes 脚本。发布包由 `scripts/build_release.py` 从上述唯一源码生成，
`dist/` 是构建产物，不是源码。

## 数据边界

代码发布与实例数据严格分离。`TAVERN_STATE_DIR` 中包括：

- `productions/`：世界、故事和运行态角色副本
- `cards/`：可复用角色卡库
- `worldbooks/`：可复用及世界私有世界书
- `model_configs.json`：自定义文本模型配置
- `tts_config.json`、`tts-cache/`、`tts-references/`：语音配置与缓存
- `world-assets/`：世界背景素材
- `apps.json`、`app_identity.json`：可选 Liveware 实例信息

发布包不得包含这些文件，也不得包含 API Key、聊天数据库、日志或用户会话。
实例中的 `/opt/data/SOUL.md` 同样属于身份数据：源码模板可用于首次部署，常规
Tavern Release 与更新器不得管理、替换或回滚它。

## Agent 边界

当前一等支持的是 Hermes：技能调用共享 CLI，CLI 调用 Tavern 本机 HTTP API。
HTTP API 是前端和 CLI 的运行时接口，但目前不是承诺长期兼容的通用 Agent 协议。

仓库当前没有 MCP Server。未来添加 MCP 或其他 Agent 适配器时，应放在独立适配目录，
调用现有运行时 API，不把框架 SDK 加进核心 `requirements.txt`，也不允许绕过确认和数据校验。

## 发布边界

`scripts/build_release.py` 生成两个独立归档：

- `tavern-release.tar.gz`：运行时、系统技能和更新器
- `tavern-skill.tar.gz`：Hermes 创意技能

清单保存每个受管理文件的 SHA256。更新器先完成基线对比和冲突审查，再原子应用；
状态目录始终在发布边界之外。
