"""Semantic preparation for externally sourced character cards.

Parsing remains deterministic in ``card_import``.  This module performs the
one-time semantic job required before an external card is stored: shape the
main character profile, separate supporting characters from shared lore, and
produce a validated, reviewable import plan.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re

import card_import


SCHEMA_VERSION = "tavern-card-preparation/v1"
MAX_SOURCE_CHARS = 90000
MAX_WORLD_ENTRIES = 96
MAX_SUPPORTING_CHARACTERS = 16


def _text(value, limit=4000):
    return str(value or "").strip()[:limit]


def _list(value, limit=12, item_limit=240):
    values = value if isinstance(value, list) else ([value] if value else [])
    result = []
    for item in values:
        text = _text(item, item_limit)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _json_from_text(value):
    text = str(value or "").strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except (TypeError, ValueError):
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.I | re.S)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            return parsed if isinstance(parsed, dict) else None
        except ValueError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            return parsed if isinstance(parsed, dict) else None
        except ValueError:
            return None
    return None


def _book_entries(card):
    book = card.get("character_book") if isinstance(card.get("character_book"), dict) else {}
    entries = book.get("entries") if isinstance(book.get("entries"), list) else []
    result = []
    for index, item in enumerate(entries[:MAX_WORLD_ENTRIES]):
        if not isinstance(item, dict):
            continue
        content = _text(item.get("content") or item.get("text"), 6000)
        if not content:
            continue
        result.append({
            "source_id": f"entry-{index}",
            "name": _text(item.get("name") or item.get("comment"), 180),
            "keys": _list(item.get("keys") or item.get("key"), 12, 100),
            "content": content,
            "constant": bool(item.get("constant")),
            "enabled": item.get("enabled", True) is not False,
            "priority": item.get("priority", item.get("order", 5)),
            "source": copy.deepcopy(item),
        })
    return result


def _source_payload(card):
    entries = _book_entries(card)
    payload = {
        "main_character_name": _text(card.get("name"), 160),
        "source_format": card.get("source_format") or "unknown",
        "card_fields": {
            "description": _text(card.get("description"), 12000),
            "personality": _text(card.get("personality"), 6000),
            "scenario": _text(card.get("scenario"), 6000),
            "first_mes": _text(card.get("first_mes"), 6000),
            "mes_example": _text(card.get("mes_example"), 6000),
            "system_prompt": _text(card.get("system_prompt"), 6000),
            "post_history_instructions": _text(card.get("post_history_instructions"), 4000),
            "profile": card.get("profile") or {},
            "entry": card.get("entry") or {},
            "performance": card.get("performance") or {},
        },
        "embedded_entries": [
            {key: entry[key] for key in (
                "source_id", "name", "keys", "content", "constant", "enabled", "priority")}
            for entry in entries
        ],
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    if len(serialized) > MAX_SOURCE_CHARS:
        raise ValueError("角色卡可整理文本过长，请先精简内嵌世界书后再导入")
    return payload, entries


def _profile_has_details(profile):
    if not isinstance(profile, dict):
        return False
    for section_name, section in profile.items():
        if not isinstance(section, dict):
            continue
        for key, value in section.items():
            if section_name == "identity" and key == "name":
                continue
            if isinstance(value, list) and any(str(item or "").strip() for item in value):
                return True
            if not isinstance(value, (dict, list)) and str(value or "").strip():
                return True
    return False


def _canonical_profile(value, fallback_name):
    raw = value if isinstance(value, dict) else {}
    profile = card_import.canonical_profile({
        "name": fallback_name,
        "profile": raw,
    })
    profile["identity"]["name"] = _text(
        profile["identity"].get("name") or fallback_name, 160)
    return profile


def _render_description(profile):
    sections = []
    mapping = (
        ("身份", "identity", ("description", "gender", "age", "species", "occupation", "affiliations", "story_role")),
        ("外观", "appearance", ("summary", "features", "attire")),
        ("性格", "personality", ("summary", "traits", "values", "motivation", "fears", "boundaries")),
        ("表达", "expression", ("speech_style", "habits", "mannerisms")),
        ("能力", "capabilities", ("skills", "powers", "limitations")),
        ("背景", "background", ("summary", "key_history")),
    )
    for label, section_name, keys in mapping:
        source = profile.get(section_name) if isinstance(profile.get(section_name), dict) else {}
        lines = []
        for key in keys:
            value = source.get(key)
            values = value if isinstance(value, list) else ([value] if value else [])
            for item in values:
                text = _text(item, 700)
                if text and text not in lines:
                    lines.append(text)
        if lines:
            sections.append(f"<{label}>\n" + "\n".join(f"- {line}" for line in lines) + f"\n</{label}>")
    return "<角色>\n" + "\n".join(sections) + "\n</角色>"


def _entry(value, fallback):
    raw = value if isinstance(value, dict) else {}
    return card_import.canonical_entry({
        "entry": raw,
        "scenario": fallback.get("scenario"),
        "first_mes": fallback.get("first_mes"),
        "mes_example": fallback.get("mes_example"),
    })


def _performance(value, fallback):
    raw = value if isinstance(value, dict) else {}
    return card_import.canonical_performance({
        "performance": raw,
        "system_prompt": fallback.get("system_prompt"),
        "post_history_instructions": fallback.get("post_history_instructions"),
    })


def _source_ids(value, known):
    values = value if isinstance(value, list) else []
    result = []
    for item in values:
        source_id = str(item or "").strip()
        if source_id in known and source_id not in result:
            result.append(source_id)
    return result


def _world_entry(value, source_by_id):
    if not isinstance(value, dict):
        return None
    source_ids = _source_ids(value.get("source_entry_ids"), source_by_id)
    if not source_ids:
        return None
    originals = [source_by_id[source_id] for source_id in source_ids]
    content = _text(value.get("content"), 6000)
    if not content:
        content = "\n".join(entry["content"] for entry in originals)
    keys = _list(value.get("keys"), 12, 100)
    if not keys:
        for original in originals:
            for key in original["keys"]:
                if key not in keys:
                    keys.append(key)
    constant = bool(value.get("constant", all(entry["constant"] for entry in originals)))
    try:
        priority = int(value.get("priority", 5) or 5)
    except (TypeError, ValueError):
        priority = 5
    return {
        "id": "lore_" + hashlib.sha1(
            ("|".join(source_ids) + "|" + content).encode("utf-8")
        ).hexdigest()[:12],
        "name": _text(value.get("name") or originals[0]["name"], 180),
        "keys": keys,
        "content": content,
        "enabled": value.get("enabled", all(entry["enabled"] for entry in originals)) is not False,
        "constant": constant,
        "selective": bool(value.get("selective", False)),
        "secondary_keys": _list(value.get("secondary_keys"), 8, 100),
        "exclusion_keys": _list(value.get("exclusion_keys"), 8, 100),
        "priority": max(1, min(10, priority)),
        "position": value.get("position") if value.get("position") in ("before_char", "after_char") else "before_char",
        "category": _text(value.get("category") or "setting", 80),
        "source_entry_ids": source_ids,
    }


def _supporting_card(value, original_card, source_by_id):
    if not isinstance(value, dict):
        return None
    name = _text(value.get("name"), 160)
    source_ids = _source_ids(value.get("source_entry_ids"), source_by_id)
    if not name or not source_ids:
        return None
    profile = _canonical_profile(value.get("profile"), name)
    if not _profile_has_details(profile):
        return None
    description = _render_description(profile)
    card = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "source_format": original_card.get("source_format") or "unknown",
        "name": name,
        "description": description,
        "personality": profile["personality"].get("summary") or "、".join(profile["personality"].get("traits") or []),
        "scenario": "",
        "first_mes": "",
        "mes_example": "",
        "system_prompt": "",
        "post_history_instructions": "",
        "alternate_greetings": [],
        "group_only_greetings": [],
        "tags": _list(original_card.get("tags"), 12, 120),
        "creator": original_card.get("creator") or "",
        "source": original_card.get("source") or "",
        "source_urls": copy.deepcopy(original_card.get("source_urls") or []),
        "profile": profile,
        "entry": card_import.canonical_entry({}),
        "performance": card_import.canonical_performance({}),
        "extensions": {"tavern": {"prepared_from": original_card.get("id"), "source_entry_ids": source_ids}},
        "source_unknown": {},
    }
    card["id"] = "card_" + hashlib.sha1(
        (name + "|" + description[:500]).encode("utf-8")
    ).hexdigest()[:12]
    return card


def _normalize_result(card, raw, entries):
    if not isinstance(raw, dict):
        raise ValueError("角色卡整理模型没有返回 JSON 对象")
    source_by_id = {entry["source_id"]: entry for entry in entries}
    main = raw.get("main_character") if isinstance(raw.get("main_character"), dict) else {}
    profile = _canonical_profile(main.get("profile"), card.get("name"))
    profile["identity"]["name"] = _text(card.get("name"), 160)
    if not _profile_has_details(profile):
        raise ValueError("整理后仍没有可用的主角色资料，已拒绝写入空白角色卡")

    entry = _entry(main.get("entry"), card)
    performance = _performance(main.get("performance"), card)
    prepared = copy.deepcopy(card)
    original_book = copy.deepcopy(prepared.get("character_book"))
    original_fields = {
        key: copy.deepcopy(prepared.get(key))
        for key in ("description", "personality", "scenario", "first_mes", "mes_example")
    }
    prepared["profile"] = profile
    prepared["entry"] = entry
    prepared["performance"] = performance
    prepared["name"] = profile["identity"]["name"] or card.get("name")
    prepared["description"] = _render_description(profile)
    prepared["personality"] = profile["personality"].get("summary") or "、".join(profile["personality"].get("traits") or [])
    prepared["scenario"] = entry["initial_scenario"]
    prepared["first_mes"] = entry["first_message"]
    prepared["mes_example"] = entry["example_dialogue"]

    world_entries = []
    covered = set()
    for value in raw.get("worldbook_entries") or []:
        normalized = _world_entry(value, source_by_id)
        if normalized:
            covered.update(normalized["source_entry_ids"])
            world_entries.append(normalized)

    supporting = []
    for value in (raw.get("supporting_characters") or [])[:MAX_SUPPORTING_CHARACTERS]:
        normalized = _supporting_card(value, card, source_by_id)
        if normalized:
            covered.update(((normalized.get("extensions") or {}).get("tavern") or {}).get("source_entry_ids") or [])
            supporting.append(normalized)

    main_sources = _source_ids(main.get("source_entry_ids"), source_by_id)
    covered.update(main_sources)
    unresolved = _source_ids(raw.get("unresolved_entry_ids"), source_by_id)
    covered.update(unresolved)
    missing = sorted(set(source_by_id) - covered)
    if missing:
        raise ValueError("整理结果遗漏内嵌条目：" + "、".join(missing[:12]))

    if world_entries:
        prepared["character_book"] = {
            "name": _text((original_book or {}).get("name") or prepared["name"], 180),
            "entries": world_entries,
        }
    else:
        prepared.pop("character_book", None)

    unknown = prepared.get("source_unknown") if isinstance(prepared.get("source_unknown"), dict) else {}
    unknown["semantic_import"] = {
        "original_fields": original_fields,
        "original_character_book": original_book,
        "main_source_entry_ids": main_sources,
        "unresolved_entry_ids": unresolved,
    }
    prepared["source_unknown"] = unknown
    extension = prepared.get("extensions") if isinstance(prepared.get("extensions"), dict) else {}
    tavern = extension.get("tavern") if isinstance(extension.get("tavern"), dict) else {}
    tavern["preparation_schema"] = SCHEMA_VERSION
    extension["tavern"] = tavern
    prepared["extensions"] = extension

    return {
        "schema": SCHEMA_VERSION,
        "card": prepared,
        "supporting_cards": supporting,
        "summary": {
            "main_character": prepared["name"],
            "profile_ready": True,
            "supporting_characters": [item["name"] for item in supporting],
            "worldbook_entries": len(world_entries),
            "main_character_entries": len(main_sources),
            "unresolved_entries": len(unresolved),
            "warnings": _list(raw.get("warnings"), 12, 300),
        },
    }


def _prompt(payload):
    schema = {
        "main_character": {
            "source_entry_ids": ["entry-0"],
            "profile": {
                "identity": {"name": "", "aliases": [], "description": "", "gender": "", "age": "", "species": "", "occupation": "", "affiliations": [], "story_role": ""},
                "appearance": {"summary": "", "features": [], "attire": []},
                "personality": {"summary": "", "traits": [], "values": [], "motivation": "", "fears": [], "boundaries": []},
                "expression": {"speech_style": "", "habits": [], "mannerisms": []},
                "capabilities": {"skills": [], "powers": [], "limitations": []},
                "background": {"summary": "", "key_history": []},
            },
            "entry": {"initial_scenario": "", "first_message": "", "example_dialogue": ""},
            "performance": {"system_prompt": "", "post_history_instructions": ""},
        },
        "supporting_characters": [{"name": "", "source_entry_ids": ["entry-1"], "profile": {}}],
        "worldbook_entries": [{"source_entry_ids": ["entry-2"], "name": "", "content": "", "keys": [], "constant": False, "priority": 5, "category": "setting"}],
        "unresolved_entry_ids": [],
        "warnings": [],
    }
    system = (
        "You normalize imported roleplay character cards. Return strict JSON only. "
        "The named main character must remain the main character. Organize only facts explicitly present in the source; never infer or invent. "
        "Put stable identity, appearance, personality, voice, abilities, and personal history in character profiles. "
        "Put locations, organizations, shared history, rules, and public setting facts in worldbook_entries. "
        "When one embedded entry mixes categories, split its content and cite the same source_entry_id in each destination. "
        "A different explicitly named person becomes a supporting character, not world lore. "
        "Temporary scene state and uncertain content go to unresolved_entry_ids. "
        "Every embedded source_entry_id must appear at least once in main_character.source_entry_ids, a supporting character, a worldbook entry, or unresolved_entry_ids. "
        "Keep output content in the source card's language. Use every key shown in the schema; empty values are allowed."
    )
    user = "Required JSON shape:\n" + json.dumps(schema, ensure_ascii=False) + "\n\nSource card:\n" + json.dumps(payload, ensure_ascii=False)
    return system, user


def prepare_card(card, chat, model=None):
    """Return a validated, side-effect-free semantic import plan."""
    normalized = card_import.normalize_card(card) if "source_format" not in card else copy.deepcopy(card)
    payload, entries = _source_payload(normalized)
    system, user = _prompt(payload)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last_error = ""
    for attempt in range(2):
        output = chat(messages, temperature=0.1, model=model, max_tokens=4000)
        parsed = _json_from_text(output)
        try:
            plan = _normalize_result(normalized, parsed, entries)
            plan["source_hash"] = hashlib.sha256(
                json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            plan["plan_id"] = "prep_" + hashlib.sha256(
                json.dumps(plan, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()[:20]
            return plan
        except ValueError as error:
            last_error = str(error)
            if attempt == 0:
                messages.extend([
                    {"role": "assistant", "content": output},
                    {"role": "user", "content": "The JSON failed validation: " + last_error + ". Return the complete corrected JSON object only."},
                ])
    raise ValueError("角色卡整理失败：" + (last_error or "模型未返回有效 JSON"))


def validate_plan(plan):
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA_VERSION:
        raise ValueError("不是受支持的角色卡整理计划")
    card = plan.get("card")
    if not isinstance(card, dict) or not str(card.get("name") or "").strip():
        raise ValueError("整理计划缺少主角色")
    profile = card_import.canonical_profile(card)
    if not _profile_has_details(profile):
        raise ValueError("整理计划中的主角色资料为空")
    plan_id = str(plan.get("plan_id") or "")
    unsigned = copy.deepcopy(plan)
    unsigned.pop("plan_id", None)
    expected = "prep_" + hashlib.sha256(
        json.dumps(unsigned, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    if plan_id != expected:
        raise ValueError("角色卡整理计划已被修改，请重新生成预览")
    return plan
