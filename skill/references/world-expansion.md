# World Expansion Workflow

When the user wants to expand an existing world with new characters, change the setting (location, era, school type), or restructure the core card — follow this coordinated sequence to avoid leaving stale references or orphan productions.

## Sequence

1. **Audit first**: `card-audit` the core card, `lore-audit` the world, `diagnose` the world. Know what you're touching before you touch it.

2. **Rewrite the core card**: Update `description`, `personality`, `first_mes`, `system_prompt`, `mes_example`, `post_history_instructions`, and `tags` in one pass. Key changes in a setting rewrite:
   - Nationality and location references
   - Age (if school type changes)
   - Physical details (height, appearance)
   - Subject taught (if school type changes)
   - Scene descriptions in `first_mes` (location-appropriate)
   - Character relationships (e.g., new fiancé)
   - Tags (remove stale ones, add relevant ones)

3. **Update worldbook entries**: Change keys, secondary_keys, and content for all existing entries to reflect the new setting. Watch for stale old names in `secondary_keys` — they linger and trigger unexpectedly.

4. **Update persona**: Adjust school type, age, location, and add any new physical details (e.g., height). Sync to the production file's embedded `persona` field.

5. **Create new original cards**: Write SillyTavern V2 JSON for each new character, save as temp files, import with `add-original`.

6. **Attach to target world**: Use `attach-card <world> <card_id>` for each new card.

7. **Clean orphan productions**: `add-original` auto-creates standalone productions and worldbooks. Delete them:
   - `tavern-state/productions/prod_<auto_id>.json`
   - `tavern-state/worldbooks/wb_prod_prod_<auto_id>.json`

8. **Add lore for new characters**: Use `add-lore <world> "..."` for each new character and any new locations/relationships.

9. **Final audit**: Run `diagnose` and `card-audit` on new cards to verify.

## Height & Physical Details

When the user specifies exact heights or physical traits, these go into:
- **Persona** (`description`): the user's own height/build
- **Core card** (`description` → `<外貌>`): the main character's height/build
- **New cards** (`description` → `<外貌>`): each supporting character's height/build
- Do NOT put heights in worldbook — they are character attributes, not setting facts

## Common Pitfalls

- **`add-original` orphans**: Every `add-original` call creates a standalone world. Always clean up after attaching.
- **`attach-card` syntax**: It's `attach-card <world> <card>`, NOT `attach-card <card> --world <world>`.
- **Stale secondary_keys**: When renaming a character, grep the worldbook JSON for old names. `secondary_keys` are the most common hiding place.
- **Persona sync gap**: `set_persona` writes to `persona.json` but the server reads from the production file. Always sync manually.
