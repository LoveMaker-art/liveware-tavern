"""smoke — 对着运行中的 server 跑通 Loop A 核心闭环（纯 stdlib）。
跑：python3 tools/smoke.py [base_url]
"""
import base64
import json
import os
import sys
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8799").rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(os.path.dirname(HERE), "fixtures")


def post(ev):
    req = urllib.request.Request(BASE + "/api/event",
                                 data=json.dumps(ev).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return json.loads(r.read())


def main():
    print("1) health:", get("/api/health"))

    with open(os.path.join(FIX, "lin.png"), "rb") as f:
        png_b64 = base64.b64encode(f.read()).decode()
    r = post({"type": "import_card", "png_base64": png_b64})
    card = r["card"]
    print("2) import_card → ", card["id"], card["name"])

    with open(os.path.join(FIX, "worldbook_rainy_city.json"), encoding="utf-8") as f:
        wb = json.load(f)
    r = post({"type": "import_worldbook", "worldbook": wb})
    print("3) import_worldbook → ", r["worldbook"]["id"], "条目", len(r["worldbook"]["entries"]))

    post({"type": "set_persona", "name": "委托人", "description": "一个深夜冒雨上门、神色慌张的陌生人。"})

    r = post({"type": "create_production", "card_id": card["id"],
              "worldbook_ids": [wb["id"]], "name": "雨夜侦探事务所"})
    p = r["production"]
    print("4) create_production → ", p["id"], "| first_mes 开场:")
    print("   ", p["story"][0]["text"][:80], "...")

    print("\n5) send_message（你→角色，看 DeepSeek 入戏生成）:")
    user_line = "*我攥着湿透的衣角，声音压得很低。* 我要查一个人……但这事不能报警。你能接吗？"
    print("   [你]", user_line)
    r = post({"type": "send_message", "production_id": p["id"], "text": user_line})
    print("\n   [凛]", r["reply"])

    print("\n6) 再来一句，验故事线连续 + 世界书触发（提'雨/水'看会不会带出心结）:")
    user_line2 = "*我犹豫了一下。* 那个人……最后一次出现，是在码头。雨那么大。"
    print("   [你]", user_line2)
    r = post({"type": "send_message", "production_id": p["id"], "text": user_line2})
    print("\n   [凛]", r["reply"])

    print("\n7) regenerate 最后一条（备选回复）:")
    r = post({"type": "regenerate", "production_id": p["id"]})
    print("   [凛·alt]", r["message"]["text"][:120], "...")

    print("\n✅ Loop A 闭环跑通：导卡→世界书→建剧组→first_mes→入戏对话→故事线连续→重生成")


if __name__ == "__main__":
    main()
