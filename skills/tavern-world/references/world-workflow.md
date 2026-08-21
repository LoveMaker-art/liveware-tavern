# World Workflow

Use this reference for recommendations, complete world construction, expansion,
or rebuilding an existing world.

## Ownership

- Character card: one character's durable identity, voice, motives, abilities,
  limits, and character-local history.
- Worldbook: shared places, factions, rules, history, objects, and secrets.
- Persona: who the user is inside this world.
- Opening: the first playable scene and immediate response hook.
- Live story state: events and relationships established during play.
- Runtime protocol: language, punctuation, dialogue markup, and output length.

Store each fact once. Never use lore or character prompts to compensate for a
runtime-format problem.

## Plan

1. Run `list --json`; use `recommend` or `plan-world` when the request is loose.
2. Offer one coherent direction and at most one alternative.
3. Confirm the world premise, Persona, cast, core lore, and opening.
4. Import external cards through the preparation gate before building.
5. Assemble one manifest and preview it without `--apply`.

## Manifest

```json
{
  "schema": "tavern-world/v1",
  "request_id": "stable-approved-plan-id",
  "world": {
    "name": "World name",
    "opening": "Playable opening"
  },
  "characters": [
    {"library": "Existing library card"},
    {"card_id": "prepared_card_id"},
    {"card": {"spec": "chara_card_v2", "spec_version": "2.0", "data": {}}}
  ],
  "worldbook_entries": [
    {"name": "Core rule", "content": "Stable fact", "constant": true, "keys": []},
    {"name": "Context lore", "content": "Stable fact", "constant": false, "keys": ["specific trigger"], "priority": 100}
  ],
  "persona": {
    "profile": {
      "identity": {"name": "User role", "aliases": [], "age": "", "occupation": "", "affiliations": [], "story_role": ""},
      "description": ""
    }
  }
}
```

External artifacts may not appear directly in the manifest. Use their prepared
library `card_id`. Inline `card` is only for material authored for this request.

Preview and apply the same file:

```sh
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
CLI="$HERMES_HOME/skills/creative/tavern/scripts/tavern_cli.py"
python3 "$CLI" build-world /tmp/world.json
python3 "$CLI" build-world /tmp/world.json --apply --confirm --request-id <stable-id> --json
python3 "$CLI" verify-world <world> --json
```

Reuse the same request ID only for the same approved manifest. Success requires
`verification.ok: true`.

## Existing Worlds

- Expand: inspect, import reusable material, attach only approved cards, add
  world-local lore, preserve the current story and opening, then verify.
- Rebuild: create one new manifest from the intended reusable material. Do not
  clone private runtime history or evolving cast state unless explicitly asked.
- Repair: use `diagnose` first and change the owning layer only. Do not create a
  replacement world as a repair shortcut.

Never directly edit production JSON.
