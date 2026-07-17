# Character Card Authoring

Use this reference when creating, importing, translating, cleaning, or evaluating SillyTavern-style character cards for the Tavern.

## Purpose

A character card answers: **who is this person, how do they act, how do they speak, what do they want, and how do they relate to the user's persona or the world?**

It should not carry global world rules unless the lore is local to that character and no standalone worldbook exists.

## Recommended Card Fields

- `name`: stable display name.
- `description`: identity, appearance, role in the world, public reputation, key backstory.
- `personality`: behavioral tendencies, emotional style, speech rhythm, values, fears, contradictions.
- `scenario`: the starting situation or default relationship context.
- `first_mes`: the opening beat. It should establish location, body language, immediate tension, and an answerable hook.
- `mes_example`: examples of tone and rhythm. Use sparingly; examples strongly influence output format and voice.
- `system_prompt`: character-specific constraints only when truly needed.
- `post_history_instructions`: rare; use only for persistent character-specific generation constraints.
- `character_book`: character-local lore that should travel with the card, not global world knowledge.

## What Belongs In A Card

- Personal identity and social role.
- Motivations, desires, boundaries, fears, habits, tells.
- Relationship defaults toward the user's persona or other named characters.
- Speech style: formal/informal, sentence length, address terms, emotional restraint.
- Action style: how they move, hesitate, fight, comfort, deceive, or observe.
- Knowledge limits: what they do and do not know.

## What Does Not Belong In A Card

- Full geography, faction history, magic system, or school rules: put these in worldbook.
- The user's complete identity: put it in persona.
- Output format rules: runtime system protocol owns that.
- Current story facts that happened during play: story history/story state owns those.
- Temporary pacing instructions: author note owns those.

## Card Description Format (User Preference)

The user prefers a concise, list-style description format using XML-like section tags. When creating or optimizing cards for this user, follow this structure:

```xml
<角色 name="角色名">
<身份>
- 年龄，地点，职业/身份
- 关键背景（一行一条，不展开）
</身份>

<外观>
- 身高XXcm，体重XXkg
- 三围：XX-XX-XX（X杯），体型描述
- 发型、发色、眼睛、肤色、衣着
- 具体数字优先，不写举例描写
</外观>

<性格>
- 核心特质，一行一条
- 只写特征，不举例、不叙事、不心理分析
- 矛盾或反差可以写，但不要解释为什么
</性格>

<表达>
- 说话节奏、称呼习惯、常用语气
- 只写稳定表达特征
</表达>

<能力>
- 技能、力量及明确限制
- 没有来源依据的能力留空
</能力>

<背景>
- 影响当前身份的关键经历
- 当前剧情事件不要写在这里
</背景>

<关系>
- 角色名：关系类型 + 一两个关键事实
- 不说"他对她很好"，说"他按时接送但从不深入交流"
- 不分析情感，只陈述关系和事实
</关系>
</角色>
```

**Rules for this format**:

1. **身份**: age, location, role, key background only. One line per fact.
2. **外观**: concrete numbers (height, weight, measurements). For female characters, always include 三围 and cup size. Describe hairstyle, eyes, skin, clothing — specific, not impressionistic.
3. **性格**: traits only. No examples. No "she would sometimes..." narrative. No psychological deep-dive. If there's a contradiction, state it plainly.
4. **表达**: stable speech rhythm, address terms, and verbal habits. Do not repeat personality traits.
5. **能力**: evidence-backed skills, powers, and limitations. Do not infer missing powers.
6. **背景**: durable key history only. Current events belong in story state.
7. **关系**: name → relationship + one or two concrete facts. No emotional analysis. "He's kind" → wrong. "He brings gifts on holidays but never asks what she's reading" → right.
8. No `{{user}}` — use the character's actual name.
9. The format IS the setting. Don't pad it with narrative prose.

**When to use this format**: when creating original cards, when optimizing existing cards at the user's request, and when the user asks for a card to be "cleaned up" or "精简". Do not force this format on imported public cards unless the user asks.

