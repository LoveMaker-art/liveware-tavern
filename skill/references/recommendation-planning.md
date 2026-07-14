# Recommendation and World Planning

Use this reference when the user asks the story curator to recommend a world, find roles, or turn a loose idea into a playable tavern setup. Keep this as backend skill behavior; do not add extra front-end entry points.

## Principle

The story curator should feel like a story lead, not a form wizard. The user gives a wish, mood, fandom, role, or one sentence. The skill layer reads profile and structure, then the story curator replies with a small, coherent proposal.

## Recommendation Workflow

1. Run `recommend ["want"]` first. It is read-only and combines story profile, local worlds, and local character library.
2. Pick one main direction and at most one backup. Do not offer a large menu unless the user explicitly asks.
3. Explain the recommendation through story feel: relationship tension, world pressure, first scene hook, and why it fits the user.
4. If the user chooses a direction, use existing commands to create or assemble it: `new-world`, `search`, `add`, `attach-card`, `add-lore`, and console persona setup.

## World Planning Workflow

Use `plan-world "idea"` after recommendation when the user chooses to create or restructure a world from a loose concept. Its output should guide placement:

- World: container name and overall premise.
- Persona: the user's own role belongs in console `我的角色`, not in worldbook as `{{user}}`.
- Cast: character cards contain character voice, desire, boundaries, relationship stance, and participation style.
- Lore: places, factions, rules, secrets, objects, history, and power systems become worldbook/lore entries.
- Story state: events that happen during play are maintained by runtime compression, not prewritten as static lore.

## Good Output Shape

A recommendation should usually contain:

- one-sentence world direction;
- suggested cast shape, not a long roster;
- first scene hook;
- what needs to be created/imported next.

Example tone:

```text
我会给你开一个偏暗线的学院世界：表面是日常入学，底下有组织、误会和身份遮掩。

登场先放三个人就够：一个牵引你入局的人，一个能解释规则的人，一个制造变数的人。你的身份放在「我的角色」里，这样故事会把你当作稳定角色，而不是临时旁观者。

第一场从夜里的档案室开始，有人已经替你签过到。
```

## Avoid

- Do not ask the user to fill long setup forms.
- Do not turn every capability into a visible front-end button.
- Do not put the user's identity into lore as `{{user}}` when it should be persona.
- Do not create a large worldbook before the first scene has a clear entry point.
- Do not recommend many unrelated cards just because search returns many results.
## Setup World

Use `setup-world <idea>` as the practical bridge from recommendation to creation. By default it only prints the world plan. `--apply --confirm` may create a blank world, attach explicitly named local cards, and write explicit lore items. Do not infer destructive or hidden changes.
