# Complete World Workflow

Use one manifest as the source of truth for a complete Tavern world. Preview the
manifest first; apply the same file only after confirmation.

## Manifest Shape

```json
{
  "schema": "tavern-world/v1",
  "request_id": "stable-id-for-this-approved-plan",
  "world": {
    "name": "World name",
    "opening": "Opening scene text"
  },
  "characters": [
    {"library": "Existing card name"},
    {"card_id": "card_existing_id"},
    {"json_file": "/absolute/path/to/card.json"},
    {"png_file": "/absolute/path/to/card.png"},
    {"full_path": "creator/chub-card"},
    {"card": {"spec": "chara_card_v2", "spec_version": "2.0", "data": {}}}
  ],
  "worldbook_entries": [
    {
      "name": "Entry name",
      "content": "Stable world fact",
      "constant": true,
      "keys": []
    },
    {
      "name": "Triggered entry",
      "content": "Contextual world fact",
      "constant": false,
      "keys": ["specific trigger"],
      "secondary_keys": [],
      "exclusion_keys": [],
      "priority": 100
    }
  ],
  "persona": {
    "profile": {
      "identity": {
        "name": "User character",
        "aliases": [],
        "age": "",
        "occupation": "",
        "affiliations": [],
        "story_role": ""
      },
      "description": ""
    }
  }
}
```

Each character entry must use exactly one source: `library`, `card_id`,
`json_file`, `png_file`, `full_path`, or inline `card`.

## Execution

Preview:

    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py build-world /tmp/world.json

Apply:

    python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py build-world /tmp/world.json --apply --confirm --request-id <stable-id> --json

The server imports cards, creates one world, attaches cast, writes lore, applies
the persona, writes the opening, activates the world, and verifies the result
under one lock. If a step fails, only artifacts created by this request are
removed and the previous active world is restored.

Reusing the same `request_id` with the same manifest is idempotent. Reusing it
with different content is rejected.

## Completion

Success requires `verification.ok: true`. Return the world name and the bare
Tavern URL. Never create a second world to repair a failed build.
