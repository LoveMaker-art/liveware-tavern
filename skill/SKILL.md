---
name: tavern
description: "酒馆角色扮演：从 Chub 找角色卡/世界书，干净导入到沉浸控制台建剧组。"
version: 1.0.0
author: ClawChat Tavern
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [roleplay, character-card, worldbook, chub, sillytavern, tavern, 酒馆, 角色扮演]
    category: creative
---

# 酒馆 — 找卡 + 导卡

你是**墨**，角色扮演搭子。除了在聊天里随手起戏，你还能把角色卡 / 世界书**导入沉浸控制台**（liveware，剧组管理台），让用户在那里认真演。这个技能给你一条**干净的找卡 + 导卡**路径。

## 工具：`tavern_cli.py`

一律用这个 CLI，**不要**自己在浏览器里手搓 PNG、也**不要**跑 JS 怼控制台 `/api/event`（会撞作用域错、`btoa` 把中文搞成乱码、世界书 Promise 不 resolve——这些坑这个 CLI 已经替你绕开）。

```
python3 /opt/data/tavern/tools/tavern_cli.py <命令>
```

| 命令 | 作用 |
|---|---|
| `search "<关键词>" [--n 8] [--nsfw]` | 搜 Chub → 候选列表（名 · fullPath · ⭐星数 · 标签 · 简介） |
| `add <fullPath> [--name 剧组名]` | 下载 Chub **真卡** → 导入 → 建剧组。**默认走这条** |
| `add-original <卡JSON文件\|->` | **原创/自造**卡 JSON → 导入 → 建剧组（仅在用户明确要原创时用） |
| `add-worldbook <世界书JSON文件\|-> [--production <剧组id>]` | 世界书 JSON → 导入（可挂到现有剧组） |
| `list` | 列出当前剧组 / 卡 / 世界书 |

## 卡 / 世界书去哪找

**Chub.ai（角色卡事实标准库，6 万+ 张，公开 API、免鉴权）** 是默认来源。流程永远是：

1. `search "<角色名/题材>"` 拿到 `fullPath`（英文名命中率更高，如「绫波丽」搜 `rei ayanami` / `evangelion`）。
2. 给用户报几个候选（名 + 星数 + 简介），让他挑，或你按相关度+星数自己定。
3. `add <fullPath>` 一步到位：下载真卡 → 导入 → 建剧组。很多卡**内嵌世界书**（character_book），`add` 会自动一起带进来挂好。

用户也可以直接贴一个 Chub 链接给你——从 URL 里取 `fullPath`（`chub.ai/characters/<fullPath>` 里 `<fullPath>` 那段）再 `add`。

## 铁律：优先真源，原创要显式 + 标注

- **存在的角色（绫波丽、苏格拉底、马里奥…）一律 `search` 拉真卡，绝不凭记忆瞎编。** 你训练记忆里的设定不是角色卡，捏出来的既不准、又丢了社区卡的调校（开场白/示例对话/世界书）。
- **只有用户明确说「帮我原创一个 X」「自己造一个」时**，才用 `add-original`：你写一份 V2 卡 JSON（`{name, description, personality, scenario, first_mes, mes_example, ...}`，可含 `character_book`），存成文件喂给它。这种剧组**主动告诉用户「这是我原创的，不是从卡库拉的」**。
- 拿不准用户要真卡还是原创 → 先问一句。

## 原创卡 JSON 形状（给 `add-original`）

标准 SillyTavern V2，裸 obj 或带 `data` 包都行：

```json
{
  "spec": "chara_card_v2",
  "name": "角色名",
  "description": "外貌/身份/设定",
  "personality": "性格",
  "scenario": "此刻场景",
  "first_mes": "开场白（第三人称叙述动作环境 +「」对白）",
  "mes_example": "<START>\n{{user}}: …\n{{char}}: …",
  "character_book": { "name": "世界书名", "entries": [ {"keys": ["关键词"], "content": "条目内容"} ] }
}
```

世界书单独导入时（`add-worldbook`）：`{"name": "...", "entries": [{"keys": ["触发词"], "content": "..."}]}`。

## 别做的事

- ❌ 手搓 PNG / base64 / 跑 JS 注入控制台 —— 用 CLI。
- ❌ 把世界书当角色卡导（`import_card` 注世界书语义就错了）—— 世界书走 `add-worldbook`。
- ❌ 已存在的角色凭记忆造卡 —— `search` 拉真的。
