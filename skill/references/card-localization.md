# Card Localization (English → Chinese)

Use this reference when the user wants to translate an imported Chub/SillyTavern character card and its associated worldbook from English to Chinese.

## Prerequisites

- The card must already be imported via `tavern_cli.py add`.
- The card file lives at `/opt/data/tavern-state/cards/<card_id>.json`.
- If the card had an embedded `character_book`, the tavern runtime extracted it as a standalone worldbook at `/opt/data/tavern-state/worldbooks/wb_<card_id>.json`.

## Content Separation Principle

When localizing a card with an embedded worldbook, restructure content so each file has a clean concern:

| File | Should contain | Should NOT contain |
|------|---------------|-------------------|
| Card `description` | Main character only: appearance, abilities, personality, relationships, background | World lore, organization descriptions, other characters' profiles |
| Worldbook entries | World setting, factions/organizations, supporting characters' profiles | Main character's personal traits |

Cards from Chub often bundle everything in `description` (user background + org info + character). **Move world lore and org info into the worldbook; keep only the main character's info in the card description.** This avoids confusing the model about what is character vs. world.

## Complete Translation Checklist

Translate ALL of the following — missing any one means the card is still partially English at runtime:

### 1. Card JSON (`/opt/data/tavern-state/cards/<card_id>.json`)

| Field | Must translate |
|-------|---------------|
| `description` | ✅ Full translation |
| `first_mes` | ✅ Full translation |
| `alternate_greetings[]` | ✅ Each entry |
| `mes_example` | ✅ If present |
| `scenario` | ✅ If present |
| `personality` | ✅ If present |
| `system_prompt` | ✅ Add or rewrite in Chinese |
| `post_history_instructions` | ✅ Add in Chinese |
| `tags` | ✅ Consider adding Chinese tags |
| `character_book.entries[].content` | ✅ Translate each entry |
| `extensions.agnai.persona.attributes.text[]` | ✅ Mirror description translation |

### 2. Worldbook JSON (`/opt/data/tavern-state/worldbooks/wb_<card_id>.json`)

**This is the most commonly missed step.** The runtime reads from this standalone file, NOT from the card's embedded `character_book`. Translate:
- `name` — worldbook display name
- Each `entries[].content` — full Chinese translation
- Keep `keys`, `id`, `position`, `priority`, `selective` unchanged

### 3. System Prompt

Add or rewrite `system_prompt` in the card JSON to enforce Chinese output:

```json
"system_prompt": "你必须使用中文进行所有输出。包括：角色对话、心理活动、动作描写、场景描写、旁白叙述等全部使用中文。保留角色名和专有名词可使用原词。"
```

Include character-specific speech pattern instructions (e.g., Delta uses third-person self-reference, calls user "Boss").

### 4. Post-History Instructions

Add `post_history_instructions` as a short reinforcement:

```json
"post_history_instructions": "注意维持角色核心性格。保持中文输出。"
```

## Verification

After translating, verify all files are in Chinese:

```sh
# Check card
python3 -c "
import json
with open('/opt/data/tavern-state/cards/<card_id>.json') as f:
    c = json.load(f)
print('first_mes:', c['first_mes'][:80])
print('system_prompt set:', bool(c.get('system_prompt')))
"

# Check worldbook (the file the runtime actually reads)
python3 -c "
import json
with open('/opt/data/tavern-state/worldbooks/wb_<card_id>.json') as f:
    wb = json.load(f)
for e in wb['entries']:
    print(f'[{e[\"name\"]}] first 60 chars: {e[\"content\"][:60]}')
"

# Verify runtime picks up the changes
curl -s http://127.0.0.1:8799/api/library/worldbooks | python3 -m json.tool | head -20
curl -s http://127.0.0.1:8799/api/cards | python3 -m json.tool | head -20
```

## Persona Setup After Localization

After translating a card, set up the user's persona for the target world only when the user wants a custom in-story identity, not the default `{{user}}` role:

```sh
curl -s -X POST http://127.0.0.1:8799/api/event \
  -H "Content-Type: application/json" \
  -d '{"type":"set_persona","production_id":"<world_id>","name":"你","description":"<character description in Chinese>"}'
```

This writes to the current production's `persona` field and is injected into generation for that world only. It must not change other worlds.

