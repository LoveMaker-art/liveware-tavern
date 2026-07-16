# Lore Audit

Use this reference when the user asks about worldbook design, lore trigger behavior, keyword pollution, character/user identity leakage, or why unrelated settings are being injected.

Primary command:

```sh
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py lore-audit "<world name or id>" [--verbose]
```

Read-only rule:

- `lore-audit` only inspects. Do not rewrite worldbooks unless the user explicitly asks for a fix.

What to look for:

- `constant=true`: suitable only for core facts that should always be present.
- `recursive=true`: powerful but easy to over-inject; use only when a lore entry should intentionally trigger more lore.
- Broad keys: short or generic keys such as `教团`, `商会`, `学校`, `任务`, `秘密` can cause unrelated entries to fire.
- **Character names as triggers**: using a character name as a trigger key causes the entry to fire whenever that character is mentioned — in multi-character worlds, this means nearly every turn. Replace with specific scene signals or relationship states.
- **Common setting words**: words like a city name, `学校`, `学生`, or `老师` can appear in nearly every turn. These make entries effectively constant. Replace them with specific locations (`北岸栈桥`, `旧港仓库`) or relationship signals (`临时同盟`, `共同调查`).
- `selective=true` with `secondary_keys`: useful when a character name alone is too broad and needs a second condition.
- `{{user}}` residue: usually means user identity belongs in persona or a specific lore entry, not generic imported text.
- Empty/very long content: empty entries do nothing; very long entries can crowd out character/story context.

Recommended structure:

- Core world premise: small constant entries.
- Factions/places/systems: keyword-triggered entries.
- Character-specific facts: role card or card worldbook, not global lore, unless many characters need to know it.
- User identity: persona first; lore only for public reputation, power ranking, or information known by other characters.
- Secrets: include who knows the secret and who does not.

How to report:

- List the risky entries by name.
- Explain why a key is too broad or why an entry should be constant/selective.
- Suggest the smallest safe change.
- Do not edit until the user approves.
