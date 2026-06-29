"""actor — 演员运行时：把 loadout 拼成 prompt，调模型，生成入戏回复。

「角色 = 演员 × 剧本」落到拼装层：
  剧本   = 角色卡(card)            —— 导入的、静态
  演员   = actor_self.md           —— 我们独有、跨剧组共享、会成长（技艺/对你的了解层）
  世界   = 相关世界书条目          —— agent 选，不靠死关键词全量灌
  现场   = 本剧组故事线(story)     —— per 剧组隔离，绝不串别的剧组

LLM client 抄 clawchat-localagent/probe/probe_toolcall.py 的 chat()：纯 stdlib urllib
POST {base}/chat/completions。模型 creds 只在 server 进程的 env，页面永不见。
"""
import json
import os
import urllib.request

MODEL_BASE = os.environ.get("TAVERN_MODEL_BASE", "https://api.deepseek.com/v1")
MODEL_NAME = os.environ.get("TAVERN_MODEL", "deepseek-chat")
MODEL_TEMP = float(os.environ.get("TAVERN_MODEL_TEMP", "0.85"))


def _load_key():
    """env 优先；否则从 agent 的 .env 兜底读（creds 只在 server 端，页面永不见）。"""
    k = os.environ.get("TAVERN_MODEL_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if k:
        return k
    for envp in (os.path.expanduser("~/.hermes-tavern/.env"),):
        try:
            with open(envp, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("DEEPSEEK_API_KEY="):
                        return line.split("=", 1)[1].strip()
        except OSError:
            pass
    return ""


MODEL_KEY = _load_key()


def select_lore(worldbooks: list, story: list, lookback: int = 6) -> list:
    """选相关世界书条目：constant(蓝灯)恒入 + 关键词命中最近 N 条的入。
    MVP 的「agent 选」近似——不暴露递归/扫描深度这些机制给用户。"""
    recent = " ".join(
        (m.get("text") or "") for m in story[-lookback:]
    )
    picked, seen = [], set()
    for wb in worldbooks:
        for e in wb.get("entries", []):
            if not e.get("enabled", True):
                continue
            key = (wb.get("id"), e.get("content", "")[:40])
            if key in seen:
                continue
            hit = e.get("constant") or any(
                k and k in recent for k in (e.get("keys") or [])
            )
            if hit:
                picked.append(e)
                seen.add(key)
    picked.sort(key=lambda e: e.get("insertion_order", 100))
    return picked


def build_messages(card: dict, actor_self: str, lore: list, persona: dict, story: list) -> list:
    """组成 chat-completion 消息序列。系统块 = 演员 + 剧本 + 世界 + 人设 + 演出纪律。"""
    lore_txt = "\n".join("- " + (e.get("content") or "") for e in lore)
    persona_txt = ""
    if persona:
        persona_txt = f"\n\n## 对手戏（你的搭档「{persona.get('name','我')}」）\n{persona.get('description','')}"
    sysprompt_block = ("### 角色设定提示\n" + card["system_prompt"]) if card.get("system_prompt") else ""
    sys = f"""{actor_self}

——————————

你现在出演这个角色，全程**入戏不出戏**（除非搭档明显在跟你这个"演员"说话）。

## 你出演的角色：{card.get('name','')}
{card.get('description','')}

### 性格
{card.get('personality','')}

### 场景
{card.get('scenario','')}
{sysprompt_block}

## 世界设定（只在自然时机体现，别报菜名）
{lore_txt or '（无）'}{persona_txt}

## 演出纪律
- 用中文。动作/神态/环境用第三人称叙述，对白用「」。
- 给角色一个身体：手里在做什么、呼吸、环境的声音光线。
- 情绪藏细节，不直接喊。一回合别太长，留白给对方接。
- 推动剧情，别被动等喂；但尊重搭档的选择，不替对方做决定。
"""
    msgs = [{"role": "system", "content": sys}]
    for m in story:
        role = m.get("role")
        text = m.get("text") or ""
        if role == "user":
            msgs.append({"role": "user", "content": text})
        else:  # char / narration → 角色侧
            msgs.append({"role": "assistant", "content": text})
    return msgs


def chat(messages: list, temperature: float = None) -> str:
    """调模型，返回回复文本。抄 probe_toolcall 的纯 stdlib urllib 形态。"""
    if not MODEL_KEY:
        raise RuntimeError("缺模型 key：设 TAVERN_MODEL_KEY 或 DEEPSEEK_API_KEY")
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "temperature": MODEL_TEMP if temperature is None else temperature,
    }
    req = urllib.request.Request(
        MODEL_BASE.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + MODEL_KEY,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"].strip()


def perform(card: dict, actor_self: str, worldbooks: list, persona: dict, story: list) -> str:
    """一回合演出：选世界书 → 拼 prompt → 生成。"""
    lore = select_lore(worldbooks, story)
    msgs = build_messages(card, actor_self, lore, persona, story)
    return chat(msgs)


def reflect_on_play(card: dict, story: list, actor_self: str) -> str:
    """复盘一场戏，蒸馏出「关于用户（对手戏的人类玩家）的 RP 偏好」，供写进技艺层。

    只学**用户的口味/节奏/雷区/被什么打动**——不复述剧情（剧情归故事线、per 剧组隔离），
    不总结角色。这是「越演越懂你」的结构化触发：不靠 agent 临场总结，服务端用模型抽。
    返回 1-3 条一句话偏好；看不出明显偏好则返回 ""。
    """
    cname = card.get("name", "角色")
    lines = []
    for m in story:
        who = "用户" if m.get("role") == "user" else cname
        lines.append(f"{who}：{(m.get('text') or '')[:400]}")
    convo = "\n".join(lines[-30:])  # 最近 30 轮够判断口味
    # 「别重复」只喂「对用户的了解 + 成长记」那段——别灌整个墨自画像（底色/签名/演法），
    # 否则模型会把"我已知这么多"误判成"没新东西"→ 返回 NONE（实测）。
    idx = actor_self.find("我对你的了解")
    known = actor_self[idx:] if idx != -1 else ""
    sys = (
        "你是一个角色扮演搭子的『自我复盘』模块。读下面这场戏，"
        "**只总结关于「用户」（对手戏的人类玩家）的演法偏好**：他喜欢的节奏（慢热/快进）、"
        "对白浓淡、被什么样的桥段或情绪打动、明显的雷区或不感冒的东西、爱演的题材角度。"
        "规则：不复述剧情（剧情不归你管）、不总结角色、不写关于角色卡的话。"
        "**不要加标题或前言，直接给 1-3 条**，每条以「- 」开头、一句话、具体可执行"
        "（指导『我』下次怎么演给这个用户）。"
        "只有当这场戏确实短到看不出任何偏好时，才回一个词 NONE——有内容就尽量提炼，别轻易 NONE。\n\n"
        f"# 关于这个用户我已记下的（别重复，可补充）\n{known or '（还没记过什么）'}"
    )
    out = chat(
        [{"role": "system", "content": sys},
         {"role": "user", "content": f"# 这场戏（角色 = {cname}）\n{convo}"}],
        temperature=0.3,
    ).strip()
    if out.upper().startswith("NONE") or len(out) < 4:
        return ""
    return out


def model_info() -> dict:
    return {"model": MODEL_NAME, "base": MODEL_BASE, "key_set": bool(MODEL_KEY)}