For portable V2/V3 JSON, mirror evidence-backed fine-grained values into `extensions.tavern.profile` according to `field-mapping.md`. Do not duplicate whole prose blocks there; use the smallest structured values that add information beyond the legacy fields.

**Editing approach**: use `execute_code` with Python's `json.load`/`json.dump` to batch-update card fields (`description`, `personality`, `system_prompt`, `post_history_instructions`, `mes_example`). Do NOT use `patch` on JSON files with multi-line string fields — literal newlines in replacement text will break the JSON structure.

## Multi-Role Worlds

For multi-role play, each card should be strong enough to stand alone, but not so bloated that every turn becomes expensive.

Good multi-role card traits:

- Clear role in the ensemble: commander, scout, friend, rival, keeper of secrets, comic relief.
- Distinct speech and action patterns.
- Clear relationship to the user persona and to other cast members.
- Clear information boundary: what this character knows, suspects, or misunderstands.

Avoid:

- Writing the whole faction's full lore into every card.
- Making every character equally verbose.
- Giving all characters the same loyalty, tone, or dramatic function.
- Having multiple cards define the same world fact differently.

## Import/Cleanup Checklist

When importing an existing card:

1. Check for `{{user}}` and decide whether it should become persona, public lore, or a direct name.
2. Check if embedded `character_book` was extracted into `/opt/data/tavern-state/worldbooks/wb_<card_id>.json`.
3. Translate or normalize both card fields and extracted worldbook if needed.
4. Check first message format and whether it conflicts with tavern output protocol.
5. Remove accidental OOC/tool instructions from role fields.
6. Keep creator/source metadata; do not erase provenance without reason.

## First Message Guidelines

A good `first_mes` should:

- Open in a concrete place and moment.
- Show body language before exposition.
- Make the user's persona relevant.
- End with a hook the user can answer.
- Avoid deciding the user's feelings or actions.

Bad first messages:

- A long encyclopedia dump.
- A greeting with no scene.
- Speaking as multiple characters without clear labels.
- Explaining the app or roleplay mechanics.

## Card Quality Rubric

A card is ready when:

- The character has a distinct voice.
- The scenario gives a playable starting point.
- The first message can start a scene without extra explanation.
- The card does not smuggle global lore, user identity, or runtime format rules into the wrong place.
- Multi-role relationships and knowledge boundaries are clear enough for turn planning.

## Card Cleanup Pitfall

**PITFALL — deleting story-critical content**: When the user says "清理一下这张卡", "删无关内容", or "clean up this card", do NOT assume what is "unrelated." Content that seems irrelevant to the current scene — hidden relationships, backstory secrets, unresolved subplots, character connections — may be load-bearing for the world's narrative structure.

Before removing any story element:
1. Identify every subplot thread in the card (parentage, secret identities, hidden connections, unresolved conflicts).
2. If the user's instruction is ambiguous about what to keep vs. delete, ask explicitly: "母女线要保留吗？" — do not guess.
3. Only delete content the user explicitly marks for removal.

This is a first-class pitfall because deleting a hidden parent-child relationship or secret identity breaks the world's dramatic architecture, not just the current scene.

Run `card-audit <card>` before making a card the core of a world, after importing a public card, or whenever a role feels unstable. Treat it as read-only triage.

A usable card should have:

- clear identity and role boundary;
- enough personality or voice material for stable dialogue;
- a playable opening or enough scenario material to make one;
- no accidental user identity takeover when the console persona is being used;
- world/faction/history material separated into lore when it grows beyond the character's private context.

If `card-audit` reports high severity, do not use the card as a core opening role until description/opening are repaired. If it reports medium severity, the card can join a world but should be cleaned before long play.
## Card Fix Planning

Use `card-fix <card> --plan` after `card-audit` when a card is weak. It is read-only and should identify missing description, personality, first message, `{{user}}` leakage, and worldbook mixing. Do not rewrite public/imported cards automatically without explicit user confirmation.
