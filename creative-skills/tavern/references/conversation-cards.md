# Conversation Cards

Use this reference when Tavern work needs to be presented directly inside a ClawChat conversation.

A conversation card is a compact Markdown presentation. It is not a second data model, an image, HTML, JSON, or an imitation of a native interactive card. The canonical data remains the Tavern world, character card, worldbook, and Persona structures.

## General Rules

- Use the user's current language.
- Keep one card focused on one decision.
- Prefer short labeled lines and blockquotes; avoid Markdown tables because they are difficult to scan on mobile.
- Show only facts useful for choosing, reviewing, or starting.
- Do not expose internal ids, file paths, raw JSON, audit traces, prompts, or tool output.
- Do not invent buttons, clickable controls, upload states, or completed writes.
- If the user asked only to browse or compare, do not write Tavern state.
- If the user already explicitly asked to create or import, perform the approved write and return a result card instead of asking for confirmation again.
- End with one natural next action, not a menu of many commands.
- For English conversations, translate the card naturally and use these labels: `World Preview`, `Genre & Mood`, `Your Role`, `Cast`, `Core Lore`, `Opening`, `Character Preview`, `Identity`, `Personality`, `Voice`, `Relationship`, `Entrance`, `Ready`, and `Added`.

## World Proposal

```markdown
### 世界预览｜<世界名>

> **类型**　<题材与氛围>
> **你在其中**　<用户角色的一句话定位>
> **登场角色**　<2-4 个名字及各自的一句话关系>
> **核心设定**　<最重要的 1-3 条世界规则>
> **开场**　<能直接进入第一幕的钩子>

回复「开始」，我就把这一场整理进酒馆；想改哪里，直接告诉我。
```

Do not display empty labels. If the user role is intentionally undefined, write `由你进入后决定` instead of guessing.

## Created World

```markdown
### 已备好｜<世界名>

> **登场角色**　<names>
> **世界设定**　<entry count or a compact factual summary>
> **开场位置**　<first-scene location or hook>

这场已经放进 Tavern，可以从右上角 Liveware 进入。
```

Only say `已备好` after verifying the world exists and its cast, lore, Persona, and opening match the approved plan.

## Character Proposal

```markdown
### 角色预览｜<角色名>

> **身份**　<age or life stage, occupation, affiliation when known>
> **性格**　<2-4 stable traits>
> **表达方式**　<voice and speech pattern>
> **与你的关系**　<starting relationship or stance>
> **入场方式**　<how this character enters the selected world>

这张角色卡可以加入「<world>」。确认后我再放进去。
```

Omit unknown fields instead of filling them with guesses. Keep world facts out of the character preview.

## Attached Character

```markdown
### 已加入｜<角色名>

> **所在世界**　<world>
> **角色定位**　<one concise line>
> **入场关系**　<one concise line>

角色已经就位，下一轮故事会读取这张世界内副本。
```

Only say `已加入` after checking both the reusable library source and the world-local effective copy.

## Delivering the Real Card File

If the user explicitly asks to receive the actual card file, attach the verified JSON or source PNG through ClawChat's native `MEDIA:<absolute_path>` mechanism. The conversational preview may be used as its caption. Never substitute a pasted JSON block for a requested file.
