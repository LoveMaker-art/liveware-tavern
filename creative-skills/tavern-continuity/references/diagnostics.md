# Continuity Diagnostics

Start with evidence. Do not modify state during diagnosis.

```sh
CLI=/opt/data/skills/creative/tavern/scripts/tavern_cli.py
python3 "$CLI" doctor --json
python3 "$CLI" diagnose <world> --json
python3 "$CLI" recall <world> --last 12 --json
python3 "$CLI" lore-audit <world> --json
```

## Ownership Map

- Story messages: confirmed visible conversation history.
- `story_state`: compressed plot facts, timeline, open threads, objects, secrets,
  and current scene checkpoint.
- `runtime_cast`: world-local effective profiles, persistent status, and relationships.
- Library cards: reusable starting templates.
- Worldbook: shared setting and knowledge boundaries.
- Runtime protocol: language, dialogue markup, punctuation, and output length.
- Model/transport: latency, timeout, HTTP errors, and empty upstream responses.

## Diagnose By Symptom

- Empty or failed reply: inspect health and generation logs before changing prompts.
- Slow reply: separate prompt assembly, upstream latency, retries, and background
  checkpoint work. Do not assume context size without measurements.
- Wrong identity or role: compare Persona, library card, runtime cast, recent
  messages, and relationship state.
- Forgotten event: check whether it is in visible history or the story ledger.
- Lore leak: audit constant, recursive, broad, duplicated, or public-secret entries.
- Format drift: inspect runtime protocol and raw model output. Do not add duplicate
  rules to cards, worldbooks, notes, or history.
- Post-checkpoint drift: compare the latest completed checkpoint, story ledger,
  and effective cast revision.

## Runtime Invariants

- Checkpoints are background state maintenance; generation must remain one
  foreground model call.
- A checkpoint may replace old prompt history only after its ledger update succeeds.
- Cast updates use the same completed story batch and must not derive durable
  identity from a summary alone.
- `origin_profile` is immutable. `profile` is the only effective evolving profile.
- Multi-character participation is chosen in the single narration generation;
  no separate turn-planning model call is required.

Report concrete findings, cause, impact, and the narrowest supported correction.
