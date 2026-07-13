# Worldbook Authoring

Use this reference when designing, importing, auditing, or repairing lore/worldbook entries for Ruotang's Tavern.

## Purpose

A worldbook answers: **what facts should the model know only when relevant?**

It is not a second character card and not a transcript. It is a selectively injected knowledge base for places, factions, systems, secrets, objects, public facts, and background rules.

## Entry Types

- **Core premise**: small constant entries that define the world and cannot be omitted.
- **Faction/organization**: triggered by faction names, members, operations, or conflicts.
- **Place/location**: triggered by place names and scene movement.
- **System/rule**: magic, school, law, technology, social hierarchy, combat rules.
- **Secret/information boundary**: who knows, who suspects, who must not know.
- **Object/asset**: important item, document, weapon, artifact, uniform, token, wound, debt.
- **Relationship/public reputation**: facts that many characters in the world can know.

## Fields And Meaning

- `keys`: primary trigger words.
- `secondary_keys` + `selective=true`: require a second condition before injecting.
- `constant=true`: always inject. Use sparingly.
- `recursive=true`: injected content may trigger more entries. Use rarely and intentionally.
- `exclusion_keys`: suppress when certain words appear.
- `priority`: higher entries fit first when budget is limited.
- `position`: `before_char` for broad setting before role material; `after_char` for nearby context after character material.
- `enabled=false`: keep but disable.

## Trigger Design

Good keys are specific:

- `米德加尔魔剑士学园`
- `迪亚波罗斯`
- `三越商会`
- `入学手续`
- `圆桌骑士`

Risky broad keys:

- `学校`
- `商会`
- `王国`
- `任务`
- `秘密`
- `教团`
- `学生` / `老师` / `班主任` / `初中` / `初三` — common setting words in school stories; fire on almost every turn
- `深圳` / `东京` / `伦敦` — city/country names that appear naturally in setting description
- Character names (e.g. `苏念清`, `赵明远`, `周小曼`) — using a character name as a trigger key causes the entry to fire whenever that character is mentioned, which in a multi-character world means nearly every turn
- one-character pronouns or common particles

**The core principle**: trigger words should be **specific scene signals, relationship states, or event markers**, not character names or generic setting words. When a worldbook entry fires on every turn, it loses its purpose as selective context injection and becomes dead weight.

**Fix pattern**: replace character names and common words with concrete triggers:

| Before (broken) | After (fixed) |
|---|---|
| `苏念清, 赵明远, 周小曼` (character names) | `深圳湾公园, 红树林, 奶茶店, 等公交, 放学路上` (scene signals) |
| `师生, 禁忌, 学生, 保守, 另一面` (generic) | `苏总, 师生关系, 班主任` (specific relationship states) |
| `深圳, 初中, 初三, 海边` (setting words) | `深圳湾, 红树林栈道, 校门口奶茶店` (specific locations) |

When a character name is too broad, use selective triggers:

```json
{
  "keys": ["伽玛", "三越"],
  "secondary_keys": ["商会", "资金", "手续", "经营", "公开身份"],
  "selective": true
}
```

This prevents any mention of a character from dragging in unrelated institutional lore.

## Constant Entry Rules

Use `constant=true` only for:

- world identity that must always be known;
- central cast relationship that affects every scene;
- safety/continuity facts that should never disappear;
- **NSFW sensory directives**: a constant entry carrying explicit writing instructions (body parts, sensory detail, pacing, prohibitions) that should be in context for every turn to prevent the model from fading to black or skipping physical description. See §NSFW Constant Injection below.

Do not make entries constant just because they are important. Important but situational lore should have precise keys and priority.

## NSFW Constant Injection

Keep worldbook entries limited to world facts, scene conditions, and content-specific continuity. Global output formatting, punctuation, sentence boundaries, narration markup, and dialogue markup belong exclusively to the runtime output protocol and must never be copied into a worldbook entry.

Entry configuration:

- **priority**: 10 (highest, injected closest to character material)
- **insertion_order**: 100 (near character card)
- **position**: `before_char`
- **keys**: focused set of body parts, actions, and scene signals. Remove single-character broad keys (`硬`, `软`, `跪`, `压`, `撑`) — they fire on non-NSFW turns and pollute context.
- **content**: direct writing directives structured as numbered imperatives. Do NOT write as a spec document — the model skips long checklists. Make each line an actionable command.

### Mandatory Sections

A content-specific constant entry must not contain runtime formatting rules. Keep only the scene-specific requirements that the user explicitly requested.

```
一、拟声词
性爱场景必须在叙事中直接嵌入拟声词，不加星号包裹，单独成行：
啪 / 啪啪 —— 肉体碰撞
噗滋 / 咕啾 —— 体液挤压与搅动的水声
啵 —— 拔出时分离声
嗯 / 啊 / 哈啊 / 唔 —— 喘息与呻吟
禁止用「发出XX的声响」「传来XX的声音」替代——直接用拟声词。

二、台词
性爱场景每段穿插角色台词——骚话、求饶、命令、叫名字、承认快感。禁止角色全程沉默。

三、神态
写出眼睛（翻白/失焦/半闭/眼泪打转）、嘴巴（微张/流口水/咬唇/嘴角拉丝）、
脸色（潮红从脸颊→耳根→脖颈→胸口的蔓延路径）、眉毛（紧皱/舒开）。

四、器官与动作
必须使用具体器官名称——龟头、阴道、阴唇、子宫口、阴蒂、阴茎——
禁止用「那里」「顶端」「体内」「下身」「入口」等模糊词替代。
每个动作写出器官交互：不是「手指滑了进去」而是「中指拨开阴唇插入阴道」；
不是「顶端没入」而是「龟头撑开穴口」。
写出器官的温度（滚烫的龟头）、湿度（湿滑的穴口）、软硬度（硬挺的阴茎）、
触觉（龟头刮过阴道皱褶）。

六、禁止
- 跳脱：一夜过去、事后、画面一转
- 文艺比喻替代直接描写（像海浪、像花开）
- 省略号替代动作（然后……、之后……）
- 角色在性爱中全程沉默无台词
- 用「发出XX的声音」替代拟声词
```

