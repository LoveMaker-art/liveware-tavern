"""Turn planning for multi-character Tavern replies.

This module owns the short per-turn speaker/director plan. It does not know
about HTTP, persistence, or active model registry; callers provide chat/model
functions from the runtime.
"""
import json


def card_names(cards):
    return [str(c.get("name") or "角色").strip() for c in cards if str(c.get("name") or "").strip()]


def closest_card_name(value, names):
    s = str(value or "").strip()
    if not s:
        return ""
    if s in names:
        return s
    folded = s.casefold()
    for n in names:
        if n and str(n).casefold() == folded:
            return n
    for n in names:
        if n and (n in s or s in n):
            return n
    return ""


def scene_story_excerpt(production, max_items=12, response_language=None):
    language = response_language or (production or {}).get("response_language") or "zh"
    en = language == "en"
    cname = "Story response" if en else "故事回复"
    lines = []
    for m in ((production or {}).get("story") or [])[-max_items:]:
        who = ("User" if en else "用户") if m.get("role") == "user" else cname
        text = (m.get("text") or "").strip().replace("\r\n", "\n")
        if text:
            lines.append(f"{who}: {text[:700]}")
    return "\n".join(lines)


def build_turn_plan(production, cards, *, response_language, story_state,
                    chat, model, json_from_model_text):
    if len(cards or []) <= 1:
        return {}
    language = response_language or "zh"
    en = language == "en"
    names = card_names(cards)
    sys = ((
        "You schedule a multi-character interactive story. Based on the current scene, active characters, and the user's latest message, create a very short turn plan in English. "
        "Do not write story prose or explanations. Output strict JSON with only primary_speaker, supporting_characters, silent_characters, narration_goal, and do_not. "
        "primary_speaker is a string; the other fields are strings or string arrays. Not every character must speak. Prefer the addressed or most motivated character and preserve knowledge boundaries."
    ) if en else (
        "你是互动故事的场面调度。根据当前场景、登场角色和用户最新输入，为下一次角色扮演回复制定极短的简体中文调度。"
        "不要写正文，不要解释。输出严格 JSON，字段只有 primary_speaker、supporting_characters、silent_characters、"
        "narration_goal、do_not。primary_speaker 是字符串，其余是字符串数组或字符串。"
        "原则：不要求所有角色说话；优先回应被用户点名或最有动机的人；保护角色知识边界。"
    ))
    plot = story_state or {}
    user = json.dumps({
        "characters": [{"id": c.get("id"), "name": c.get("name"),
                        "profile": c.get("profile") or {},
                        "persistent_status": c.get("persistent_status") or {},
                        "relationships": c.get("relationships") or []} for c in cards or []],
        "story_state": {key: plot.get(key) for key in
                        ("timeline", "facts", "open_threads", "objects", "secrets", "scene", "style_notes")},
        "response_language": language,
        "recent_story": scene_story_excerpt(production, response_language=language),
    }, ensure_ascii=False)
    out = chat([{"role": "system", "content": sys}, {"role": "user", "content": user}],
               temperature=0.15, model=model).strip()
    raw = json_from_model_text(out)

    def clean_arr(v, limit=6):
        if isinstance(v, str):
            v = [v]
        out = []
        for x in v or []:
            s = str(x).strip().lstrip("-•").strip()
            fixed = closest_card_name(s, names) or s[:120]
            if fixed and fixed not in out:
                out.append(fixed)
        return out[:limit]

    primary = closest_card_name(raw.get("primary_speaker"), names)
    return {
        "primary_speaker": primary,
        "supporting_characters": clean_arr(raw.get("supporting_characters")),
        "silent_characters": clean_arr(raw.get("silent_characters")),
        "narration_goal": str(raw.get("narration_goal") or "").strip()[:180],
        "do_not": clean_arr(raw.get("do_not")),
    }


def prepare_turn_plan(production, cards, **kwargs):
    try:
        return build_turn_plan(production, cards, **kwargs)
    except Exception:
        return {}