**Do NOT POST to `/api/persona` directly** — that endpoint is legacy read-only and returns `{}` to avoid cross-world persona bleed. Use the `set_persona` event with `production_id`.

## Custom Character / Power Dynamic Restructuring

When the user wants to replace the default `{{user}}` with a canon character name (e.g., 席德 for Shadow) AND set up their own character as a separate entity:

### Step 1 — Decide Whether the Opening May Be Rewritten

Only rewrite `story[0]` for a brand-new world or when the user explicitly asks. If the user has already played turns, preserve story history and shift the scene through current-world lore/persona instead.

If rewriting is allowed, replace `{{user}}` in the production's cached first_mes with the canon name:

```python
with open(f'/opt/data/tavern-state/productions/{prod_id}.json') as f:
    prod = json.load(f)
prod['story'][0]['text'] = prod['story'][0]['text'].replace('{{user}}', '暗影大人（席德）')
for i in range(len(prod['story'][0]['alts'])):
    prod['story'][0]['alts'][i] = prod['story'][0]['alts'][i].replace('{{user}}', '暗影大人（席德）')
json.dump(prod, f, ensure_ascii=False, indent=2)
```

### Step 2 — Set Current-World Persona via Event API

```sh
curl -s -X POST http://127.0.0.1:8799/api/event \
  -H "Content-Type: application/json" \
  -d '{"type":"set_persona","production_id":"<world_id>","name":"你","description":"同样穿越到这个世界的人。拥有2倍暗影大人的魔力，最强。"}'
```

### Step 3 — Update Worldbook

- Rewrite the `Shadow`/protagonist entry to reflect the new power ranking (e.g., "第二强")
- Add a new entry for the user's character (trigger keys: `["你", "穿越者", "最强"]`)
- Update any organization entries that reference `{{user}}` as leader name

### Step 4 — Rewrite the Opening Scene

If the user wants their character present in the opening, rewrite `prod['story'][0]['text']` and `prod['story'][0]['alts'][0]` with the new scene that includes their character as a participant.

### Pattern: User Is Stronger Than Canon Protagonist

A recurring user preference: the user's persona is stronger than the canon protagonist (e.g., "2倍魔力，最强，暗影第二强"). When this comes up:

1. **Worldbook**: Update the protagonist entry to say "第二强". Add a new worldbook entry for the user with trigger keys like `["你", "穿越者", "最强"]` and content stating they are the strongest.
2. **Production opening**: The canon protagonist (席德) interacts with the card character (Delta); the user's character is present as a bystander. Delta detects the user's overwhelming magic and mistakes them for an enemy (魔人). This creates immediate dramatic tension and a natural entry point for the user.
3. **Persona description**: State the power ranking explicitly so the model always knows who is strongest.

## Common Pitfalls

- **Production file caches `story[0]` separately.** The `tavern_cli.py add` command stores the card's `first_mes` into the production file at `/opt/data/tavern-state/productions/<prod_id>.json` under `story[0].text`, and alternate greetings under `story[0].alts`. Updating the card file's `first_mes` does NOT update the production. Edit `story[0]` only for a brand-new world or with explicit user permission:

  ```python
  with open(f'/opt/data/tavern-state/productions/{prod_id}.json') as f:
      prod = json.load(f)
  prod['story'][0]['text'] = cn_first_mes
  prod['story'][0]['alts'] = [cn_first_mes, cn_greeting_1, cn_greeting_2]
  json.dump(prod, f, ensure_ascii=False, indent=2)
  ```

- **Worldbook file is separate from card file.** Translating the card's `character_book` entries does NOT update the standalone worldbook the runtime reads. Always check both.
- **`extensions.agnai.persona.attributes.text` mirrors `description`.** If the card has an `agnai` extension block, its `text` array contains a copy of the description — update it too.
- **The runtime caches on read, not on write.** After updating the files, the runtime picks up changes on the next API call. No restart needed.
- **Some cards have no `system_prompt`.** Always add one when localizing, or the model may default to English for narration and scene descriptions.
- **`alternate_greetings` may be empty.** Check `len(card.get('alternate_greetings', []))` — if 0, the card has only the default `first_mes`.
- **Card `name` field may be null.** The display name comes from the top-level `"name"` field in the JSON, not `data.name`. Set it explicitly.