### PITFALL — "具体部位" Is Too Vague

The phrase "写出具体部位" causes the model to default to surface body zones (脖颈、腰肢、大腿) rather than organs (龟头、阴道、阴唇). Always list the required organ names explicitly and list the banned euphemisms. The model's natural tendency in Chinese erotica is literary euphemism — the instruction must actively counter this.

### PITFALL — Append-Only Degradation

When the user reports missing elements in NSFW output, do NOT append new rules to the existing entry. Each append makes the entry longer and less likely to be followed. Instead, **restructure**: merge overlapping entries, strip redundancy, and rewrite as a clean, prioritized block. The model follows short, forceful commands better than long specification documents.

### PITFALL — Descriptive Sound vs. Onomatopoeia

The model defaults to describing sounds ("发出黏腻的水声") rather than rendering them ("噗滋——"). The instruction must explicitly ban the descriptive form and require direct onomatopoeia embedding. Without this prohibition, the model consistently chooses description over rendering.

### When to use

The user explicitly asks for NSFW content with vivid sensory描写, or reports that intimate scenes lack visual detail, onomatopoeia, dialogue, or organ-level description.

### PITFALL — NSFW directive invisible to user

A constant worldbook entry carrying NSFW writing directives works for the generation pipeline but is NOT visible in the tavern UI's "世界设定" panel. When the user says "添加到世界设定" or "我怎么没看到", they expect the directive in the **director's note** (`note` command). Always set the `note` in addition to the worldbook entry — the worldbook handles generation, the note gives the user visibility and edit access.

### When not to use

The user wants fade-to-black, implied intimacy, or the story's tone doesn't call for explicit content. A constant NSFW entry will affect every turn, including non-intimate scenes — the model may drift toward sexual暗示 in neutral dialogue. If this becomes a problem, switch to triggered mode (`constant: false`) relying on the comprehensive key list.

## Secret And Knowledge Boundary Rules

Secrets should include who knows them:

```text
秘密：阿尔法的某个心思只有暗影明确察觉；德尔塔不知道，其他七影暂未被告知。
```

Avoid writing secrets as universal truth if characters should not act on that knowledge.

## User Identity Rules

- User's playable identity belongs in persona.
- Public reputation can be lore.
- Power ranking can be lore if other characters should reason from it.
- Do not leave generic `{{user}}` in imported lore without deciding what it means.

## Split/Merge Rules

Split entries when:

- the triggers differ;
- one part is constant and another is situational;
- a secret has different knowledge boundaries;
- the content is longer than a screenful and only part is usually relevant.

Merge entries when:

- they share the same keys and are always needed together;
- duplicate facts compete;
- a broad entry repeats card content without adding world knowledge.

## Audit Checklist

Run:

```sh
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py lore-audit "<world>"
```

Then check:

- Are constants truly always needed?
- Are broad keys causing accidental injection?
- Are duplicate keys intentional?
- Is recursive disabled unless deliberately needed?
- Are secrets labeled with who knows them?
- Is user identity in persona rather than lore?
- Are character personalities in cards rather than global lore?
- Are long entries split into smaller triggerable facts?

## Lore Fix Planning
## Lore Fix Planning

Use `lore-fix <world> --plan` after `lore-audit` when the user asks how to repair a worldbook. It is read-only and should be used before editing data.
The repair plan prioritizes:

- high severity: empty content, missing triggers, entries that cannot enter context;
- medium severity: broad trigger keys, `{{user}}` leakage, recursive pollution, overlong constant entries;
- low severity: duplicate keys and long entries that should be split.

**PITFALL — `lore-fix --plan` blind spots**: the CLI's automated analysis only flags trigger key *duplication* across entries. It does NOT catch:

- character names used as trigger keys (e.g. `苏念清`, `赵明远`) — these fire on every mention of that character;
- common setting words (e.g. `深圳`, `初中`, `初三`, `学生`) — these appear in nearly every turn;
- the combination of both making a worldbook effectively constant injection with no selectivity.

When `lore-fix --plan` returns only `[低]` severity items but the user reports that lore is "always firing" or "feels like it's injected every turn", manually inspect the trigger keys for character names and common setting words. The fix is the same pattern: replace with specific scene signals, relationship states, or event markers.

Do not auto-apply fixes unless the user explicitly asks. Worldbook fixes can change story behavior, so propose the plan first, then edit the smallest necessary entries.
## Conservative Apply

`lore-fix <world> --apply --confirm` may be used only for conservative mechanical fixes: disable recursive scanning and replace over-broad trigger keys with narrower candidates. It must not rewrite lore content or change story facts. Run `lore-audit` again after applying.
