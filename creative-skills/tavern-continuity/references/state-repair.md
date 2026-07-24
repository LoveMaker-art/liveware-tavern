# Tavern State Repair

Use this reference when Ruotang needs to convert a user correction into a safe state repair.

## Choose the right repair target

Use `story-fix` for:

- object custody: who has a key, weapon, document, artifact, or clue;
- current scene: location, time, ongoing action, immediate situation;
- confirmed facts: established events, known outcomes, public discoveries;
- open threads: unresolved questions, active tasks, pending promises;
- secrets: hidden facts and who knows or does not know them;
- timeline: durable event sequence;
- style_notes only when the existing story_state style note is wrong.

Use `cast-fix` for:

- a character's durable status, injury, disguise, occupation, location-like persistent state, or relationship posture;
- user profile or user_status inside the world;
- relationship graph changes among characters or between user and characters;
- dynamic profile changes that should persist in this world only.

Use another skill instead:

- worldbook trigger/key pollution → `tavern-world`;
- reusable card identity/personality/source template → `tavern-world`;
- user acting taste or durable preference → `tavern-story-profile`;
- output format or language protocol → runtime engineering / `tavern-continuity`;
- model timeout/configuration → `tavern-ops`.

## Required workflow

1. Always run `--plan` first.
2. Treat low-confidence or ambiguous plans as a question to the user, not as permission to write.
3. Apply only after the user explicitly confirms.
4. After applying, verify with:

       python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py diagnose "<world>"

## Safety rules

- Never overwrite production story history.
- Never edit `origin_profile`; it is the immutable imported baseline.
- Never copy world-local evolved profiles back into reusable library cards.
- Never repair by adding hidden prompt rules to notes, lore, cards, or memory.
- Prefer the smallest change that makes the current state match the user's correction.
- If the user is correcting a future preference rather than a past/current fact, use `note` or `learn` instead of state repair.

## Examples

Correction: “钥匙现在在我手里，不在贝塔手里。”

- Use `story-fix`.
- Likely update `objects` and maybe `facts`.
- Do not change Beta's character profile unless her long-term status changed.

Correction: “阿尔法的伤已经恢复了。”

- Use `cast-fix`.
- Update `persistent_status.physical_condition` for Alpha.
- Add a story_state fact only if the recovery itself is an established plot event that future scenes need.

Correction: “贝塔不该知道那个秘密。”

- Use `story-fix` for `secrets.known_by` / knowledge boundary.
- Use `cast-fix` only if her relationship or durable status also changed.
