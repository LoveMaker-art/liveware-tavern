# Event-Driven World Update

Use this reference when the user wants to add a major event or scenario change to an existing world — a new arc, a plot twist, a "return from X" event, or any shift that cascades through worldbook, character cards, and production opening.

## Core Principle

A major event is not just a new lore entry. It cascades:

```
Event lore → Worldbook updates → Character card updates → Production opening rewrite
```

Skipping any layer leaves the world inconsistent: the lore says one thing, but the cards and opening say another.

## Full Workflow

### Step 1 — Understand the event first

Before writing anything, research the event if it's from source material (light novel, anime, game). Don't guess plot details — the user will notice.

### Step 2 — Add event lore via CLI

```sh
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py add-lore "<world>" "事件：<name> · constant=true · <full event description>"
```

The CLI auto-generates trigger keys from the content. These are often too broad — fix them in Step 4.

### Step 3 — Audit current state

```sh
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py lore-audit "<world>"
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py diagnose "<world>"
```

Check: trigger key overlaps, constant entry count, card descriptions, persona state.

### Step 4 — Fix worldbook trigger keys

The CLI's auto-generated keys often include broad terms that overlap with existing entries (e.g., "教团" appearing in both the event entry and the faction entry). Edit the worldbook JSON directly:

```python
import json
wb_path = '/opt/data/tavern-state/worldbooks/wb_prod_<world_id>.json'
with open(wb_path) as f:
    wb = json.load(f)
for entry in wb['entries']:
    if entry['id'] == '<event_entry_id>':
        entry['keys'] = ['specific', 'narrow', 'keys', 'only']
        entry['priority'] = 200  # Event entries should be highest priority
        entry['recursive'] = False
```

### Step 5 — Add supporting lore entries

New concepts introduced by the event (phenomena, locations, factions, intelligence reports) need their own entries. Add them directly to the worldbook JSON:

```python
wb['entries'].append({
    "id": "lore_<timestamp_hex>",
    "name": "分类：条目名",
    "keys": ["specific", "trigger", "words"],
    "content": "<full Chinese content>",
    "enabled": True,
    "constant": False,
    "selective": False,
    "priority": 140,
    "position": "after_char",
    "category": "设定",
    "source": "user_lore",
    "recursive": False
})
```

### Step 6 — Update character cards

Cards directly affected by the event need description, system_prompt, and post_history_instructions updates. Cards tangentially affected get a one-line addition.

**Directly affected** (e.g., character who went to Earth):
- Rewrite `description` to include the new experience
- Update `system_prompt` to reflect new knowledge/behavior
- Update `post_history_instructions`

**Tangentially affected** (e.g., other Seven Shadows):
- Add one line to `description` using `str.replace()` on a stable anchor string

Card files: `/opt/data/tavern-state/cards/card_<name>.json`

### Step 7 — Production opening (CAUTION)

**⚠️ Only rewrite the production opening for a BRAND-NEW world or when the user explicitly asks.**

If the user has an ongoing story with existing history (checked via `recall`), do NOT overwrite `story[0]`. The user will continue from where they left off — the event lore and card updates alone are sufficient to shift the scene. Overwriting a live production's opening erases the user's play context.

When the user DOES ask for a new opening:

```python
prod_path = '/opt/data/tavern-state/productions/<prod_id>.json'
with open(prod_path) as f:
    prod = json.load(f)
prod['story'][0]['text'] = new_opening
prod['story'][0]['alts'] = [new_opening]
```

The new opening should:
- Establish the event's immediate situation (time, place, mood)
- Position each key character in the scene
- End with a hook that invites the user to act

### Step 8 — Verify

```sh
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py diagnose "<world>"
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py lore-audit "<world>"
```

## Pitfalls

### `add-original --name` creates a NEW world, not attaches to existing

When adding an original card to an EXISTING world, do NOT use the `--name` flag:
```sh
# WRONG — creates a duplicate world
python3 .../tavern_cli.py add-original card.json --name "影之实力者"

# RIGHT — imports card, then attaches to existing world
python3 .../tavern_cli.py add-original card.json
python3 .../tavern_cli.py attach-card "影之实力者" "card_<id>"
```
If you accidentally create a duplicate world, delete the extra production JSON and verify with `list`.

### Scenario completeness: check for missing characters

When the user adds an event that implies a new character (e.g., "someone is coming through the rift"), proactively ask whether they want to add that character. Don't wait for the user to point out the gap. Run `list` to check the current cast, then suggest the missing role.

### CLI auto-generated trigger keys are too broad

`add-lore` auto-extracts trigger keys from the content. Terms like "教团", "七影", "商会" will overlap with existing entries. Always run `lore-audit` after `add-lore` and fix the event entry's keys to be narrow and specific.

### Hex ID generation fails with large values

When generating lore entry IDs like `lore_<hex>`, use `int(time.time())` for the hex source, not existing entry IDs. Existing IDs from the CLI (e.g., `lore_873bf9f4`) won't parse as int in Python.

### Script failures roll back partially

When using `execute_code` to make multiple file changes, if the script fails mid-execution, earlier changes within the same script are NOT saved. Split risky operations into separate scripts, or use try/except to ensure critical writes complete.

### Production file caches story[0] separately

The `add` command stores the card's `first_mes` into the production file. Updating the card file's `first_mes` does NOT update the production. Always edit the production file directly when changing the opening scene.

## Content Guidelines for Event Backgrounds

A good event lore entry should be:
- **Constant**: always injected as the core premise
- **Highest priority**: 200 so it's never crowded out
- **Narrow keys**: 5-7 specific trigger words, not broad terms
- **Actionable**: establishes immediate tension, not just backstory

A good event opening should:
- Open in a concrete place and moment
- Position characters by their current task
- Show sensory details (smell, sound, light) before exposition
- End with a hook the user can answer
- Not decide the user's actions or feelings