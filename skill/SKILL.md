---
name: tavern
description: "Use when the user wants the Tavern: story worlds, roleplay scenes, SillyTavern character cards, world lore, liveware tavern scenes, story memory/reflection, or tavern model setup."
version: 1.19.2
author: ClawChat Tavern
license: AGPL-3.0-only
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [roleplay, story-world, character-card, world-lore, chub, sillytavern, tavern, 酒馆, 世界, 角色扮演]
    category: creative
---

# Tavern

## Purpose

This skill is the operating layer for the Tavern. Treat the product model as:

- **World**: the main container. A world contains cast, current-world lore, story history, model settings, persona, and local direction.
- **Cast**: reusable character cards joined to a world as possible participants.
- **Library cards**: reusable character templates returned by `/api/library/cards`; adding/removing them from a world does not delete the library card.
- **Library worldbooks**: reusable world templates returned by `/api/library/worldbooks`; they are used to start or seed worlds.
- **Current-world lore**: production-owned canonical worldbook files returned by `/api/production/worldbooks?production_id=...`. A production stores only `worldbook_ids`; the runtime, frontend, model, and CLI all load those files directly.
- **Story**: the exact running scene generated from the current world, cast, lore, persona, story state, and user turns.

The story curator is the user's story lead in ClawChat. The story curator helps choose, organize, and open worlds; the story curator is not automatically a character inside every running story.

The story curator's main soul lives in `/opt/data/SOUL.md`. Runtime service code lives in `/opt/data/apps/tavern-runtime`. Persistent tavern data lives in `/opt/data/tavern-state`.

## When to Use

Use this skill when the user wants to:

- open a story world, continue a scene, or move a scene into the tavern liveware;
- find, import, or create SillyTavern/Chub character cards;
- join one or more character cards into a world;
- add background, rules, secrets, places, or other lore to a world;
- distinguish reusable library material from current-world state;
- continue, recall, review, or refine a tavern world;
- inspect the story curator's story profile, growth, intimacy, or remembered acting preferences;
- configure or test the tavern model provider;
- set up the user's own persona ("我的角色") in the console right panel;
- operate the tavern liveware app in ClawChat.

Do not use this skill for ordinary facts, unrelated coding work, or general ClawChat platform maintenance.

## Primary CLI

Use the CLI instead of browser scraping, manual PNG/base64 card generation, or direct JavaScript injection into the console:

```sh
python3 /opt/data/skills/creative/tavern/scripts/tavern_cli.py <command>
```

Core commands:

- `new-world --name "world name"`: create a blank world.
- `search "<query>" [--n 8]`: find existing Chub/SillyTavern cards.
- `add <fullPath|Chub URL> [--name "world name"]`: import a real card and open a world from it.
- `starter [<number|name>] [--name "world name"]`: use bundled starter cards when Chub is unreachable or the user wants a quick start.
- `add-original <jsonfile|-> [--name "world name"]`: import an explicitly original SillyTavern V2 JSON card and open a world from it.

  - **PITFALL**: `add-original` auto-creates a standalone production and worldbook for the new card. When the card is meant for an existing world, after `attach-card` succeeds, delete the auto-created production (`tavern-state/productions/prod_<id>.json`) and its worldbook (`tavern-state/worldbooks/wb_prod_prod_<id>.json`) to avoid orphan worlds cluttering the left rail.

- `attach-card <world> <card>`: join an already imported card into an existing world.
- `add-lore <world> "natural language setting"`: add a natural-language setting to a world; the runtime organizes it into lore entries.

  - **PITFALL**: `add-lore` auto-generates entries that can still have content-modeling issues: (a) `constant=true` makes trigger keys irrelevant; (b) character identity, personality, and backstory belong in character cards rather than worldbook entries; (c) generated keys can be too broad (`学校`, `老师`, `学生`); and (d) repeated additions can create near-duplicate entries. After substantial additions, run `lore-audit <world>` and narrow keys, remove duplicate entries, and move character-only facts back to cards.

  - **Fixing entries that `lore-fix --apply` cannot reach**: `lore-fix --apply --confirm` only narrows broad trigger keys and disables recursive scanning. For other targeted corrections, edit the production-owned worldbook file identified by `production.worldbook_ids`, or use the Liveware `update_lore` API. Do not add a `worldbooks` object back into the production JSON.
