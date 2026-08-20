# State Repair

Use state repair only after diagnosis identifies the wrong owner.

## Choose The Target

Use `story-fix` for an incorrect plot fact, scene, timeline event, object holder,
secret, or open thread.

Use `cast-fix` for an incorrect world-local persistent character/user status,
effective profile, identity field, or relationship.

Use another workflow for reusable cards, worldbook triggers, user taste, model
configuration, runtime code, or visible story-message editing.

## Required Flow

```sh
REPAIR=/opt/data/skills/creative/tavern-continuity/scripts/tavern_repair.py
python3 "$REPAIR" story-fix <world> "correction" --plan
python3 "$REPAIR" cast-fix <world> "correction" --plan
```

1. Generate one plan for the correct owner.
2. Show changed fields and evidence.
3. Ask when confidence is low or the request is ambiguous.
4. Apply only after explicit confirmation with `--apply --confirm`.
5. Run `diagnose --json` and `recall --json` again.

Never change `origin_profile`, reusable cards, story messages, unrelated roles,
or other worlds. Do not convert an uncertain interpretation into a durable fact.
