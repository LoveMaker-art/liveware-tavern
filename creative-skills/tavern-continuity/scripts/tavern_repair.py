#!/usr/bin/env python3
"""Ruotang Tavern state repair tool.

Plans and applies narrow repairs to production-owned story_state and runtime_cast.
"""
import argparse
import contextlib
import importlib
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request


CONSOLE = os.environ.get("TAVERN_CONSOLE", "http://127.0.0.1:8799").rstrip("/")
UA = "tavern-repair/1.0"


def die(msg):
    print("错误：" + str(msg), file=sys.stderr)
    sys.exit(1)


def http_json(path, timeout=30):
    url = CONSOLE + path
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        die(f"请求失败 {url}: {e}")


def get_productions():
    d = http_json("/api/productions", timeout=20)
    return d if isinstance(d, list) else d.get("productions", [])


def resolve_production(q):
    prods = get_productions()
    matches = [p for p in prods if p.get("id") == q or q in (p.get("name") or "")]
    if not matches:
        die(f"没找到世界「{q}」——先 list/diagnose 看有哪些。")
    return matches[0]


def get_production_detail(pid):
    d = http_json("/api/production?production_id=" + urllib.parse.quote(pid), timeout=25)
    return d.get("production") if isinstance(d.get("production"), dict) else d


def state_dir():
    return os.environ.get("TAVERN_STATE_DIR", "/opt/data/tavern-state")


def production_state_path(pid):
    return os.path.join(state_dir(), "productions", pid + ".json")


def load_production_state(pid):
    path = production_state_path(pid)
    if not os.path.exists(path):
        die(f"找不到世界状态文件：{path}")
    with open(path, encoding="utf-8") as f:
        return path, json.load(f)


def write_production_state(path, obj, label):
    backup = path + f".bak.{label}.{int(time.time())}"
    with open(backup, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return backup


def runtime_actor_chat(messages, temperature=0.1):
    runtime = "/opt/data/apps/tavern-runtime"
    if runtime not in sys.path:
        sys.path.insert(0, runtime)
    actor = importlib.import_module("actor")
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return actor.chat(messages, temperature=temperature)


def json_from_model_text(text):
    raw = (text or "").strip()
    if not raw:
        die("模型没有返回修复计划。")
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    die("修复计划不是可解析 JSON：\n" + raw[:800])


def short(text, n=160):
    text = " ".join(str(text or "").split())
    return text[:n] + ("..." if len(text) > n else "")


def recent_story(p, limit=24):
    return [
        {"role": m.get("role"), "text": (m.get("text") or "")[:900]}
        for m in (p.get("story") or [])[-limit:]
    ]


def story_fix_plan(p, request):
    state = p.get("story_state") or {}
    cast = p.get("runtime_cast") or {}
    system = (
        "你是若棠的酒馆剧情账本修复器。根据用户的修复请求、当前 story_state、runtime_cast 摘要和最近剧情，"
        "只规划对 story_state 的最小修复。不要改历史对话，不要续写剧情，不要把用户偏好写进剧情状态。"
        "只输出严格 JSON 对象，字段：summary, confidence, risks, operations。"
        "operations 是数组，每项字段：op(add|update|remove), section(scene|facts|objects|open_threads|secrets|timeline|style_notes), "
        "match, field, value, reason。"
        "scene 是对象，可用 field 指定子字段；facts/objects/open_threads/secrets/timeline/style_notes 是数组。"
        "如果证据不足，operations 为空，并在 risks 说明需要用户确认。"
    )
    user = json.dumps({
        "world": {"id": p.get("id"), "name": p.get("name")},
        "request": request,
        "story_state": state,
        "runtime_cast_summary": {
            "revision": cast.get("revision"),
            "characters": [
                {
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "persistent_status": c.get("persistent_status") or {},
                }
                for c in (cast.get("characters") or [])[:20]
            ],
            "relationships": (cast.get("relationships") or [])[:30],
            "user_status": cast.get("user_status") or {},
        },
        "recent_story": recent_story(p),
    }, ensure_ascii=False)
    plan = json_from_model_text(runtime_actor_chat([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], temperature=0.05))
    if not isinstance(plan, dict):
        die("修复计划格式错误：顶层不是对象。")
    plan.setdefault("operations", [])
    return plan


def cast_fix_plan(p, request):
    cast = p.get("runtime_cast") or {}
    cards = p.get("cards") or []
    system = (
        "你是若棠的酒馆角色状态修复器。根据用户请求、runtime_cast、角色卡摘要和最近剧情，"
        "只规划对 runtime_cast 的最小修复。不要改 origin_profile，不要改角色库模板，不要改历史对话。"
        "只输出严格 JSON 对象，字段：summary, confidence, risks, operations。"
        "operations 是数组，每项字段：op(add|update|remove), target(character|relationship|user_profile|user_status), "
        "character, match, field, value, reason。"
        "character 可填角色名或 id。character 的 field 只允许 profile.* 或 persistent_status.*；"
        "user_profile/user_status 的 field 是其子路径；relationship 可按 match 查找或 add 新关系对象。"
        "如果证据不足，operations 为空，并在 risks 说明需要用户确认。"
    )
    user = json.dumps({
        "world": {"id": p.get("id"), "name": p.get("name")},
        "request": request,
        "runtime_cast": cast,
        "cards_summary": [
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "origin_profile": c.get("origin_profile") or {},
                "profile": c.get("profile") or {},
                "persistent_status": c.get("persistent_status") or {},
            }
            for c in cards[:20]
        ],
        "recent_story": recent_story(p),
    }, ensure_ascii=False)
    plan = json_from_model_text(runtime_actor_chat([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], temperature=0.05))
    if not isinstance(plan, dict):
        die("修复计划格式错误：顶层不是对象。")
    plan.setdefault("operations", [])
    return plan