- `add-worldbook <jsonfile|-> [--production <world id>]`: import structured lore/worldbook JSON and optionally attach it to a world. The flag remains `--production` for runtime compatibility.

  - **Worldbook dual-storage architecture**: worldbook data exists in two places. The **independent file** (`tavern-state/worldbooks/wb_prod_*.json`) is the canonical store written by the CLI and the API. The **production JSON** (`tavern-state/productions/prod_*.json`) contains an embedded `worldbooks` array that is the runtime cache — the model (`server.py _loadout()` L1163-1170) reads THIS embedded copy, not the independent file. The CLI only writes the independent file; it does NOT automatically sync the production JSON's embedded `worldbooks` array. After editing worldbooks via CLI or direct file write, you MUST manually sync the updated entries into the production JSON's embedded `worldbooks` field, or the model will continue reading stale data. Use `execute_code` with `json.load`/`json.dump` to copy the updated entries from the independent file into the production file's `worldbooks` array. The frontend also reads the embedded copy, so syncing fixes both the model and the UI in one step.
- `list`: list worlds, cast, and lore groups.
- `recall <world> [--last N]`: read actual tavern story history before continuing, reviewing, or referencing it.
- `learn "<preference>" [--reason "<why>"]`: store durable cross-world acting preferences.
- `reflect <world>`: distill a world's story into actor learning after a meaningful scene or review, then write it into the story curator's story profile.
- `reflect-preview <world>`: preview what `reflect` would learn without writing to the story profile. Use before uncertain or noisy scenes.
- `note <world> "<director note>"`: set world-specific direction.
- `card`: read the story curator's story profile, growth, intimacy, and known preferences.
- `profile-audit`: turn the story curator's story profile into recommendation signals for worlds, roles, and story tone. Read-only.
- `recommend ["want"]`: combine the story curator's story profile, local worlds, and local character library into one actionable recommendation. Read-only.
- `plan-world "idea" [--name "..."] [--style "..."]`: convert a loose user idea into a world/cast/lore/opening implementation plan. Read-only; it does not create state.
- `setup-world "idea" [--card ...] [--lore ...] [--apply --confirm]`: plan or conservatively create a world from one idea. Default is read-only; apply requires explicit confirmation.
- `card-audit <card>`: read-only quality audit for a local character card: identity, voice, opening, user placeholders, worldbook mixing, and playability.
- `card-fix <card> --plan`: read-only repair plan for a character card. It does not rewrite card files.
- `diagnose <world>`: read-only diagnosis for a world's cast, persona, lore, story, format, and structural health.
- `lore-audit <world> [--verbose]`: read-only audit of worldbook trigger keys, constant/selective entries, recursion, `{{user}}` residue, and pollution risk.
- `lore-fix <world> --plan`: read-only repair plan for worldbook/lore issues found by audit: broad keys, duplicate keys, empty entries, overlong constants, recursion, and `{{user}}` leakage.
- `lore-fix <world> --apply --confirm`: conservative mechanical worldbook repair. It only narrows broad trigger keys and disables recursive scanning; it does not rewrite lore content.
- `model list|add|use|rm|test`: manage tavern model configuration.

## Core Invocation Strategy

Treat these rules as first-order skill behavior, not optional reference material:

- **Workflow discipline**: Before risky data modification (cards, worldbooks, live worlds, story history), run the audit/plan chain first. Never skip to direct JSON edits when user context may be lost. The correct path for structural fixes is: `diagnose` → `lore-audit` → `card-audit` → `card-fix --plan` or `lore-fix --plan` → then apply. Small explicit UI-equivalent updates such as `set_persona`, `attach-card`, or `add-lore` may be applied when the user clearly asks.
- **Do not modify production story history** unless the user explicitly asks. The `story` array in the production file is the user's ongoing play — overwriting `story[0]` or `alts` without permission destroys their context. Lore and card updates are sufficient to shift the scene; the user will continue from where they left off.

  - **PITFALL — proposing to clear history**: Before suggesting to clear, reset, or rewrite conversation history, always read the production file or run `recall <world>` first. The user may have an ongoing conversation they value. Proposing destruction without reading what's there first breaks trust. If the user reports a format or quality issue with the latest reply, inspect the actual output before proposing any fix that touches history.
