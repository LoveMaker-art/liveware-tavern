# Character Card Field Mapping

Use this contract whenever a card is imported, created, localized, repaired, or attached to a world. It defines the boundary between source-card compatibility and Tavern's effective character model.

## Authority And Precedence

Tavern preserves the familiar SillyTavern fields for round-tripping, then derives three canonical objects used by the UI and generation runtime:

- `profile`: durable identity and behavior.
- `entry`: initial scenario, opening, and dialogue examples.
- `performance`: character-local prompt instructions.

For each canonical section, a non-empty top-level canonical value takes precedence over `extensions.tavern.profile`; canonical values take precedence over legacy prose. For portable SillyTavern V2/V3 source cards, put evidence-backed fine-grained fields under `extensions.tavern.profile`. After import, Tavern stores the effective canonical value in top-level `profile`. Import conversion guarantees shape, not semantic correctness. Never claim a field was extracted correctly without inspecting its evidence.

## Source-To-Canonical Mapping

| Source field | Tavern target | Rule |
|---|---|---|
| `name` | `profile.identity.name` | Required stable display name. |
| `nickname` | `profile.identity.aliases[]` | Used only when explicit aliases are absent. |
| plain `description` | `profile.identity.description` | Preserve concise stable identity facts; move other content to its proper owner. |
| `personality` | `profile.personality.summary` | Legacy fallback only; prefer explicit traits, values, motivation, fears, and boundaries when evidence supports them. |
| `scenario` | `entry.initial_scenario` | Starting/default situation, not current story state. |
| `first_mes` | `entry.first_message` | Opening beat. |
| `mes_example` | `entry.example_dialogue` | Voice examples, not world facts. |
| `system_prompt` | `performance.system_prompt` | Character-specific identity, voice, or knowledge constraints only. |
| `post_history_instructions` | `performance.post_history_instructions` | Rare persistent character constraint. |
| `alternate_greetings` | top-level `alternate_greetings[]` | Preserve as alternate openings. |
| `character_book` | standalone worldbook on attachment | Character-local lore may travel with the card; global lore must be separated. |
| `tags`, `creator`, `character_version`, unknown `extensions` | preserved source metadata | Do not discard or reinterpret them as character facts. |

## Structured Description Sections

When `description` uses `<角色>` or `<character>` sections, the runtime recognizes these mappings:

| Section | Tavern target |
|---|---|
| `<身份>` / `<identity>` | `profile.identity.description` |
| `<外观>` / `<appearance>` | `profile.appearance.summary` |
| `<性格>` / `<personality>` | `profile.personality.traits[]` |
| `<表达>` / `<expression>` | `profile.expression.speech_style` |
| `<能力>` / `<capabilities>` | `profile.capabilities.skills[]` |
| `<背景>` / `<background>` | `profile.background.summary` |
| `<关系>` / `<relationships>` | initial relationship hints; resolved into the world-local relationship graph when the cast is first attached and no live relationship state exists |
| `【当前状态】`, `【当前任务】`, `【当前位置】` | story-ledger scene notes; never durable profile fields |

Section parsing does not infer fine-grained facts. If the source explicitly provides age, gender, species, occupation, affiliations, story role, values, motivation, fears, powers, limitations, habits, or key history, write those facts into the matching canonical field. If evidence is absent, leave the field empty instead of inventing it.

## Canonical Profile Fields

```text
profile.identity
  name, aliases, description, gender, age, species,
  occupation, affiliations, story_role

profile.appearance
  summary, features, attire

profile.personality
  summary, traits, values, motivation, fears, boundaries

profile.expression
  speech_style, habits, mannerisms

profile.capabilities
  skills, powers, limitations

profile.background
  summary, key_history
```

Do not duplicate the same sentence across `description`, `personality`, and canonical sections. Legacy fields remain compatible source text; canonical fields are the effective structured representation.

## Content Routing

| Content | Owner |
|---|---|
| Stable character identity, appearance, behavior, voice, ability, background | Character `profile` |
| Default opening situation and greetings | Character `entry` |
| Character-local generation constraint | Character `performance` |
| Geography, organizations, history, rules, shared public facts | Worldbook |
| User's role inside this world | World-local Persona / 我的角色 |
| Events, current location, injuries, possessions, active goals, learned facts | Story ledger and dynamic cast state |
| Current relationship conclusions | World-local relationship graph |
| Narration/dialogue markup and global output format | Runtime output protocol |

An imported `{{user}}` identity must be classified before use: move the user's playable identity to Persona, public facts to worldbook, and relationship defaults to the relationship graph. Never leave a named source protagonist ambiguously occupying the user's identity.

## Required Workflow

1. Import through `add`, `add-original`, or the console importer; never write directly into a production JSON file.
2. Inspect the preserved source fields and canonical `profile`, `entry`, and `performance` separately.
3. Move world lore, user identity, current-scene facts, and relationship state to their proper owners.
4. Populate fine-grained canonical fields only from explicit source evidence. Record uncertainty by leaving fields empty, not by guessing.
5. Run `card-audit`. Repair high-severity identity, voice, opening, `{{user}}`, or worldbook-mixing findings before using the card as a core role.
6. Attach the reusable card to the intended world. Verify the independent `runtime_cast` copy, relationship graph, Persona boundary, and opening with `diagnose <world>`.

The reusable library card is a template. Once attached, the world's `runtime_cast.characters[]` profile is authoritative for that story; later state updates must not rewrite the reusable library source.
