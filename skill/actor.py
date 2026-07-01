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
# 反复读/slop 的服务端兜底(无 UI——采样参数按设计 canon 收进自动档,不暴露旋钮)。
MODEL_FREQ_PENALTY = float(os.environ.get("TAVERN_FREQ_PENALTY", "0.3"))
MODEL_PRES_PENALTY = float(os.environ.get("TAVERN_PRES_PENALTY", "0.0"))
# 上下文预算(字符):长局只喂最新尾巴+开场,别每回合发整条 story 撞模型上限。
CTX_BUDGET_CHARS = int(os.environ.get("TAVERN_CTX_CHARS", "24000"))
# 世界书扫描深度(往回看几条命中关键词)。
LORE_LOOKBACK = int(os.environ.get("TAVERN_LORE_LOOKBACK", "6"))


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


def select_lore(worldbooks: list, story: list, lookback: int = None) -> list:
    """选相关世界书条目：constant(蓝灯)恒入 + 关键词命中最近 N 条的入；
    selective(绿灯)还需命中一个二级关键词(secondary_keys)才入——避免过度触发。
    MVP 的「agent 选」近似——不暴露递归/扫描深度这些机制给用户(扫描深度走 env)。"""
    lookback = LORE_LOOKBACK if lookback is None else lookback
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
            primary = e.get("constant") or any(
                k and k in recent for k in (e.get("keys") or [])
            )
            if not primary:
                continue
            # selective(绿灯):一级命中后还要求一个二级关键词同现,收窄触发。
            if e.get("selective") and e.get("secondary_keys"):
                if not any(k and k in recent for k in e["secondary_keys"]):
                    continue
            picked.append(e)
            seen.add(key)
    picked.sort(key=lambda e: e.get("insertion_order", 100))
    return picked


def _fit_history(story: list, budget_chars: int) -> list:
    """上下文预算:始终保留开场(story[0],first_mes 定调) + 预算内的最新尾巴。
    长局别每回合发整条 story——会撞模型上下文上限(报错/被静默截断)+ 成本延迟爆炸。"""
    if budget_chars <= 0 or len(story) <= 1:
        return story
    opening = story[:1]
    total = len(opening[0].get("text") or "")
    kept = []
    for m in reversed(story[1:]):
        t = len(m.get("text") or "")
        if total + t > budget_chars and kept:
            break
        kept.append(m)
        total += t
    kept.reverse()
    return opening + kept


def _prompt_self(actor_self: str) -> str:
    """注入生成的技艺层 = 底色 + 我对你的了解 + 签名，**不含成长记**。
    成长记是 append-only 的生涯流水账（演员卡「生涯年表」的资产），塞进每次 prompt 只会
    稀释 + 吃预算（A/B 实测；Q_B 注入瘦身）——它的家在演员卡，不在生成上下文。"""
    return actor_self.split("# 成长记", 1)[0].rstrip()


def build_messages(card: dict, actor_self: str, lore: list, persona: dict, story: list,
                   note: str = "") -> list:
    """组成 chat-completion 消息序列。系统块 = 演员 + 剧本 + 世界 + 人设 + 演出纪律；
    世界书分两档放置(背景 vs 贴近生成点),作者注释/贴尾指令注在最靠近生成点处。"""
    actor_self = _prompt_self(actor_self)  # 只注 底色+口味+签名,剥掉成长记(Q_B)
    # 世界书分档:position=before_char 当背景进系统块顶;其余注在故事之后、贴近生成点,
    # 才真正能 steer 当前这一回合(ST 的核心:lore 离生成点近才管用,不是堆在 system 顶)。
    lore_top = [e for e in lore if (e.get("position") or "") == "before_char"]
    lore_near = [e for e in lore if (e.get("position") or "") != "before_char"]
    lore_top_txt = "\n".join("- " + (e.get("content") or "") for e in lore_top)
    persona_txt = ""
    if persona:
        persona_txt = f"\n\n## 对手戏（你的搭档「{persona.get('name','我')}」）\n{persona.get('description','')}"
    sysprompt_block = ("### 角色设定提示\n" + card["system_prompt"]) if card.get("system_prompt") else ""
    # 示例对白(few-shot 风格锚):卡作者给的最强语气/节奏样本。此前 card_import 解析了却没注入。
    example_block = ("\n\n## 示例对白（仿其语气、句式、节奏，别照抄内容）\n" + card["mes_example"]) \
        if card.get("mes_example") else ""
    sys = f"""{actor_self}

——————————

你现在出演这个角色，全程**入戏不出戏**（除非搭档明显在跟你这个"演员"说话）。

## 你出演的角色：{card.get('name','')}
{card.get('description','')}

### 性格
{card.get('personality','')}

### 场景
{card.get('scenario','')}
{sysprompt_block}{example_block}

## 世界设定（背景，只在自然时机体现，别报菜名）
{lore_top_txt or '（无）'}{persona_txt}

## 演出纪律
- 用中文。动作/神态/环境用第三人称叙述，对白用「」。
- 给角色一个身体：手里在做什么、呼吸、环境的声音光线。
- 情绪藏细节，不直接喊。一回合别太长，留白给对方接。
- 推动剧情，别被动等喂；但尊重搭档的选择，不替对方做决定。
"""
    msgs = [{"role": "system", "content": sys}]
    # 上下文预算:长局只喂开场 + 最新尾巴(系统块/贴近世界书/作者注释/贴尾指令始终保留)。
    for m in _fit_history(story, CTX_BUDGET_CHARS):
        role = m.get("role")
        text = m.get("text") or ""
        if role == "user":
            msgs.append({"role": "user", "content": text})
        else:  # char / narration → 角色侧
            msgs.append({"role": "assistant", "content": text})
    # 此刻相关的世界书:注在故事之后、贴近生成点(比堆在 system 顶更能 steer 当前回合)。
    if lore_near:
        near_txt = "\n".join("- " + (e.get("content") or "") for e in lore_near)
        msgs.append({"role": "system",
                     "content": "### 此刻相关的世界设定（自然融入，别罗列）\n" + near_txt})
    # 作者注释(结构化的临场语气/格式杠杆,agent 用 set_note 设):贴近生成点,不靠模型"记着"。
    # 这是「结构性 > 软性」的落点——不暴露 UI 旋钮(设计 canon),由对话/agent 设、注入这里。
    if note:
        msgs.append({"role": "system", "content": "〔导演提示，本回合照此调整〕" + note})
    # 贴尾指令(post_history_instructions):最靠近生成点——格式/不脱戏的最高杠杆提醒。
    # ST 的「post-history」机制;此前解析了却没注入。
    post = card.get("post_history_instructions")
    if post:
        msgs.append({"role": "system",
                     "content": "### 贴尾指令（最高优先，与上文冲突时以此为准）\n" + post})
    return msgs


