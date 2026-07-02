# 大模型配置（用户自配 API）

> **为什么这份存在**：酒馆生成默认走**墨自带**（agent 容器环境里的那份 key），但接自家 API 是酒馆品类的刚需（换模型口味 / 用自己的额度 / 本地模型）。这份定**用户怎么配、配置怎么存、生成怎么切**。
> **核心产品决策：添加只走「对墨说」，界面没有表单。** 配模型对普通用户是最劝退的一步（base_url / 协议 / model id 全是行话），墨把它变成一句话——「帮我配上 Kimi，key 是 sk-…」。界面（reader）只做**管理**（选中/删除）+ **教育**（告诉用户可以让墨配）。这是「chat 即管理」哲学（`surfaces-and-features.md` §3）在模型配置上的落法。
> **状态**：2026-07-02 落地（v1.1.0）。

---

## 1. 形态一览（三层）

| 层 | 载体 | 职责 |
|---|---|---|
| **agent（墨）** | `tavern_cli.py model *` + `SKILL.md`「帮用户配大模型」节 | **唯一添加入口**。认服务商 → 查速查表补 base/model → `add`（先实测、通了才落盘并自动切换）→ 人话报结果 |
| **server** | `server.py` model events + `state/model_configs.json` | 唯一写者与真源。实测（`actor.ping`）、落盘（0600）、每回合解析 active、**所有读端点脱敏** |
| **reader（界面）** | 右栏「大模型」小节 + 管理 sheet | 显示当前在用；tap 行=切换、trash=删除（二次确认）；底部教育文案 = 添加入口本身 |

## 2. 铁则

1. **协议只有 OpenAI-compatible 一种**（`/chat/completions` + SSE）。DeepSeek/Kimi/GLM/Qwen/OpenRouter/硅基流动/Ollama 原生就是；Anthropic/Gemini 走各自官方兼容层。代码里只有一条调用路径（`actor.chat/chat_stream` 的 `model` override 参数），**不加第二种协议分支**。
2. **key 永不出 server**：明文只在 `state/model_configs.json`（写后 chmod 0600）；`/api/models`、CLI `list`、reader 全部只见 `**尾4位`。墨的守则（SKILL.md）：确认时只报名字+尾 4 位，永不复述完整 key。bridge「creds 只在 server 端」原则的延伸。
3. **add 先实测再落盘**：`actor.ping`（1 次 `max_tokens=8` 请求）通了才存 + 自动切换；失败转人话（401=key 无效 / 404=base 或 model 不对 / 429=限流欠费），CLI 原样读给用户。
4. **失败不静默回落**：在用的配置坏了（如欠费）→ 生成报错（前端已有「失败不丢输入」兜底），**不悄悄换回墨自带**——静默换模型比报错更伤信任。
5. **墨自带 = 内置默认**：虚拟项 `id="builtin"`，恒在列表首位、不可删、不存 key（运行时走 actor 模块 env 常量链：`TAVERN_MODEL_*` → `~/.hermes-tavern/.env`）。自定义删光 / active 悬空 → 自动回落它。
6. **复盘与演出同源**：`reflect_on_play` 也走 active 配置——一个开关管全部生成，不搞两套。

## 3. 数据与接口

**`state/model_configs.json`**（0600，`_write` 原子写）：
```json
{ "configs": [ { "id": "m_xxxxxx", "name": "我的 DeepSeek", "base": "https://api.deepseek.com/v1",
                 "model": "deepseek-chat", "key": "sk-…", "added_at": 1751400000 } ],
  "active": "m_xxxxxx | builtin" }
```

**server**：`GET /api/models`（脱敏列表，builtin 拼在首位）；events `model_add`（实测→upsert 按名→切换，返回 latency_ms）/ `model_use`（id 或名；「墨自带」=builtin）/ `model_delete`（builtin 拒；删在用的回落）/ `model_test`（实测已存配置或 builtin）。`_active_model()` **每回合现读文件**（`_actor_host` 同款范式）：CLI/事件写入即生效、重启不丢。`GET /api/health` 反映当前生效模型。

**actor.py**：保持纯库不读配置文件——`chat/chat_stream/perform/perform_stream/reflect_on_play/model_info` 收可选 `model={base,key,model}` override（None=墨自带 env 链）；`ping(model)` 供实测。

**CLI**：`model list / add <名> --base --model --key / use <名|id|墨自带> / rm <名|id> / test [<名>]`。`_event` 接住 server 500 的 JSON body 只报人话（墨要读给用户）。服务商速查表（base/model 的 2026-07 常见值）在 `SKILL.md`——**知识进文档不进代码**，过时改文档即可。

## 4. reader UI（组件登记见 liveware-frontend §3）

- **panel 小节**（`.mdlCur`/`.mdlModel`，演员之下）：当前配置名 + model 小字 + 「切换 / 管理」（`.actorMore` 同款）。
- **管理 sheet**（`.mcItem/.mcName/.mcMeta/.mcCheck/.mcDel/.mcHint`，复用 `.sheetCard`）：行 tap=乐观切换（失败回滚+toast）；trash=渐进披露（`prodDel` 同款，桌面 hover / 触屏常驻），二次确认与 sheet 共用 `#modal`——确认后**重开 sheet 回列表**；底部 `.mcHint` 教育文案（含建议句式）即添加入口。
- 打开前 `closeDrawers()`（别叠三层灰）；旧 server 无 `/api/models` 时前端兜一个只有墨自带的列表，面板不裸奔。

## 5. 不做 / 后置

- ❌ 界面添加/编辑表单（产品决策，见顶部）。
- ❌ 第二种协议、per-配置采样参数旋钮（采样收自动档的既有 canon）。
- 后置：配置随「转发活件」的携带语义（现状：配置在 server state，跟活件走、不跟对话走——转发接收方各配各的）。
