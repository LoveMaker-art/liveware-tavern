# 独立部署

独立模式只运行 Tavern 核心 Web 应用，不要求 Hermes、ClawChat、Liveware 或
`/opt/data` 目录。

## 前置条件

- Python 3.10+
- 可写的持久化目录
- OpenAI-compatible `POST /chat/completions` 模型接口

## 安装

```sh
git clone https://github.com/LoveMaker-art/liveware-tavern.git
cd liveware-tavern
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

复制配置模板并填写模型信息：

```sh
cp .env.example .env
```

Tavern 不会自行读取 `.env`。启动前需将其导入当前 shell：

```sh
set -a
. ./.env
set +a
python3 app/backend/server.py --port "${TAVERN_PORT:-8799}"
```

浏览器打开 `http://127.0.0.1:8799/`。健康检查：

```sh
curl -fsS http://127.0.0.1:8799/api/health
```

## 持久化与升级

`TAVERN_STATE_DIR` 是实例数据的唯一根目录，包含世界、角色卡、世界书、故事、
模型配置、语音配置与世界素材。升级源码时保留该目录即可。

推荐把状态目录放在仓库外，或至少保留默认的 `./tavern-state` 并确保它不进入版本控制。
不要把密钥、状态目录或日志提交到 Git。

## 网络暴露

默认只监听 `127.0.0.1`。需要远程访问时，应在 Tavern 前放置带 TLS 和认证的反向代理，
并配置 `TAVERN_ALLOWED_ORIGINS`。不要直接把无认证的运行时监听到公网地址。

## 独立模式不包含什么

- 不会安装或调用 Hermes 技能。
- 不会自动注册 ClawChat Liveware。
- 不会同步 ClawChat 昵称、语言或身份。
- 不会为其他 Agent 自动创建工具定义。

这些能力属于适配层，而不是 Tavern 核心运行时。
