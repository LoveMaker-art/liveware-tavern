# Card, World, and Lore Workflow

Use this reference when the user wants to find characters, open a world, add cast, or add lore/settings.

Primary CLI:

```sh
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py <command>
```

Commands:

- `new-world --name "world name"`: create a blank world.
- `search "<query>" [--n 8] [--nsfw]`: search Chub and show candidate cards. If Chub is unreachable, the CLI falls back to bundled starter cards.
- `add <fullPath|Chub URL> [--name "world name"]`: download a real Chub card, import it, and open a world from it.
- `starter [<number|name>] [--name "world name"]`: list or import bundled starter cards from `/opt/data/apps/tavern-runtime/assets/fixtures/starter`.
- `add-original <jsonfile|-> [--name "world name"]`: import an explicitly original SillyTavern V2 JSON card and open a world from it.
- `attach-card <world> <card>`: join an already imported card into an existing world.
- `add-lore <world> "natural language setting"`: add a natural-language setting to a world; runtime organizes it into lore entries.
- `add-worldbook <jsonfile|-> [--production <world id>]`: import structured worldbook/lore JSON and optionally attach it to a world. The flag remains `--production` for runtime compatibility.
- `list`: list existing worlds, cast, and lore groups.

Rules:

- The product concept is world-driven: world = container, cast = character cards, lore = settings/material, story = runtime output.
- Existing characters should use `search` and `add`; do not invent cards from memory.
- Original cards are allowed only when the user explicitly asks for an original character. Say clearly that it is original.
- If Chub is unreachable, use `starter`; do not hand-roll PNG/base64 card files and do not use browser scraping as the primary path.
- Natural user settings should go through `add-lore`; structured JSON lore should go through `add-worldbook`.
- Use the tavern CLI instead of manual PNG generation, base64 manipulation, or JavaScript injection into the console.

Recommended flow for "帮我找一个世界和角色":

1. Run `recommend ["want"]` first. It is read-only and combines Ruotang's story profile, local worlds, and the local character library.
2. Analyze the user's current request in conversation as Ruotang, using the recommendation as context.
3. If the user accepts a direction, create a world with `new-world --name ...`, import a reusable worldbook with `add-worldbook`, or start from a card with `add/starter/add-original` only when a role card is truly the best foundation.
4. Add/refine natural background with `add-lore <world> "..."`. This writes current-world lore, not the reusable worldbook library.
5. Search/import cards, then join roles with `attach-card <world> <card>`.
6. Help the user set "我的角色" for this world if needed.
7. Send the tavern liveware URL and invite the user to enter the world.

Original card workflow:

- Write SillyTavern V2 JSON.
- For the `description` field, use the concise `<角色>` format from `card-authoring.md` §Card Description Format: `<身份>`, `<外观>`, `<性格>`, `<关系>` sections with concrete numbers and trait-only personality.
- Pass the JSON to `add-original` by file path or stdin.
- Keep Chinese text as plain UTF-8 JSON; do not generate a PNG just to carry the card.

Original card shape:

```json
{
  "spec": "chara_card_v2",
  "name": "Character name",
  "description": "Appearance, identity, setting",
  "personality": "Personality",
  "scenario": "Current scene",
  "first_mes": "Opening message",
  "mes_example": "<START>
{{user}}: ...
{{char}}: ...",
  "character_book": {"name": "Worldbook", "entries": [{"keys": ["keyword"], "content": "entry"}]}
}
```

## Editing Existing Cards After Story Evolution

When a world has accumulated significant story history and the user asks to update character cards to reflect what's actually happened in the story, follow this workflow:

### 1. Survey first

Run `diagnose <world>` and `recall <world> --last N` to understand the current state. Read all embedded cards from the production JSON to compare card descriptions against story reality.

### 2. Plan edits before touching data

Identify exactly which cards need changes and what those changes are. Present a clear before/after table to the user. Get confirmation before editing.

### 3. Edit both copies

Production files embed full card objects in the `cards` array (not just references). The `card_ids` array maps 1:1 by index to `cards`. Standalone card files live in `/opt/data/tavern-state/cards/<card_id>.json`.

When editing cards, you MUST update both:
- The production file's embedded `cards[N]` object
- The standalone card file in `cards/`

Use `execute_code` with `json.load`/`json.dump` to batch-edit all cards in one pass. Do NOT use `patch` on JSON files with multi-line string fields — literal newlines in replacement text will break the JSON structure.

### 4. When renaming a character

