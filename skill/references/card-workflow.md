# Card, World, and Lore Workflow

Use this reference when the user wants to find characters, open a world, add cast, or add lore/settings.

Primary CLI:

```sh
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py <command>
```

Commands:

- `new-world --name "world name"`: create a blank world.
- `search "<query>" [--n 8]`: search Chub and show candidate cards. If Chub is unreachable, the CLI falls back to bundled starter cards.
- `inspect-card <file|HTTPS URL|Chub path>`: detect and audit a V1/V2/V3 JSON, PNG/APNG, or V3 CHARX without writing state.
- `import-card <file|HTTPS URL|Chub path>`: import a recognized external card into the reusable library.
- `add <fullPath|Chub URL>`: backward-compatible Chub-only import.
- `starter [<number|name>]`: list or import bundled starter cards from `/opt/data/apps/tavern-runtime/assets/fixtures/starter`.
- `add-original <jsonfile|->`: import an explicitly original SillyTavern V2 JSON card into the reusable library. Never use this command for a card found online.
- Add `--new-world [--name "..."]` to those commands only when the user explicitly wants a one-card world.
- `build-world <manifest>`: atomically create a complete world from cards, lore, Persona, and an opening.
- `attach-card <world> <card>`: join an already imported card into an existing world.
- `add-lore <world> "natural language setting"`: add a natural-language setting to a world; runtime organizes it into lore entries.
- `add-worldbook <jsonfile|-> [--production <world id>]`: import structured worldbook/lore JSON and optionally attach it to a world. The flag remains `--production` for runtime compatibility.
- `list`: list existing worlds, cast, and lore groups.

Rules:

- The product concept is world-driven: world = container, cast = character cards, lore = settings/material, story = runtime output.
- Existing characters should use network research plus `inspect-card` and `import-card`; do not invent cards from memory.
- Original cards are allowed only when the user explicitly asks for an original character. Say clearly that it is original.
- If Chub is unreachable, use `starter`; do not hand-roll PNG/base64 card files and do not use browser scraping as the primary path.
- Natural user settings should go through `add-lore`; structured JSON lore should go through `add-worldbook`.
- Use the tavern CLI instead of manual PNG generation, base64 manipulation, or JavaScript injection into the console.

## External Card Normalization

For cards found on the web, use this path:

1. Search public sources and identify the actual downloadable artifact. A detail page or preview image is not the card.
2. Run `inspect-card <artifact>` before writing anything. It must report V1, V2, or V3 and a non-empty character name.
3. Import the same artifact with `import-card`. This preserves source version, standard V3 metadata, vendor extensions, and unknown fields while deriving `profile`, `entry`, and `performance`.
4. Apply `field-mapping.md`. Inspect semantic alignment and move world lore, Persona, current state, and relationship facts to their proper owners. Do not hand-copy source prose into production JSON.
5. Run `card-audit <card>` before making the card a core role. Structural normalization is automatic, but semantic quality and fine-grained fields still require evidence-based review.
6. Localize only when requested, and retain creator/source attribution. Do not silently rewrite a public card as an original card.
7. Attach the library card to the chosen world. The runtime creates an independent `runtime_cast` role with an immutable `origin_profile` and one effective `profile`.
8. Verify with `diagnose <world>`. Story-local changes remain in that world's effective profile and never mutate the library template.

### Format Compatibility

- V1: accepts flat JSON and legacy `chara` PNG fields, including common aliases such as `char_name`, `char_persona`, `world_scenario`, and `char_greeting`.
- V2: accepts wrapped JSON and `chara` PNG, including alternate greetings, character-local system prompts, extensions, and embedded `character_book`.
- V3: accepts wrapped JSON, `ccv3` PNG/APNG, and CHARX archives containing root `card.json`; preserves the resource manifest, `assets`, multilingual creator notes, source references, group-only greetings, and timestamps.
- Unknown root/data fields are retained as source metadata and are not injected into the story prompt.
- V3 embedded assets are preserved as a safe resource manifest. They do not automatically become a world background or theme; visual theming belongs to `tavern-world-visuals`.
- V3 group-only greetings are available as opening alternatives for multi-character worlds when no explicit world opening overrides them.

