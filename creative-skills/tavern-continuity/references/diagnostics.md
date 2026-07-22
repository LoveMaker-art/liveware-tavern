# Tavern Diagnostics

Use this reference when the user says a world feels wrong, output is broken, a model reply is empty, characters are confused, or the user asks why something happened.

Primary command:

```sh
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py diagnose "<world name or id>"
```

Read-only rule:

- `diagnose` must not modify cards, worlds, story, persona, or worldbooks.
- It is the first step before proposing fixes when the cause is unclear.

What diagnosis checks:

- Cast presence and duplicate cards.
- Empty `char` messages that can poison subsequent generations.
- `{{user}}` residue in world, cards, or worldbooks.
- Missing or weak user persona.
- Missing worldbooks for long-running worlds.
- Broad or duplicate lore trigger keys.
- Recent raw actor replies and the runtime output protocol selected for them.

How to answer after diagnosis:

1. State the concrete findings, not a vague theory.
2. Separate cause from symptom.
3. Say whether a fix is read-only, safe edit, or risky edit.
4. Ask before destructive cleanup or large state rewrites.

Follow-up commands:

```sh
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py recall "<world>" --last 12
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py lore-audit "<world>"
python3 /opt/data/skills/creative/tavern-continuity/scripts/tavern_repair.py story-fix "<world>" "<what is wrong>" --plan
python3 /opt/data/skills/creative/tavern-continuity/scripts/tavern_repair.py cast-fix "<world>" "<what is wrong>" --plan
```

Common interpretations:

- Empty actor replies: clean empty `char` turns before continuing.
- Role confusion: inspect persona and `{{user}}` residue.
- Lore pollution: run `lore-audit`; broad keys or recursive entries are common causes.
- Format drift: inspect the effective runtime protocol, selected language, raw provider response, retries, and latest history. Correct the runtime-owned rule rather than adding prompt fragments to story data.
- Wrong plot ledger: use `story-fix --plan` from this skill to propose the smallest story_state change; apply only after the user confirms.
- Wrong character/user status: use `cast-fix --plan` from this skill to propose the smallest runtime_cast change; apply only after the user confirms.
- **Model timeout with zero output** (no error, no content, just timeout): the model API returns normally on a direct `curl`/`test` call but the tavern generation pipeline times out. This typically means the full prompt is too large — too many cards + worldbook entries + story history. Diagnose with: (1) `recall <world> --last 5` to check history length, (2) count cast members and worldbook entries, (3) test model directly with `model test`. Fix by pruning empty `char` entries, reducing cast if safe, or switching to a model with larger context. Server restart alone will not fix this.