def print_fix_plan(title, p, plan):
    print(f"=== {title}：{p.get('name')}（{p.get('id')}）===")
    print("摘要：" + str(plan.get("summary") or "无"))
    print("置信度：" + str(plan.get("confidence") or "未给出"))
    risks = plan.get("risks") or []
    if isinstance(risks, str):
        risks = [risks]
    if risks:
        print("\n风险/需要确认：")
        for r in risks:
            print("- " + str(r))
    ops = plan.get("operations") or []
    if not ops:
        print("\n没有可安全自动执行的修复动作。")
        return
    print("\n计划动作：")
    for i, op in enumerate(ops, 1):
        print(f"[{i}] {op.get('op')} {op.get('section') or op.get('target')} "
              f"{op.get('character') or ''} {op.get('field') or ''}")
        if op.get("match"):
            print("    match: " + short(op.get("match"), 220))
        if "value" in op:
            print("    value: " + short(json.dumps(op.get("value"), ensure_ascii=False), 260))
        if op.get("reason"):
            print("    reason: " + str(op.get("reason")))
    print("\n未写入。确认后可运行同一命令加 --apply --confirm。")


def match_index(items, match):
    if match is None or match == "":
        return None
    needle = str(match)
    for i, item in enumerate(items):
        if needle in json.dumps(item, ensure_ascii=False):
            return i
    low = needle.lower()
    for i, item in enumerate(items):
        if low in json.dumps(item, ensure_ascii=False).lower():
            return i
    return None


def set_path(obj, path, value):
    parts = [p for p in str(path or "").split(".") if p]
    if not parts:
        return False
    cur = obj
    for part in parts[:-1]:
        if not isinstance(cur, dict):
            return False
        if not isinstance(cur.get(part), dict):
            cur[part] = {}
        cur = cur[part]
    if not isinstance(cur, dict):
        return False
    cur[parts[-1]] = value
    return True


def find_character(cast, ref):
    chars = cast.get("characters") or []
    q = str(ref or "").strip()
    if not q:
        return None
    for c in chars:
        if q in (c.get("id"), c.get("source_card_id")):
            return c
    ql = q.lower()
    for c in chars:
        if ql in (c.get("name") or "").lower() or ql in (c.get("nickname") or "").lower():
            return c
    return None


def apply_story_fix(obj, plan):
    state = obj.setdefault("story_state", {})
    changed = 0
    allowed = {"scene", "facts", "objects", "open_threads", "secrets", "timeline", "style_notes"}
    for op in plan.get("operations") or []:
        section = str(op.get("section") or "").strip()
        action = str(op.get("op") or "").strip()
        if section not in allowed:
            print(f"跳过未知 section：{section}")
            continue
        if section == "scene":
            scene = state.setdefault("scene", {})
            if not isinstance(scene, dict):
                scene = {}
                state["scene"] = scene
            if action in ("update", "add"):
                field = op.get("field")
                if field:
                    if set_path(scene, field, op.get("value")):
                        changed += 1
                elif isinstance(op.get("value"), dict):
                    scene.update(op.get("value"))
                    changed += 1
            elif action == "remove" and op.get("field"):
                if op["field"] in scene:
                    scene.pop(op["field"], None)
                    changed += 1
            continue
        arr = state.setdefault(section, [])
        if not isinstance(arr, list):
            arr = []
            state[section] = arr
        if action == "add":
            arr.append(op.get("value"))
            changed += 1
        elif action == "update":
            idx = match_index(arr, op.get("match"))
            if idx is None:
                arr.append(op.get("value"))
            else:
                arr[idx] = op.get("value")
            changed += 1
        elif action == "remove":
            idx = match_index(arr, op.get("match"))
            if idx is not None:
                arr.pop(idx)
                changed += 1
    if changed:
        state["updated_at"] = int(time.time())
    return changed


