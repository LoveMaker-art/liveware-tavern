# Worldbook Workflow

Use this reference for worldbook authoring, import, trigger design, audit, and
repair.

## What Belongs Here

Shared locations, organizations, rules, history, public events, objects, and
secrets belong in worldbook. Character identity belongs in cards; the user's
playable identity belongs in Persona; events established during play belong in
story state.

## Entry Fields

- `content`: one coherent, stable fact group.
- `keys`: specific primary triggers.
- `secondary_keys` with `selective=true`: require additional context.
- `constant=true`: inject every turn; reserve for short global rules.
- `recursive=true`: allow injected lore to trigger more lore; use rarely.
- `exclusion_keys`: suppress in conflicting contexts.
- `priority`: resolve limited injection budget.
- `position`: `before_char` for broad setting, `after_char` for nearby context.
- `enabled=false`: retain without injecting.

## Trigger Design

Prefer names and distinctive phrases such as a full place, faction, artifact,
or event name. Avoid one-character pronouns and generic terms such as school,
city, mission, secret, street, or evening. If a character name is too broad,
use selective secondary keys.

Secrets must describe who knows them. Do not write privileged knowledge as a
public fact. Keep constant entries short and few.

## Workflow

```sh
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
CLI="$HERMES_HOME/skills/creative/tavern/scripts/tavern_cli.py"
python3 "$CLI" add-worldbook <worldbook-json>
python3 "$CLI" add-lore <world> "setting" --json
python3 "$CLI" lore-audit <world> --json
python3 "$CLI" lore-fix <world> --plan
```

`lore-audit` is read-only. Use a repair plan before changing broad triggers,
recursion, empty entries, duplicated facts, or `{{user}}` residue. Mechanical
repair still requires explicit confirmation.

## Verification

Confirm the intended world references the expected worldbook, entry modes and
triggers are correct, no character profile was stored as shared lore, and no
unrelated world or reusable library template changed.