- If the user says "帮我找一个世界和角色", "推荐一个世界", "我想玩...", or asks the story curator to choose roles/worlds, run `recommend` first. Add `--external` when local roles are insufficient or the user wants public cards. Use `profile-audit` only when the user asks why a recommendation fits, and use `card` only when the user asks to see the raw story profile.
- Before recommending worlds or roles, use story profile signals: `knows`, recent growth, specialties, roles played, and intimacy. Do not turn this into a questionnaire if the profile already gives a good direction.
- If the user gives a loose idea for a new world, run `setup-world <idea>` or `plan-world` before creating anything. Only run `setup-world --apply --confirm` after the user explicitly confirms the plan.
- Before creating or restructuring a world, use `references/content-modeling.md` to decide what belongs in cards, worldbook, persona, story state, author note, and runtime protocol.
- If the user wants an existing character, fandom character, public card, or named persona, use `search` and then `add` or import the card and `attach-card` it to the chosen world. Do not invent the card from memory.
- When creating or cleaning character cards, follow `references/card-authoring.md`. Run `card-audit <card>` before using a card as the core of a new world or when a role feels unstable; run `card-fix <card> --plan` when the user asks how to repair it.
- When creating, auditing, or repairing worldbook/lore entries, follow `references/worldbook-authoring.md`.
- If Chub/search is unreachable, use `starter` as the offline fallback. Do not hand-roll PNG/base64 card files.
- If the user explicitly asks for an original character, write SillyTavern V2 JSON and import it with `add-original`. Clearly treat it as original.
- If the user gives background, rules, secrets, places, or mood, prefer `add-lore <world> "..."` for natural-language settings. Use `add-worldbook` only when the user provides structured worldbook JSON.
- In ordinary ClawChat conversation, saying “改一下世界/角色/设定” is not automatically effective. It becomes real only after the story curator uses the tavern skill/API to write the backend state, or the user edits it in the Liveware console.
- Lore entries are dispatched by keys plus scene/story state, and may use `constant`, `selective`/`secondary_keys`, `exclusion_keys`, `probability`, `priority`, `insertion_order`, `position`, and explicit `recursive` scanning. Keep advanced knobs in data, not as routine user-facing UI.
- If the user asks to continue, inspect, judge, summarize, or refer to a previous tavern scene, run `recall` before answering.
- If the user gives acting feedback or a durable preference, run `learn` immediately with the preference and reason.
- If the user wants to replace `{{user}}` with a canon character name (e.g., 席德 for Shadow) and set up their own separate persona, update the current world only: (1) use `set_persona` with `production_id`, (2) add/update current-world lore for public identity/power ranking, and (3) rewrite the cached opening text/alts only for a brand-new world or when the user explicitly asks. See `references/card-localization.md` §Custom Character / Power Dynamic Restructuring.
- If a meaningful scene ends, the user asks for a review, or the conversation moves away from a world, run `reflect-preview` first when the signal is uncertain; run `reflect` only when the preview contains real reusable user preference.
- If the user says a world feels wrong, chaotic, off-character, empty, slow, format-broken, or asks "why did this happen", run `diagnose <world>` before proposing fixes.
- If the issue involves worldbook/lore/设定/关键词/角色身份 leaking into the wrong place, run `lore-audit <world>` after `diagnose` or directly when the user asks about lore structure. If the user asks how to fix it, run `lore-fix <world> --plan` before editing data.
- If the user asks what the story curator remembers, how the story curator has grown, intimacy level, or story-profile state, run `card` before answering.
- Use `note` for story directions that should affect only one world, such as relationship tension, scene focus, pacing, or an immediate narrative intention. Do not use it to duplicate runtime-owned output-format rules.

  - **PITFALL — duplicating runtime output rules**: Global output format, punctuation, sentence boundaries, narration markup, and dialogue markup are owned by the runtime output protocol in `actor.py`. Do not add or copy those rules into character-card `system_prompt`, `post_history_instructions`, worldbook entries, director notes, user memory, or story history. Those channels contain character, world, scene, and durable preference data only. When output formatting fails, diagnose the runtime prompt/model response path instead of creating another prompt layer.

  - **PITFALL — `system_prompt` vs `post_history_instructions`**: These two fields on a character card are tavern-specific extensions (not part of any standard card format) and serve different injection points with very different effective power. `system_prompt` is injected before conversation history, buried inside the long character-description block — its positional priority is weak; most of what goes here could live in `personality` or `description` instead. `post_history_instructions` is optional, injected AFTER conversation history and right before the output contract — it is the STRONGEST injection point in the entire prompt, the last thing the model sees before generating. Reserve it for character-specific behavior that must never be forgotten, like relationship boundaries or knowledge constraints that aren't covered by description/personality. Neither field may carry the runtime's global output-format or punctuation protocol.
  - **PITFALL — confusing worldbook with world settings**: When the user says "添加到世界设定" or "在世界设定里看不到", they are looking at the **director's note** (`note` command / `author_note` field), not the worldbook. The worldbook entries (even constant ones) live under a separate "世界书/Lore" section in the UI. If the user explicitly asks for something to appear in "世界设定", use `note <world> "<text>"`. A constant worldbook entry and a director note are two separate injection channels that can carry the same instruction — having both is redundant. Prefer the director note for instructions the user wants to see and edit directly; prefer the worldbook for trigger-keyed lore that should only appear in relevant scenes. If the instruction already exists as a constant worldbook entry and the user says "我怎么没看到", it's because they're looking at the wrong UI panel — point them to the worldbook panel, don't duplicate into the note.\n\n    - **PITFALL — author_note is invisible in the frontend**: The `author_note` field is a pure server-side injection — it is read from the production JSON and fed directly into the model prompt without ever being sent to the frontend. The frontend JavaScript (`app.js`) has zero references to `author_note`, `导演提示`, or `作者注释`. When the user says "我怎么没看到", and you set it via `note <world>`, the answer is: it's invisible by design. Only the worldbook entries appear in the UI. The `author_note` is injected into every turn as a system message labeled `〔导演提示，本回合照此调整〕`, so the model sees it but the user cannot inspect or edit it in the console.

