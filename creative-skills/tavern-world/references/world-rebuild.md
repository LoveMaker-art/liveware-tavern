# World Rebuild / Clone Workflow

When the user wants to rebuild a world from scratch (new name, same cards/worldbook/persona, clean story history):

## Sequence

1. `new-world --name "..."` → get new production ID
2. `attach-card <world> <card_id>` × N → attach all character cards
3. `add-lore <world> "..."` × N → add lore entries (natural language, let auto-generation handle structure)
4. `lore-audit <world>` → inspect auto-generated entries
5. Fix auto-generated issues (see `add-lore` pitfall in SKILL.md):
   - Remove `selective` when `constant=true` (contradiction)
   - Turn off `constant` for character-description entries
   - Remove duplicate entries (similar content from multiple `add-lore` calls)
   - Narrow over-broad keys (`学校`, `老师`)
   - `lore-fix --apply --confirm` only handles narrow keys and recursive scanning; use `json.load`/`json.dump` for the rest
6. `set_persona` via API, then write `persona.json` into the production file's `persona` field
7. `diagnose <world>` → final verification

## Reading from an existing world

When cloning from an existing production:
- Read `productions/<prod_id>.json` for `card_ids`, `worldbook_ids`, `persona`
- Read `worldbooks/<wb_id>.json` for lore entry content
- Read `persona.json` for user persona
- Recreate entries via `add-lore` (don't copy worldbook JSON directly — let auto-generation handle trigger keys fresh, then audit)

## Pitfall: persona field

After `set_persona` API call, the production file's `persona` field is still `{}`. Must manually copy from `persona.json`:

```python
with open("persona.json") as f: persona = json.load(f)
prod["persona"] = {"name": persona["name"], "description": persona["description"]}
```
