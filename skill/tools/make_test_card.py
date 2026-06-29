"""make_test_card — 生成一张 spec 正确的 V2 角色卡 PNG（chara tEXt chunk）+ 一份世界书。

纯 stdlib（zlib+struct 手写 PNG），不依赖 PIL/外网。用来自测 card_import 的真格式路径。
跑：python3 tools/make_test_card.py  → 输出 fixtures/lin.png + fixtures/worldbook_rainy_city.json
"""
import base64
import binascii
import json
import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "fixtures")

CARD_V2 = {
    "spec": "chara_card_v2",
    "spec_version": "2.0",
    "data": {
        "name": "凛",
        "description": (
            "私家侦探，三十出头。常年一件皱风衣，烟不离手。话少，眼神能剥人一层皮。"
            "事务所开在雨夜不停的霓虹老街，招牌的灯管缺一截，闪。"
        ),
        "personality": "冷面、毒舌但靠谱；嘴上嫌弃心里上心；讨厌废话和谎话，最恨被人当傻子。",
        "scenario": "深夜，委托人冒雨敲开「凛侦探事务所」的门。桌上一盏台灯，墙角钟在走。",
        "first_mes": (
            "*门被推开时带进一阵冷雨。她没抬头，指间的烟转了半圈。*\n"
            "「……坐。」*终于看你一眼，目光像称重，*「带钱了，还是带麻烦了？」"
        ),
        "mes_example": (
            "<START>\n{{user}}: 我想委托你查一个人。\n"
            "{{char}}: *她把烟摁灭，椅子往后一靠。*「名字、最后一次见面、还有——你为什么不敢报警。三个都说，少一个我不接。」"
        ),
        "alternate_greetings": [
            "*事务所的灯还亮着。她正擦一把旧左轮，听见脚步也没停手。*「门没锁。要么进来说话，要么把雨关在外面。」"
        ],
        "system_prompt": "",
        "tags": ["侦探", "黑色", "雨夜", "悬疑"],
        "creator": "tavern-test",
        "character_version": "1.0",
        "extensions": {"tavern_test/note": "合成测试卡，验证 V2 导入路径"},
    },
}

WORLDBOOK = {
    "id": "wb_rainy_city",
    "name": "雨夜都市",
    "entries": [
        {"keys": ["水", "雨", "下雨", "淋湿"], "content": "凛怕水里翻出来的旧案——三年前的码头浮尸案是她的心结，一沾水气就烦躁。", "enabled": True, "insertion_order": 10, "constant": False, "selective": False, "secondary_keys": [], "position": "before_char", "source": "import"},
        {"keys": ["老K", "线人"], "content": "老K：街角报刊亭的瘸腿老头，凛的线人，消息灵但要价高，爱赊烟。", "enabled": True, "insertion_order": 20, "constant": False, "selective": False, "secondary_keys": [], "position": "before_char", "source": "import"},
        {"keys": [], "content": "世界基调：永远在下雨的赛博霓虹旧城，警察靠不住，真相要自己挖。", "enabled": True, "insertion_order": 1, "constant": True, "selective": False, "secondary_keys": [], "position": "before_char", "source": "import"},
    ],
}


def _chunk(ctype: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + ctype
        + data
        + struct.pack(">I", binascii.crc32(ctype + data) & 0xFFFFFFFF)
    )


def _make_png(card: dict, w: int = 96, h: int = 96) -> bytes:
    # 一张纯色(深蓝夜)图，足够当"装饰像素"
    row = b"\x00" + bytes([18, 22, 33]) * w  # filter 0 + RGB
    raw = row * h
    idat = zlib.compress(raw, 9)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit RGB
    chara = base64.b64encode(
        json.dumps(card, ensure_ascii=False).encode("utf-8")
    )  # tEXt 文本是 base64(JSON)
    text_data = b"chara\x00" + chara
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"tEXt", text_data)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )


def main():
    os.makedirs(OUT, exist_ok=True)
    png_path = os.path.join(OUT, "lin.png")
    wb_path = os.path.join(OUT, "worldbook_rainy_city.json")
    with open(png_path, "wb") as f:
        f.write(_make_png(CARD_V2))
    with open(wb_path, "w", encoding="utf-8") as f:
        json.dump(WORLDBOOK, f, ensure_ascii=False, indent=2)
    print("wrote", png_path)
    print("wrote", wb_path)


if __name__ == "__main__":
    main()
