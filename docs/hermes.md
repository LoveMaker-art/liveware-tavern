# Hermes + Tavern 部署

本仓库的 Agent 集成以 Hermes `/opt/data` 布局为准。安装完成后：

```text
/opt/data/apps/tavern-runtime/          核心运行时
/opt/data/tavern-state/                 用户和实例数据
/opt/data/skills/creative/tavern*/      创意技能
/opt/data/skills/system/tavern-updater/ 更新技能
/opt/data/skills/system/model-api-manager/ 模型 API 管理技能
/opt/data/AGENTS.md                     Tavern 路由说明
/opt/data/SOUL.md                       Agent 人格与相处方式
```

首次从源码部署 Agent 时，可将模板复制为实例人格文件：

```sh
install -m 600 integrations/hermes/SOUL.md /opt/data/SOUL.md
```

仓库模板提供诺拉的默认人格。部署后 `/opt/data/SOUL.md` 归实例所有，不属于 Tavern
代码发布；更新器不会覆盖用户后续调整的名字、人格或相处方式。

## 推荐安装与更新

```sh
curl -fsSL https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download/install-tavern-updater.sh | sh -s -- --apply --confirm
```

这个命令先更新并验证更新器，再完成兼容性审查。只有无冲突且校验通过的文件才会进入
应用阶段；启动或健康检查失败时会回滚受管理文件。

更新边界：

- 会更新发布清单中的后端、前端、Tavern 创意技能、系统技能、更新技能与受管理的 `AGENTS.md`。
- 不会覆盖 `/opt/data/tavern-state`、模型密钥、ClawChat 会话、用户世界和自定义技能。
- 不应使用 `git pull` 直接覆盖正在运行的 `/opt/data/apps/tavern-runtime`。

## Hermes 如何驱动 Tavern

`integrations/hermes/skills/creative/tavern/SKILL.md` 是路由器，只负责把请求交给一个专业技能：

| 技能 | 职责 |
| --- | --- |
| `tavern-world` | 创建世界，导入和整理角色卡、世界书、Persona 与开场 |
| `tavern-world-visuals` | 世界背景和视觉主题 |
| `tavern-story-profile` | 故事回忆与长期偏好 |
| `tavern-continuity` | 剧情账本、角色状态、压缩与生成诊断 |
| `tavern-ops` | 模型、服务健康、Liveware、命名与语言 |
| `tavern-updater` | 版本审查、安装和回滚 |
| `model-api-manager` | 区分 Agent 与 Tavern 配置域，验证并接入模型 API |

技能通过唯一共享 CLI 执行结构化操作：

```sh
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py doctor --json
```

核心运行时仍通过本机 HTTP API 读写状态。技能负责理解用户意图、选择安全命令、确认写入
并验证结果；CLI 负责稳定参数与机器可读返回；运行时负责实际数据一致性。

## ClawChat / Liveware

源码位于 `integrations/clawchat/` 的 `tavern-liveware-register` Hook 在 Gateway 启动时调用：

1. `provision.sh` 创建或复用 Tavern 和 Story Profile 应用并完成注册。
2. `bringup.sh` 启动运行时、绑定 tunnel 并恢复入口。

这两个脚本只适用于已安装 ClawChat 插件和 Liveware 二进制的 Hermes 实例。独立部署不需要它们。

## 验证

```sh
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py doctor --json
curl -fsS http://127.0.0.1:8799/api/health
```

`doctor` 应确认运行时、技能版本和路由能力；健康接口应返回 `"ok": true`。
