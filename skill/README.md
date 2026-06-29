# 酒馆 skill — MVP 演员运行时

「角色 = 演员 × 剧本」落到代码：剧本 = 导入的角色卡(V2/V3 PNG)，演员 = `actor_self.md`(我们独有、跨剧组共享、会成长)，世界 = 世界书，现场 = 本剧组隔离故事线。控制台同源调它生成入戏回复。

## 文件

| 文件 | 作用 |
|---|---|
| `server.py` | 同源 HTTP server(stdlib)：serve `reader/` + `/api/*` 事件 + 状态文件。**演员运行时的壳** |
| `actor.py` | 拼 prompt(角色卡 × actor_self × 世界书 × 故事线) + 调模型(DeepSeek，urllib) |
| `card_import.py` | 解析 V2/V3 角色卡 PNG(`chara`/`ccv3` tEXt → base64 → JSON，保留未知 extensions) |
| `actor_self.md` | 演员「墨」的活·自画像种子(底色/对你的了解/签名/成长记)；运行时副本在 `state/actor_self.md` |
| `SOUL.md` | chat 侧「墨」人格(部署到 `~/.hermes-clean/SOUL.md`)。**也硬指路找卡/导卡走 `tavern_cli.py`**——gateway 里 enabled 技能 ≠ agent 一定会选(墨会跑去浏览器硬怼),靠 SOUL 永远在 context 来 steer + 禁反模式。**SOUL.md 热生效**(改完下条消息即拿到,无需重启;区别于新技能要重启才进会话) |
| `SKILL.md` | **agent 工具面**：墨的「找卡+导卡」技能(Chub 来源 + CLI 用法 + 优先真源/原创标注策略)。容器注册到 `skills/creative/tavern/`，gateway 启动扫描 |
| `reader/` | 控制台 UI：`index.html` `console.css`(沉静感) `app.js` `bridge.js`(同源事件总线) |
| `tools/make_test_card.py` | 生成 spec 正确的 V2 测试卡 + 世界书(纯 Python) |
| `tools/tavern_cli.py` | **墨的找卡+导卡 CLI**(纯 stdlib)：`search`(Chub)/`add <fullPath>`(拉真卡→导入→建剧组)/`add-original`(原创卡 JSON)/`add-worldbook`/`list`。打本地控制台 `/api/event` |
| `tools/bringup.sh` | **容器重启后恢复 Loop B**：起 server.py(setsid)+ liveware 重登 + tunnel bind + tunnel-agent。跑 `docker exec hermes-clean sh /opt/data/tavern/tools/bringup.sh`(持久化 v1.1 兜底；`/opt/data` 持久、`/root/.clawling` 易失) |
| `tools/smoke.py` | Loop A 冒烟：导卡→世界书→建剧组→first_mes→入戏对话→重生成 |
| `state/` | 运行时状态(JSON)：`cards/` `worldbooks/` `productions/`(=loadout+隔离故事线) `actor_self.md` `persona.json` `state.json` |

## 事件协议(`POST /api/event`，同源，复刻 digest bridge.js)

`import_card{png_base64}` · `import_worldbook{worldbook}` · `create_production{card_id,worldbook_ids?,name?}` · `switch_loadout{production_id}` · `send_message{production_id,text}`(同步返回 reply) · `regenerate{production_id}` · `edit_message{production_id,message_id,text}` · `actor_grow{change,reason}`(改写 actor_self.md) · `set_persona{name,description}`
GET：`/api/health` `/api/cards` `/api/worldbooks` `/api/productions` `/api/actor`

## 跑

```sh
# 模型 key：env 优先，否则自动从 ~/.hermes-tavern/.env 读 DEEPSEEK_API_KEY
python3 skill/server.py --port 8799          # 控制台 → http://127.0.0.1:8799
python3 skill/tools/make_test_card.py        # 生成 fixtures/lin.png + 世界书
python3 skill/tools/smoke.py                  # 对运行中的 server 跑 Loop A
```
预览：`.claude/launch.json` 的 `tavern` 配置(在 clawchat 仓)→ preview_start。
模型基座切换：env `TAVERN_MODEL_BASE` / `TAVERN_MODEL` / `TAVERN_MODEL_KEY`(默认 DeepSeek；可指本地 ollama)。