## Console UI Features

The tavern console is world-driven:

- **Left rail (Worlds)**: choose an existing world or click "开启新世界". Creation paths are intentionally simple: "自建世界" creates a blank world; "导入世界" chooses from the reusable worldbook library.
- **库 (Library)**: read-only browsing for reusable assets. `角色卡库` shows reusable character cards; `世界书库` shows reusable world templates. Do not confuse these with the current world's running lore.
- **登场角色 (Cast)**: cards currently joined to this world. It defaults collapsed in the right panel. Edit mode can add roles from the character library, create a role, or remove a role from this world without deleting the library card.
- **世界设定 (Lore)**: current-world settings, rules, places, secrets, and background. It defaults collapsed in the right panel. Edit mode can add/delete lore for this world. Constant entries appear before triggered entries.
- **我的角色 (Persona)**: the user's own in-story identity for this world. It is scoped to the current world, not cross-world. Supports manual editing (name + description) and importing from the character-card library.
  - **Programmatic persona setup**: POST `{"type":"set_persona", "production_id":"<world_id>", "name":"...", "description":"..."}` to `http://127.0.0.1:8799/api/event`. The `/api/persona` endpoint is legacy read-only and returns `{}` to avoid cross-world bleed.

  - **PITFALL**: `set_persona` only writes to `/opt/data/tavern-state/persona.json`. The server reads persona from the production file's embedded `persona` field (`productions/<prod_id>.json` → `"persona"`). After calling `set_persona`, the production file's `persona` field is still `{}` — the frontend will show "还没设". **Fix**: after `set_persona`, read `persona.json` and write its contents into the production file's `persona` field. Verify with `curl /api/productions` to confirm the persona name appears.

  - **Name-change cleanup**: when renaming a character (card `name`, `description`, `system_prompt`), also check the worldbook for stale old names in `secondary_keys` — they linger and can trigger on the old name unexpectedly. After editing embedded cards in the production file, sync the standalone card files under `tavern-state/cards/<card_id>.json` — the production embeds are runtime copies; the standalone files are the canonical library cards. Use `execute_code` with `json.load`/`json.dump` to mirror the updated fields into the standalone file.

