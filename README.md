# Tavern

Tavern 是一个开源的多角色互动故事系统。它包含可独立运行的 Web
酒馆、持久化世界与角色数据，以及一套面向 Hermes Agent 的管理技能。

> Tavern 不依赖 Liveware 才能运行。Liveware 只是 ClawChat 中的可选展示入口；
> Hermes 技能是当前仓库提供的 Agent 集成方式。

## 选择部署方式

| 目标 | 使用内容 | 文档 |
| --- | --- | --- |
| 只运行酒馆 Web 应用 | `app/` | [独立部署](docs/standalone.md) |
| 安装 Hermes Agent + 酒馆 | `app/`、`skills/`、`integrations/hermes/` | [Hermes 部署](docs/hermes.md) |
| 理解代码、状态与发布边界 | 全仓库 | [项目架构](docs/architecture.md) |
| 配置模型、存储、安全与性能 | 环境变量和实例状态 | [配置参考](docs/configuration.md) |

## 五分钟启动独立酒馆

需要 Python 3.10+ 和一个 OpenAI-compatible Chat Completions 接口。

```sh
git clone https://github.com/LoveMaker-art/liveware-tavern.git
cd liveware-tavern

python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

export TAVERN_STATE_DIR="$PWD/tavern-state"
export TAVERN_MODEL_BASE="https://your-provider.example/v1"
export TAVERN_MODEL_KEY="replace-with-your-key"
export TAVERN_MODEL="your-model-id"

python3 app/backend/server.py --port 8799
```

打开 <http://127.0.0.1:8799/>。运行数据只写入 `TAVERN_STATE_DIR`，不会写回源码目录。

## Hermes Agent 集成

- **Hermes：已适配。** 仓库根目录的 `skills/` 是一个符合 Hermes 官方结构的 Custom Tap。Agent 可通过六个创意技能、两个系统技能及共享 CLI 创建世界、导入角色卡和世界书、维护剧情连续性、配置模型并管理运行服务与版本。
- **ClawChat：已适配。** 可选 Hook 会在 Gateway 启动时恢复 Tavern 服务并注册两个 Liveware 入口。
- **其他 Agent：尚未提供即装即用适配器。** Tavern 已有本地 HTTP API，但本仓库当前没有 MCP Server，也没有承诺稳定的通用工具协议。不要仅凭“存在 HTTP API”把它描述为已完成通用 Agent 适配。

已经运行 Tavern、只需安装 Hermes 技能时：

```sh
hermes skills tap add LoveMaker-art/liveware-tavern
hermes skills install LoveMaker-art/liveware-tavern/tavern
hermes skills install LoveMaker-art/liveware-tavern/tavern-world
hermes skills install LoveMaker-art/liveware-tavern/tavern-story-profile
hermes skills install LoveMaker-art/liveware-tavern/tavern-continuity
hermes skills install LoveMaker-art/liveware-tavern/tavern-ops
hermes skills install LoveMaker-art/liveware-tavern/tavern-world-visuals
hermes skills install LoveMaker-art/liveware-tavern/tavern-updater
hermes skills install LoveMaker-art/liveware-tavern/model-api-manager
```

Hermes 会把技能安装到当前 profile 的 `$HERMES_HOME/skills/`。新会话自动生效；应用部署与
ClawChat 注册仍按 [Hermes 部署](docs/hermes.md) 完成。

## 仓库结构

```text
app/backend/                    Tavern 后端唯一源码
app/frontend/                   Tavern Web 前端唯一源码
app/assets/                     内置模板和运行资源
skills/                         Hermes Custom Tap：技能、共享 CLI 与可选 ClawChat 适配器
integrations/hermes/            可选 AGENTS 与 SOUL 实例模板
tools/                          兼容旧调用路径的 Tavern CLI 入口
bootstrap/                      更新器 Bootstrap
docs/                           部署、配置与架构文档
scripts/                        发布构建脚本
tests/                          后端、前端、更新器与仓库边界测试
```

核心运行时不包含用户世界、角色卡、故事、密钥、ClawChat 会话或注册信息。详见[项目架构](docs/architecture.md)。

## 测试

```sh
PYTHONPATH=app/backend python3 -m unittest discover -s tests -v
node --test tests/frontend_security.test.js
python3 scripts/build_release.py
```

## Hermes 更新

Hermes 实例可通过经过校验的 Bootstrap 安装或更新应用与整套技能：

```sh
curl -fsSL https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download/install-tavern-updater.sh | sh -s -- --apply --confirm
```

更新器只管理发布清单中的代码和技能。用户世界、模型配置、身份、故事与素材位于
`$TAVERN_STATE_DIR`，不在覆盖范围内。具体流程见 [Hermes 部署](docs/hermes.md)。

## License

本项目采用 GNU Affero General Public License v3.0 only（`AGPL-3.0-only`）。
详见 [LICENSE](LICENSE)。通过网络提供修改版服务时，应按 AGPL 第 13 条向用户提供对应源码。

`v1.18.1` 及更早版本仍按当时随版本附带的 MIT License 发布。