## 状态(2026-06-29)

- ✅ **Loop A 全绿**：导 V2 卡 + 世界书 → 拼完整 prompt → DeepSeek 入戏生成(世界书心结触发、故事线连续) → 控制台沉浸演出(桌面 master-detail / 移动全屏舞台 + 抽屉，明暗自适应) + 重生成/编辑/切换。preview 三态截图验过。
- ✅ **本地 Hermes agent**：容器 `hermes-clean`(HERMES_HOME `~/.hermes-clean`)，DeepSeek 基座。**干净激活实测：stripped config + 全新连接码 → 全新 `usr_01KW8SQPTXECF8E4XHYXF7708B`(≠ 旧 `usr_01KW0YR6`，全 home 零 `01KW0YR6` 污染) ⇒ 账号确实支持多 agent**(此前「一账号一 agent」结论是 cp 带身份 config.yaml 的污染所致，已推翻)。演员运行时 server.py 仍在 Mac 裸跑(Loop A)。
- ✅ **墨人格已部署 hermes-clean**：`skill/SOUL.md`(1532B)→`~/.hermes-clean/SOUL.md` + `docker restart`(避 gateway-restart 180s drain)；`hermes chat` 试戏冒烟完美入戏(三人称叙述 / 「」对白 / 给角色身体)，clawchat WS 已重连(4× ESTABLISHED → app.clawling.com:443)。
- ✅ **chat 试戏(ClawChat app)**：在 Windows rig 自驱实测通过——ClawChat 发消息 → 墨完美入戏(店长老周，三人称叙述 +「」)。注:已有会话里若有占位期旧消息会让模型在同会话内自报旧名(历史污染，非 bug)，fresh 会话自报「我叫墨」。account nickname 已正名为「墨」。
- ✅ **Loop B 全链路打通(2026-06-29，首试即通)**：控制台 server.py 跑在 **hermes-clean 容器内**(agent 自托管，解了 host 形态)→ `liveware` CLI 注册(login→`app create --agent-type hermes`→`tunnel bind … http://127.0.0.1:8799`)→ 公网 `app-02dd46427910ed17.apps.clawling.io` 从 Mac 外部 `/api/health` + `/` 首试 200 → 发进 ClawChat 渲染**活件卡** → 点开 Windows **独立容器窗**(`ClawChatLivewareWindow` / WebView2)显示完整沉浸控制台。**memory 记的 503 / 鉴权 flapping 已不复现**;liveware + tunnel-agent 二进制现随 clawchat 插件 0.14.0-31 装在 `/opt/data/clawchat/liveware/`。
  - 容器内部署:`docker cp skill hermes-clean:/opt/data/tavern` + `docker exec -d … python3 server.py --port 8799`(key 从容器 `/opt/data/.env` 的 `DEEPSEEK_API_KEY` 读;**必须 `-d` detached,前台 exec 一返回就杀掉后台子进程**)。重启容器后 server.py / tunnel-agent 不自起(v1.1 再做常驻)。
  - **读+写都过 tunnel 验过**:GET `/api/productions` + POST `/api/event`(send_message)外部首打,DeepSeek 入戏回包 200。⚠️ **relay 把 POST body 改 `chunked` 剥 `Content-Length`**,server.py 的 `_read_body()` 已兼容(否则只读 Content-Length 会拿到空 body → `type=None`,GET 好 POST 空的迷惑现象)。

## 护栏

纯 agent 侧；ClawChat 客户端零改、零新后端接口；状态只落 agent 侧文件，**active loadout 永不写能力服务器/member-backend**；复用 V2 格式不 fork ST；模型 creds 只在 server 端。