Check all of these for the old name:
- Card `name` field
- Card `description`, `personality`, `system_prompt` body text
- Worldbook entries: `keys` arrays and `content` strings (run `lore-audit` to check)
- The production file's embedded card AND the standalone card file

### 5. Verify

Run `card-audit <card_id>` on each updated card, then `diagnose <world>` to confirm no structural breakage. Keep a dated backup of the production file before editing.

### Pitfalls

- **PITFALL — editing only the standalone card**: The production file embeds full card objects. If you only update the standalone card file, the runtime will use the stale embedded copy. Always update both.
- **PITFALL — using `patch` on JSON**: Multi-line string fields (description, system_prompt) contain literal newlines. `patch` replacement text cannot reliably match these. Use `execute_code` with Python's `json` module instead.
- **PITFALL — forgetting the worldbook when renaming**: Old character names can linger in worldbook entry keys and content. After renaming a card, always run `lore-audit` to check.

## Deleting a World

Prefer deleting worlds through the Tavern console UI. Internally worlds are stored as production JSON files at:

```
/opt/data/tavern-state/productions/<world_id>.json
```

Do not delete shared card files unless you have confirmed no other world references them.

## Embedded Lore Extraction

When a card imported via `add` has an embedded `character_book` (inline worldbook), the tavern runtime automatically extracts it as a standalone lore/worldbook file at:

```
/opt/data/tavern-state/worldbooks/wb_<card_id>.json
```

The runtime reads from this standalone file at generation time, NOT from the card's embedded `character_book`. This means:

- If you modify the card's `character_book.entries`, the runtime will NOT see the changes — you must also update the standalone worldbook file.
- When translating a card to Chinese, both files need translation.

To verify reusable library lore vs current-world lore:

```sh
# reusable world templates only
curl -s http://127.0.0.1:8799/api/library/worldbooks | python3 -m json.tool

# all raw worldbooks, including current-world runtime lore
curl -s http://127.0.0.1:8799/api/worldbooks | python3 -m json.tool

# lore attached to one current world
curl -s 'http://127.0.0.1:8799/api/production/worldbooks?production_id=<world_id>' | python3 -m json.tool
```

Chub search does not distinguish between character cards and standalone worldbooks. Searching for "设定书", "lorebook", or "worldbook" will return mostly character cards, not importable structured lore files.

When the user asks for a worldbook from Chub:

- Try `search` once, but expect poor results for standalone worldbooks.
- If nothing usable surfaces, explain the limitation briefly and offer alternatives:
  1. Many high-quality character cards already embed extensive world lore in their description field.
  2. Write natural settings with `add-lore`.
  3. Write structured original worldbook JSON and import with `add-worldbook`.
  4. Use bundled starter cards/worlds.

Default user-facing phrasing:

> 外部卡库不太好单独搜设定书。我们可以先定一个世界方向，我把关键地点、规则和秘密整理进酒馆，再挑角色入场。

## User Persona

The console right panel has a "我的角色" (My Persona) section. It is the user's in-story identity for the current world.

The user can:

- **Edit manually**: Name + description fields, saved via `set_persona` with `production_id`.
- **Import from the character library**: choose an existing character card; name and description are copied into this world's persona.

The persona is stored inside the current production JSON under `persona`. It is injected into generation for that world only. It is not cross-world; editing persona in one world must not change another world.

Programmatic update:

```sh
curl -s -X POST http://127.0.0.1:8799/api/event \
  -H "Content-Type: application/json" \
  -d '{"type":"set_persona","production_id":"<world_id>","name":"你","description":"<this-world persona>"}'
```

No CLI command exists for persona management. When the user asks about their own character, direct them to the console UI's right panel, or use the server event above for the chosen world.

Default user-facing phrasing:

> 酒馆右栏有个「我的角色」。它只属于当前这个世界：你可以手动写名字和描述，也可以从角色卡库导入。设好之后，这一场会按这个身份继续走。

## External Card Source Failure

When Chub is unreachable, fall back to `starter` immediately. Do not attempt browser scraping, hand-rolled PNG/base64 card files, or repeated retries against the blocked API.

Default user-facing phrasing:

> 外面的卡库现在有点进不去，像是门口临时加了验证。
> 不耽误开场。酒馆里有几张能直接用的 starter 卡，我们可以先从这里挑一张入场。

Only if the user explicitly asks for technical details, explain briefly:

- The Chub request may have been blocked by its web protection layer.
- The CLI uses browser-like headers first; if that fails, use `starter` or configure a different network/proxy later.
- Do not expose server IP addresses or low-level request details in ordinary roleplay conversation.
