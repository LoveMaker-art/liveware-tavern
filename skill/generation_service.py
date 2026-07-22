"""Foreground actor generation helpers for Tavern runtime.

This module owns how a reply is generated and retried. It does not own HTTP
events, persistence, cancellation, story-state scheduling, or background jobs.
Runtime dependencies are injected by server.py to avoid global coupling.
"""
import sys


def loadout(production, *, ensure_production_session):
    """Return cards, worldbooks, persona, and director note for one generation."""
    ensure_production_session(production)
    cards = [c for c in (production.get("cards") or []) if isinstance(c, dict)]
    worldbooks = [w for w in (production.get("worldbooks") or []) if isinstance(w, dict)]
    persona = production.get("persona") or {}
    note = production.get("author_note", "")
    return cards, worldbooks, persona, note


def perform_loaded(cards, worldbooks, persona, story, note, *,
                   actor_module, model, story_state, turn_plan, response_language):
    return actor_module.perform(
        cards, worldbooks, persona, story, note,
        model=model,
        story_state=story_state,
        turn_plan=turn_plan,
        response_language=response_language,
    )


def perform_into(production, *, turn_plan=None, actor_module, active_model,
                 effective_story_state, ensure_world_language,
                 prepare_turn_plan, ensure_production_session):
    cards, worldbooks, persona, note = loadout(
        production,
        ensure_production_session=ensure_production_session,
    )
    if turn_plan is None:
        turn_plan = prepare_turn_plan(production, cards)
    language = ensure_world_language(production)
    return perform_loaded(
        cards, worldbooks, persona, production["story"], note,
        actor_module=actor_module,
        model=active_model(),
        story_state=effective_story_state(production),
        turn_plan=turn_plan,
        response_language=language,
    )


def ensure_actor_reply(production, cards, worldbooks, persona, note, text, *,
                       turn_plan=None, actor_module, active_model,
                       effective_story_state, ensure_world_language,
                       prepare_turn_plan, normalize_actor_reply):
    text = normalize_actor_reply(text)
    if text:
        return text
    language = ensure_world_language(production)
    retry_instruction = (
        "Continue from the user's latest message with one coherent story response in English. "
        "Keep action, environment, and character dialogue naturally connected."
        if language == "en" else
        "承接最后一条用户输入，使用简体中文续写当前故事的一段内容。动作、环境与角色对白要自然连贯。"
    )
    retry_note = (note + "\n" if note else "") + retry_instruction
    if turn_plan is None:
        turn_plan = prepare_turn_plan(production, cards)
    try:
        text = normalize_actor_reply(perform_loaded(
            cards, worldbooks, persona, production["story"], retry_note,
            actor_module=actor_module,
            model=active_model(),
            story_state=effective_story_state(production),
            turn_plan=turn_plan,
            response_language=language,
        ))
    except Exception as e:  # noqa: BLE001
        print("actor retry failed:", repr(e), file=sys.stderr, flush=True)
        raise RuntimeError("模型暂时没有返回内容，请稍后重试。")
    if not text:
        print("actor retry returned empty", file=sys.stderr, flush=True)
        raise RuntimeError("模型暂时没有返回内容，请稍后重试。")
    return text
