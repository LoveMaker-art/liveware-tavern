# Character Card Workflow

Use this reference for external import, original authoring, localization, and
reusable card repair.

## Accepted Sources

- SillyTavern V1, V2, or V3 JSON.
- PNG/APNG containing recognized character-card metadata.
- V3 CHARX archives.
- Public HTTPS artifact or Chub full path with visible provenance.

An ordinary image, HTML detail page, malformed archive, or inaccessible link is
not a card. Imported scripts, regex executors, MVU/TavernHelper blocks, and
executable assets are unsupported and removed during normalization.

## Mandatory External Import

```sh
CLI=/opt/data/skills/creative/tavern/scripts/tavern_cli.py
python3 "$CLI" inspect-card <artifact> --json
python3 "$CLI" prepare-card <artifact> --output /tmp/card-plan.json --json
python3 "$CLI" apply-card-plan /tmp/card-plan.json --confirm
python3 "$CLI" card-audit <stored-card>
```

Inspection and preparation are read-only. Apply only the exact reviewed plan.
The main character profile must be non-empty. Named supporting people become
candidate reusable cards; shared setting becomes worldbook entries; uncertain
or temporary scene data stays unresolved. Supporting cards do not join a world
until explicitly attached.

## Canonical Content

Keep evidence-backed fields only:

- `name`, aliases, age/life stage, occupation, affiliations, story role;
- durable appearance and physical traits when the source states them;
- personality, values, motives, fears, habits, and contradictions;
- speech rhythm, address terms, and stable verbal habits;
- skills, powers, and limitations;
- durable background and named relationships;
- scenario, opening, and short dialogue examples;
- creator, source, version, tags, and non-executable metadata.

Unknown fields may be empty. Do not infer age, body details, powers, identity,
or relationships from stereotypes. Do not turn a specific user's preferences
into universal card requirements.

## Ownership And Mapping

- Character-specific facts stay in the card.
- Shared places, factions, rules, and history go to worldbook.
- Imported `{{user}}` identity must be classified: playable identity to Persona,
  public fact to worldbook, relationship default to the world's relationship state.
- Current injuries, locations, emotions, possessions, and story events belong to
  live story state, not the reusable card.
- Global output rules never belong in `system_prompt` or
  `post_history_instructions`.

## Original Cards

Use `add-original` only for material explicitly authored for this request. A
good card has a stable identity, distinct voice, motives and limits, a playable
scenario, and an opening with something the user can answer. Avoid encyclopedia
prose and duplicated facts.

## Localization

Localize only when requested. Translate all user-visible card fields and
associated worldbook content consistently while preserving names, canon facts,
placeholders, creator attribution, source, and field structure. Do not add a
language-enforcement system prompt; interface language and output language are
runtime concerns.

After storage, audit the card and verify its world-local runtime copy separately.
Never write card files directly.
