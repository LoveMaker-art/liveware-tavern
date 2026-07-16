# Worldbook Authoring

Use this reference when designing, importing, auditing, or repairing lore/worldbook entries for the Tavern.

## Purpose

A worldbook answers: **what facts should the model know only when relevant?**

It is not a second character card and not a transcript. It is a selectively injected knowledge base for places, factions, systems, secrets, objects, public facts, and background rules.

## Entry Types

- **Core premise**: small constant entries that define the world and cannot be omitted.
- **Faction/organization**: triggered by faction names, members, operations, or conflicts.
- **Place/location**: triggered by place names and scene movement.
- **System/rule**: magic, school, law, technology, social hierarchy, combat rules.
- **Secret/information boundary**: who knows, who suspects, who must not know.
- **Object/asset**: important item, document, weapon, artifact, uniform, token, wound, debt.
- **Relationship/public reputation**: facts that many characters in the world can know.

## Fields And Meaning

- `keys`: primary trigger words.
- `secondary_keys` + `selective=true`: require a second condition before injecting.
- `constant=true`: always inject. Use sparingly.
- `recursive=true`: injected content may trigger more entries. Use rarely and intentionally.
- `exclusion_keys`: suppress when certain words appear.
- `priority`: higher entries fit first when budget is limited.
- `position`: `before_char` for broad setting before role material; `after_char` for nearby context after character material.
- `enabled=false`: keep but disable.

## Trigger Design

Good keys are specific:

- `雾港旧钟楼`
- `潮汐档案局`
- `白鹭商会密函`
- `月蚀通行证`
- `旧港七号仓`

Risky broad keys:

- `学校`
- `商会`
- `王国`
- `任务`
- `秘密`
- `教团`
- `城市` / `雨天` / `咖啡馆` / `街道` / `傍晚` — common setting words that fire on almost every turn
- `深圳` / `东京` / `伦敦` — city/country names that appear naturally in setting description
- Character names — using a character name as a trigger key causes the entry to fire whenever that character is mentioned, which in a multi-character world means nearly every turn
- one-character pronouns or common particles

**The core principle**: trigger words should be **specific scene signals, relationship states, or event markers**, not character names or generic setting words. When a worldbook entry fires on every turn, it loses its purpose as selective context injection and becomes dead weight.

**Fix pattern**: replace character names and common words with concrete triggers:

| Before (broken) | After (fixed) |
|---|---|
| character names | `旧钟楼密道, 白鹭徽章, 月蚀通行证` (scene signals) |
| `城市, 雨天, 咖啡馆, 往事, 熟人` (generic) | `临江路, 晚潮咖啡馆, 旧相册` (specific places and story objects) |
| a city or country name | `北岸栈桥, 海关旧仓, 灯塔值班室` (specific locations) |

When a character name is too broad, use selective triggers:

```json
{
  "keys": ["白鹭商会"],
  "secondary_keys": ["密函", "账本", "旧港", "交易", "会长"],
  "selective": true
}
```

This prevents any mention of a character from dragging in unrelated institutional lore.

## Constant Entry Rules

Use `constant=true` only for:

- world identity that must always be known;
- central cast relationship that affects every scene;
- safety/continuity facts that should never disappear;

Do not make entries constant just because they are important. Important but situational lore should have precise keys and priority.

## Secret And Knowledge Boundary Rules

Secrets should include who knows them:

```text
秘密：馆长知道航海图缺失的一页由谁取走；巡夜人和其他调查者尚不知情。
```

Avoid writing secrets as universal truth if characters should not act on that knowledge.

## User Identity Rules

- User's playable identity belongs in persona.
- Public reputation can be lore.
- Power ranking can be lore if other characters should reason from it.
- Do not leave generic `{{user}}` in imported lore without deciding what it means.

## Split/Merge Rules

Split entries when:

- the triggers differ;
- one part is constant and another is situational;
- a secret has different knowledge boundaries;
- the content is longer than a screenful and only part is usually relevant.

Merge entries when:

- they share the same keys and are always needed together;
- duplicate facts compete;
- a broad entry repeats card content without adding world knowledge.

## Audit Checklist

Run:

```sh
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py lore-audit "<world>"
```

Then check:

- Are constants truly always needed?
- Are broad keys causing accidental injection?
- Are duplicate keys intentional?
- Is recursive disabled unless deliberately needed?
- Are secrets labeled with who knows them?
- Is user identity in persona rather than lore?
- Are character personalities in cards rather than global lore?
- Are long entries split into smaller triggerable facts?

## Lore Fix Planning

Use `lore-fix <world> --plan` after `lore-audit` when the user asks how to repair a worldbook. It is read-only and should be used before editing data.
The repair plan prioritizes:

- high severity: empty content, missing triggers, entries that cannot enter context;
- medium severity: broad trigger keys, `{{user}}` leakage, recursive pollution, overlong constant entries;
- low severity: duplicate keys and long entries that should be split.

**PITFALL — `lore-fix --plan` blind spots**: the CLI's automated analysis only flags trigger key *duplication* across entries. It does NOT catch:

- character names used as trigger keys — these fire on every mention of that character;
- common setting words (for example a city name, `学校`, `学生`) — these appear in nearly every turn;
- the combination of both making a worldbook effectively constant injection with no selectivity.

When `lore-fix --plan` returns only `[低]` severity items but the user reports that lore is "always firing" or "feels like it's injected every turn", manually inspect the trigger keys for character names and common setting words. The fix is the same pattern: replace with specific scene signals, relationship states, or event markers.

Do not auto-apply fixes unless the user explicitly asks. Worldbook fixes can change story behavior, so propose the plan first, then edit the smallest necessary entries.
## Conservative Apply

`lore-fix <world> --apply --confirm` may be used only for conservative mechanical fixes: disable recursive scanning and replace over-broad trigger keys with narrower candidates. It must not rewrite lore content or change story facts. Run `lore-audit` again after applying.