Reject ordinary images, HTML pages, arrays, cards without a name, oversized files, unsafe CHARX paths, and external URLs that are not public HTTPS addresses. Do not silently convert a rejected artifact into a newly invented card.

Recommended flow for "帮我找一个世界和角色":

1. Run `recommend ["want"]` first. It is read-only and combines the story curator's story profile, local worlds, and the local character library.
2. Analyze the user's current request in conversation as the story curator, using the recommendation as context.
3. If the user accepts a direction, assemble one complete-world manifest.
4. Preview it with `build-world <manifest>` and apply the same file once with
   `--apply --confirm --request-id <stable-id> --json`.
5. Require `verification.ok: true`, then send the bare URL from `app-link`.

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

Separate reusable templates from one world's evolving cast:

- `/opt/data/tavern-state/cards/<card_id>.json` is the reusable library template.
- `production.runtime_cast.characters[]` is the current world's authoritative cast.
- `origin_profile` is the immutable profile captured when the role entered that world.
- `profile` is the only effective profile shown in the UI and injected into generation.

The runtime reviews every 15 confirmed turns and applies only evidence-backed durable changes to the effective `profile`, persistent status, and relationship graph. It never writes story evolution back to the reusable library card.

Character evolution is strictly incremental. It reads only the newly eligible 15-turn batch that advances the plot ledger. A ledger rebuild must preserve the existing cast and must not replay historical turns through the character-state model. If either the ledger update or character update fails during a normal batch, neither checkpoint advances.

When the user explicitly asks to edit a role, follow this workflow:

### 1. Survey first

Run `diagnose <world>` and `recall <world> --last N` to understand the current state. Inspect the role under `production.runtime_cast.characters[]`, not a hydrated `cards` projection.

### 2. Plan edits before touching data

Identify exactly which cards need changes and what those changes are. Present a clear before/after table to the user. Get confirmation before editing.

### 3. Edit the intended scope

- For the current world only, use the Liveware `update_cast` event. It updates `runtime_cast` and immediately refreshes the UI/model projection.
- To revise the reusable template for future worlds, edit the standalone library card only after explicit user confirmation. Existing worlds retain their own copies.
- Never maintain a production `cards` cache manually; it is a hydrated projection and is stripped when the production is saved.

### 4. When renaming a character

Check all of these for the old name:
- Card `name` field
- Card `description`, `personality`, `system_prompt` body text
- Worldbook entries: `keys` arrays and `content` strings (run `lore-audit` to check)
- Whether the request is world-local or a reusable-template revision

### 5. Verify

Run `card-audit <card_id>` when the reusable template changed, then `diagnose <world>` to confirm the active world remains coherent.

### Pitfalls

- **PITFALL — editing the wrong scope**: changing a reusable library card does not rewrite existing worlds; changing a world's `runtime_cast` does not rewrite the library. Choose the scope deliberately.
- **PITFALL — using `patch` on JSON**: Multi-line string fields (description, system_prompt) contain literal newlines. `patch` replacement text cannot reliably match these. Use `execute_code` with Python's `json` module instead.
- **PITFALL — forgetting the worldbook when renaming**: Old character names can linger in worldbook entry keys and content. After renaming a card, always run `lore-audit` to check.


## Removing Cast from a World

The tavern CLI has no `detach-card` or `remove-card` command. To remove a character from a world's active cast while preserving the standalone card file:

1. Use the Liveware `detach_card` event with `production_id` and `card_id`.
2. Verify the role disappeared from `runtime_cast.characters` and its relationship edges were removed.
3. Do NOT delete the standalone card file in `/opt/data/tavern-state/cards/<card_id>.json` — the user may want it for future worlds.

`add-original` imports into the reusable library and does not create a world
unless `--new-world` is explicit. Never delete production or worldbook files as
normal cleanup.

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

For a new complete world, place the Persona in the `build-world` manifest. For
an existing world, use the console editor or the supported Liveware event. Do
not write the production JSON directly.

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
