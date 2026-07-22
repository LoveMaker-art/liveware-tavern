"""Lightweight structure index for Tavern character replies.

This module is deliberately rule-based: no model calls, no state writes.
Raw message text remains authoritative; segments are an auxiliary index for
diagnosis, TTS, and future scheduling analysis.
"""
import re


def segment_cast_aliases(cards=None):
    aliases = {}
    for c in cards or []:
        if not isinstance(c, dict):
            continue
        canonical = str(c.get("name") or c.get("id") or "").strip()
        if not canonical:
            continue
        for key in ("name", "nickname"):
            alias = str(c.get(key) or "").strip()
            if alias:
                aliases[alias] = canonical
        profile = c.get("profile") if isinstance(c.get("profile"), dict) else {}
        identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
        for key in ("name", "nickname", "title"):
            alias = str(identity.get(key) or "").strip()
            if alias:
                aliases[alias] = canonical
    return aliases


def parse_actor_segments(text, cards=None):
    """Parse char reply text into a conservative actor/narration index."""
    text = str(text or "")
    aliases = segment_cast_aliases(cards)
    if aliases:
        names_pat = "|".join(re.escape(x) for x in sorted(aliases, key=len, reverse=True))
        dialogue_re = re.compile(r"(?m)(^|\n)\s*(?P<speaker>" + names_pat + r")\s*[：:]\s*「(?P<text>[^」]*)」")
    else:
        dialogue_re = re.compile(r"(?m)(^|\n)\s*(?P<speaker>[\w\u4e00-\u9fff· ._-]{1,40})\s*[：:]\s*「(?P<text>[^」]*)」")

    def official(name):
        s = str(name or "").strip()
        return aliases.get(s, s)

    speakers = []
    dialogue_blocks = []
    for m in dialogue_re.finditer(text):
        speaker = official(m.group("speaker"))
        spoken = (m.group("text") or "").strip()
        if not speaker or not spoken:
            continue
        if speaker not in speakers:
            speakers.append(speaker)
        dialogue_blocks.append({
            "speaker": speaker,
            "text": spoken,
        })

    def names_in(s):
        found = []
        if aliases:
            for alias, canonical in aliases.items():
                if alias and alias in s and canonical not in found:
                    found.append(canonical)
        return found

    mentioned = []
    for name in names_in(text):
        if name not in mentioned:
            mentioned.append(name)

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    attributed_standalone = set()
    last_context_chars = []
    for para in paragraphs:
        clean = para.strip().strip("*").strip()
        if not clean:
            continue
        dm = dialogue_re.match(clean)
        if dm:
            speaker = official(dm.group("speaker"))
            last_context_chars = [speaker] if speaker else []
            continue
        qm = re.match(r"^「(?P<text>[^」]{1,1200})」$", clean)
        if qm and len(last_context_chars) == 1:
            speaker = last_context_chars[0]
            spoken = (qm.group("text") or "").strip()
            if spoken:
                if speaker not in speakers:
                    speakers.append(speaker)
                dialogue_blocks.append({
                    "speaker": speaker,
                    "text": spoken,
                    "inferred": True,
                    "source": "previous-single-character-narration",
                })
                attributed_standalone.add(clean)
            continue
        chars = names_in(clean)
        if chars:
            last_context_chars = chars

    narration_blocks = []
    for para in paragraphs:
        clean = para.strip().strip("*").strip()
        if not clean:
            continue
        if dialogue_re.match(clean) or clean in attributed_standalone:
            continue
        chars = names_in(clean)
        narration_blocks.append({
            "characters": chars,
            "text": clean,
        })

    action_only = []
    for block in narration_blocks:
        for name in block.get("characters") or []:
            if name not in speakers and name not in action_only:
                action_only.append(name)

    return {
        "version": 1,
        "parser": "rule-v1",
        "speakers": speakers,
        "action_only": action_only,
        "mentioned": mentioned,
        "dialogue_blocks": dialogue_blocks,
        "narration_blocks": narration_blocks,
    }


def set_message_segments(message, cards=None):
    if isinstance(message, dict) and message.get("role") == "char":
        message["segments"] = parse_actor_segments(message.get("text") or "", cards)
    elif isinstance(message, dict):
        message.pop("segments", None)
    return message
