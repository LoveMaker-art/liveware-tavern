"""Reply text formatting helpers for Tavern runtime.

Pure formatting only: no model calls, no state writes, no production access.
"""
import re


def language_code(value: str = "zh") -> str:
    code = str(value or "zh").strip().lower()
    return "en" if code.startswith("en") else "zh"


def continue_note(note: str = "", response_language: str = "zh") -> str:
    if language_code(response_language) == "en":
        instruction = (
            "Continue from the current story in English and advance to the next natural narrative beat. "
            "Prefer the result of the next action, a new scene fragment, or a small passage of time so the situation changes perceptibly. "
            "Do not repeat the same emotion, action, or information. Keep action, environment, and dialogue coherent, and leave room for the user to respond."
        )
    else:
        instruction = (
            "结合目前的剧情进展，使用简体中文承接最后一条用户输入，推进到下一个自然剧情节点。"
            "优先选择下一个动作结果、下一个场景片段或轻微时间推进；让局面出现可感知的新变化。"
            "不要停留在原地反复解释同一种情绪、同一个动作或同一句信息；推进要克制，动作、环境与角色对白要自然连贯，并留下可继续回应的空间。"
        )
    return (note + "\n" if note else "") + instruction


def format_actor_paragraph(para: str) -> str:
    para = (para or "").strip()
    if not para:
        return ""
    # If a paragraph contains dialogue, keep the whole paragraph unitalicized.
    # Pure narration paragraphs are the only paragraphs wrapped in *...*.
    if "「" in para or "」" in para or re.match(r"^[\w\u4e00-\u9fff·]{1,12}：「[\s\S]*」$", para):
        return para.replace("*", "").strip()
    # Already-wrapped pure narration stays wrapped.
    if para.startswith("*") and para.endswith("*"):
        return para
    clean = para.replace("*", "").strip()
    return "*" + clean + "*" if clean else ""


def normalize_actor_reply(text: str) -> str:
    """Normalize generated actor text for tavern rendering without rewriting story content."""
    text = (text or "").strip()
    if not text:
        return ""
    text = (text.replace("**", "*")
                .replace("“", "「").replace("”", "」")
                .replace("『", "「").replace("』", "」"))
    out = []
    open_quote = True
    for ch in text:
        if ch == '"':
            out.append("「" if open_quote else "」")
            open_quote = not open_quote
        else:
            out.append(ch)
    text = "".join(out)
    text = re.sub(r"(^|\n)([\w\u4e00-\u9fff·]{1,12}):(?=「)", r"\1\2：", text)
    paras = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    formatted = [format_actor_paragraph(p) for p in paras]
    return "\n\n".join(p for p in formatted if p)