When a user asks about their own character or persona, point them to the right panel's "我的角色" section. The CLI has no dedicated persona command — persona is managed through the console UI or the `set_persona` server event with `production_id`.

## Conversation Posture

- In normal ClawChat conversation, speak as the story curator. Do not expose tool mechanics unless the user asks what happened technically.
- Prefer softer wording such as "走故事", "开一段", "入场", "接住设定", and "慢慢往下走" over repeatedly saying "演".
- When recommending a world, present a small number of clear options: one world direction, one or more cast choices, and the first scene hook.
- Keep replies short enough for the user to answer. Move the scene forward, but do not decide the user's actions or feelings for them.
- If a liveware URL is useful, send the actual tavern or story-profile URL plainly so ClawChat can render it.

## References

Read only the reference needed for the user's task:

- Recommendation and world planning workflow: `references/recommendation-planning.md`
- Content modeling and placement rules: `references/content-modeling.md`
- Character cards, worlds, and lore workflow: `references/card-workflow.md`
- Character card authoring and cleanup: `references/card-authoring.md`
- Worldbook authoring and trigger design: `references/worldbook-authoring.md`
- Story profile, recall, learning, reflection, and director notes: `references/actor-memory.md`
- Diagnostics for broken worlds, bad output, empty replies, and runtime structure: `references/diagnostics.md`
- Worldbook/lore trigger hygiene and audit workflow: `references/lore-audit.md`
- Model provider setup and key handling: `references/model-config.md`
- Liveware provisioning, bringup, health checks, greeting bootstrap, and app paths: `references/liveware-ops.md`
- UI localization and i18n changes: `references/i18n.md`
- Card localization (English→Chinese translation workflow): `references/card-localization.md`
- Event-driven world updates (adding arcs, scenario shifts, cascade edits): `references/event-driven-update.md`
- Multi-card world expansion and setting rewrite workflow: `references/world-expansion.md`
- Cloning or rebuilding a world from existing cards/lore/persona: `references/world-rebuild.md`

## Guardrails

- Existing characters should use real cards via `search`/`add`; do not invent them from memory.
- Original cards require explicit user intent and should be labeled as original.
- If Chub is unreachable, use `starter`; do not hand-roll PNG card files.
- Read existing tavern story with `recall` before continuing or reviewing a world.
- Use `recommend` before recommending worlds or roles from the user's taste. Use `setup-world`/`plan-world` before creating a world from a loose idea. Use `card-audit` and `card-fix --plan` before relying on a weak card as a core role.
- Use `diagnose` before guessing causes for a broken world; use `lore-audit` before editing worldbook structure; use `lore-fix --plan` to produce a repair plan before applying changes.
- Store acting preferences with `learn` or `reflect`; do not rely on ordinary chat memory for tavern generation.
- Never repeat a full model key back to the user.
- Keep persona files out of the skill. `/opt/data/SOUL.md` is the source of the story curator's main soul.

## Troubleshooting: Empty Model Responses

If the user reports "sending messages but nothing generates" (模型没反应/生成空白):

**Most likely cause**: The story history contains empty `char` role messages from a previous failed generation. These empty assistant messages pollute the model's context and cause cascading failures — the model sees a blank previous reply and continues outputting blanks.

**Diagnosis**: Read the production story and check for entries where `role=char` and `text` (or `content`) is empty (`len=0`).

**Fix**:
1. Clean out all empty `char` entries from the production's `story` array, plus any user messages that follow them (they were responses to the blank output).
2. Keep only: the first_mes (`story[0]`) + the first legitimate user message.
3. Regenerate by sending the first user message again via the `send_message` event.
4. If it generates correctly, the cascade is broken.

**Root prevention**: If a single generation returns empty, clean it immediately before the user sends another message — don't let empty char messages accumulate in context.