def _payload(messages: list, temperature: float, stream: bool) -> dict:
    return {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": stream,
        "temperature": MODEL_TEMP if temperature is None else temperature,
        "frequency_penalty": MODEL_FREQ_PENALTY,  # 反复读兜底(无 UI,设计 canon)
        "presence_penalty": MODEL_PRES_PENALTY,
    }


def _request(payload: dict) -> urllib.request.Request:
    if not MODEL_KEY:
        raise RuntimeError("缺模型 key：设 TAVERN_MODEL_KEY 或 DEEPSEEK_API_KEY")
    return urllib.request.Request(
        MODEL_BASE.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + MODEL_KEY,
        },
        method="POST",
    )


def chat(messages: list, temperature: float = None) -> str:
    """调模型，返回回复文本（非流式）。抄 probe_toolcall 的纯 stdlib urllib 形态。"""
    with urllib.request.urlopen(_request(_payload(messages, temperature, False)), timeout=90) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"].strip()


def chat_stream(messages: list, temperature: float = None):
    """调模型，逐 token yield 文本增量（SSE，OpenAI-compatible）。
    用于控制台流式渲染——同模型下"逐字流"比干等占位条体感强一档。"""
    with urllib.request.urlopen(_request(_payload(messages, temperature, True)), timeout=120) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"].get("content")
            except Exception:
                continue
            if delta:
                yield delta


def perform(card: dict, actor_self: str, worldbooks: list, persona: dict, story: list,
            note: str = "") -> str:
    """一回合演出：选世界书 → 拼 prompt → 生成。"""
    lore = select_lore(worldbooks, story)
    msgs = build_messages(card, actor_self, lore, persona, story, note)
    return chat(msgs)


def perform_stream(card: dict, actor_self: str, worldbooks: list, persona: dict, story: list,
                   note: str = ""):
    """一回合演出（流式）：选世界书 → 拼 prompt → 逐 token yield。"""
    lore = select_lore(worldbooks, story)
    msgs = build_messages(card, actor_self, lore, persona, story, note)
    yield from chat_stream(msgs)


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


def merge_knows(existing: list, addition: str) -> list:
    """把新学到的（addition）并进「对用户的了解」现有清单，产出合并、去重、有界的新清单。

    「越演越懂你」的 consolidation 引擎（Q_B）：不是尾部堆流水账，而是维护一份**活的、精炼**
    的偏好档——新信息更具体就替换旧的笼统条、矛盾以新为准、控制在 ~12 条。这份档注入每场生成，
    也展示在演员卡「我对你的了解」。返回 list[str]；addition 空则原样返回。
    """
    if not (addition or "").strip():
        return list(existing)
    cur = "\n".join("- " + e for e in existing) if existing else "（还没记过什么）"
    sys = (
        "你在维护一个角色扮演搭子『对用户的了解』档——一份简短、精炼、不重复的偏好清单，"
        "指导它下次怎么演给这个用户。给你【现有清单】和【新学到的】，产出【合并后的清单】：\n"
        "- 合并同类、去重；新信息更具体就替换旧的笼统条；矛盾以新的为准。\n"
        "- **一条只讲一个维度**（节奏 / 浓淡 / 雷区 / 幽默 / 题材 / 演法…）；"
        "两个不同维度**分成两条**，别为了省行数塞进一行。\n"
        "- 每条一句话、具体可执行。\n"
        "- 控制在 12 条以内，越精越好；别注水、别加标题或解释。\n"
        "- 只输出清单，每条以「- 」开头。"
    )
    out = chat(
        [{"role": "system", "content": sys},
         {"role": "user", "content": f"【现有清单】\n{cur}\n\n【新学到的】\n{addition}"}],
        temperature=0.3,
    )
    items = [ln.strip()[2:].strip() for ln in out.splitlines() if ln.strip().startswith("- ")]
    items = [i for i in items if i]
    return items[:12] if items else list(existing)


def model_info() -> dict:
    return {"model": MODEL_NAME, "base": MODEL_BASE, "key_set": bool(MODEL_KEY)}