def apply_cast_fix(obj, plan):
    cast = obj.setdefault("runtime_cast", {})
    changed = 0
    for op in plan.get("operations") or []:
        target = str(op.get("target") or "").strip()
        action = str(op.get("op") or "").strip()
        if target == "character":
            c = find_character(cast, op.get("character"))
            if not c:
                print(f"跳过：找不到角色 {op.get('character')}")
                continue
            field = str(op.get("field") or "")
            if not (field.startswith("profile.") or field.startswith("persistent_status.")):
                print(f"跳过不允许的角色字段：{field}")
                continue
            if action in ("add", "update") and set_path(c, field, op.get("value")):
                c["updated_at"] = int(time.time())
                c["profile_updated_turn" if field.startswith("profile.") else "status_updated_turn"] = cast.get("applied_turn")
                changed += 1
        elif target in ("user_profile", "user_status"):
            root = cast.setdefault(target, {})
            if action in ("add", "update") and set_path(root, op.get("field"), op.get("value")):
                cast[target + "_updated_turn"] = cast.get("applied_turn")
                changed += 1
        elif target == "relationship":
            rels = cast.setdefault("relationships", [])
            if action == "add":
                rels.append(op.get("value"))
                changed += 1
            elif action == "update":
                idx = match_index(rels, op.get("match"))
                if idx is None:
                    rels.append(op.get("value"))
                else:
                    rels[idx] = op.get("value")
                changed += 1
            elif action == "remove":
                idx = match_index(rels, op.get("match"))
                if idx is not None:
                    rels.pop(idx)
                    changed += 1
        else:
            print(f"跳过未知 target：{target}")
    if changed:
        cast["revision"] = int(cast.get("revision") or 0) + 1
        cast["updated_at"] = int(time.time())
    return changed


def cmd_story_fix(a):
    if a.apply and not a.confirm:
        die("--apply 会修改 story_state；请加 --confirm。")
    p = get_production_detail(resolve_production(a.world)["id"])
    request = (a.request or "").strip()
    if not request:
        die("请说明要修复的剧情状态，例如：\"钥匙现在在我手里，不在贝塔手里\"。")
    plan = story_fix_plan(p, request)
    if not a.apply:
        print_fix_plan("剧情状态修复计划", p, plan)
        return
    path, obj = load_production_state(p["id"])
    changed = apply_story_fix(obj, plan)
    if not changed:
        print("没有执行任何写入；计划没有安全动作或无法匹配。")
        return
    backup = write_production_state(path, obj, "story-fix")
    print(f"✅ 已修复 story_state：{changed} 处")
    print(f"备份：{backup}")
    print("建议下一步：diagnose <世界>，必要时 story-fix --plan 再核对。")


def cmd_cast_fix(a):
    if a.apply and not a.confirm:
        die("--apply 会修改 runtime_cast；请加 --confirm。")
    p = get_production_detail(resolve_production(a.world)["id"])
    request = (a.request or "").strip()
    if not request:
        die("请说明要修复的角色状态，例如：\"阿尔法的伤势已经恢复\" 或 \"我和贝塔是临时同盟\"。")
    plan = cast_fix_plan(p, request)
    if not a.apply:
        print_fix_plan("角色状态修复计划", p, plan)
        return
    path, obj = load_production_state(p["id"])
    changed = apply_cast_fix(obj, plan)
    if not changed:
        print("没有执行任何写入；计划没有安全动作或无法匹配。")
        return
    backup = write_production_state(path, obj, "cast-fix")
    print(f"✅ 已修复 runtime_cast：{changed} 处")
    print(f"备份：{backup}")
    print("建议下一步：diagnose <世界>，必要时 cast-fix --plan 再核对。")


def main():
    ap = argparse.ArgumentParser(prog="tavern_repair", description="若棠酒馆状态修复工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("story-fix", help="修复剧情账本 story_state；默认只规划，--apply --confirm 后写入")
    s.add_argument("world", help="世界 id 或名字片段")
    s.add_argument("request", help="自然语言修复请求，如：钥匙现在在我手里，不在贝塔手里")
    s.add_argument("--plan", action="store_true", default=True, help="只生成修复计划，不修改数据")
    s.add_argument("--apply", action="store_true", help="按计划修改 story_state")
    s.add_argument("--confirm", action="store_true", help="确认写入 production 状态文件")
    s.set_defaults(fn=cmd_story_fix)

    s = sub.add_parser("cast-fix", help="修复角色/用户状态 runtime_cast；默认只规划，--apply --confirm 后写入")
    s.add_argument("world", help="世界 id 或名字片段")
    s.add_argument("request", help="自然语言修复请求，如：阿尔法的伤势已经恢复")
    s.add_argument("--plan", action="store_true", default=True, help="只生成修复计划，不修改数据")
    s.add_argument("--apply", action="store_true", help="按计划修改 runtime_cast")
    s.add_argument("--confirm", action="store_true", help="确认写入 production 状态文件")
    s.set_defaults(fn=cmd_cast_fix)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