## Troubleshooting: Wrong Speaker / Narrative Format

If the model replies in third-person narration instead of character dialogue, or speaks as the user's persona instead of the target character:

**Symptoms**:
- `*李东*："..."` — the model narrates the user's persona speaking, instead of the character responding
- The reply is pure scene description with no character dialogue
- The model writes like an omniscient narrator rather than inhabiting the character

**Likely causes**:
1. The card's `first_mes` is written in narrative style, and the model is continuing that narrative voice
2. The `system_prompt` doesn't explicitly instruct first-person character response
3. The story context contains narrative-style entries that the model is mirroring

**Diagnosis**: Read the latest `char` reply in the production file. Check whether the text contains `*角色名*："..."` (narrating another character) or actual first-person dialogue from the target character.

**Fix**:
1. Ensure `system_prompt` starts with a clear instruction like "以苏念清的身份回复" or "Respond as {name}"
2. Ensure `mes_example` shows the character speaking in first person, not being narrated
3. If the story history contains narrative-style char replies, the user may need to continue from before the format broke

## Troubleshooting: Output Format Drift

When punctuation, sentence boundaries, narration markup, or dialogue markup drift, inspect the effective `actor.py` output protocol, selected language, provider response, retries, and the latest raw model output. Do not write corrective format rules into cards, lore, director notes, memory, or history. Fix the single runtime-owned protocol or provider path, then test a fresh turn.

## Troubleshooting: Liveware / Web Tavern Stuck on "World is Building" / "世界正在构建…"

If the user reports that the liveware app (in ClawChat) or the web tavern is stuck on the loading/thinking indicator after they send a message:

**Symptoms**:
- The UI shows "世界正在构建…" / "World is building..." and never returns a reply
- The user can send new messages but gets no response
- The issue affects the tavern liveware app, not the current ClawChat agent conversation

**Diagnosis checklist**:
1. **Check the backend health**: `curl -fsS http://127.0.0.1:8799/api/health` and `curl -fsS https://<app-id>.apps.clawling.io/api/health` should both return `{"ok": true, ...}`
2. **Check the gateway is running**: `HERMES_HOME=/opt/data /opt/hermes/.venv/bin/hermes gateway status`
3. **Check gateway logs for timeouts**: `tail -n 100 /opt/data/logs/gateway.log` and look for `TimeoutError` in `send_frame` / `clawchat_gateway/connection.py` — this indicates the ClawChat connection is waiting for acknowledgments that aren't arriving
4. **Check the errors log**: `HERMES_HOME=/opt/data /opt/hermes/.venv/bin/hermes logs errors --lines 100` for API connection failures or stream drops
5. **Inspect the production file**: look for empty `char` role entries in the story array (length 0) or malformed content that could cause generation to fail silently

**Most common causes**:
1. **ClawChat connection timeout**: `send_frame` waits for an ACK that never arrives. This can happen when the gateway<->ClawChat connection is unstable. The backend itself is healthy but the message delivery channel is blocked.
2. **Model provider connection error**: the configured model API is slow or unreachable, causing the generation to hang.
3. **Empty/malformed char messages accumulated in story history**: previous failed generations left empty `char` entries that pollute the context and cause the model to continue producing empty responses.

**Fixes**:
1. **For ClawChat connection timeouts**: restart the gateway. If the issue persists, the ClawChat platform side may be slow; wait a moment and retry.
2. **For model provider issues**: check `/api/health` and test a simple chat request. If the model endpoint is unreachable, wait for it to recover or switch model config.
3. **For empty char messages**: clean the production's `story` array by removing empty `char` entries and any user messages that responded to them. Then regenerate from the last valid turn.
4. **For general stuck state**: open the tavern web UI directly at the liveware URL and try sending from there. If the web UI works but the ClawChat bot doesn't, the issue is the ClawChat message delivery layer, not the tavern backend.

**PITFALL**: Do not confuse the tavern liveware app with the ClawChat agent chat. When the user says "世界正在构建…", they are usually referring to the tavern bot in their ClawChat chat or the web tavern, not the current agent conversation. Ask explicitly or check the liveware app logs first.
