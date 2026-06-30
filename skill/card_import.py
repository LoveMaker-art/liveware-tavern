"""card_import — 把一张酒馆角色卡(V2/V3 PNG)解析成 tavern 内部 card JSON。

纯 stdlib：读 PNG 的 tEXt chunk，V2 关键字 `chara`、V3 关键字 `ccv3`，chunk 数据是
`keyword\\0base64(json)`，base64 解出来是角色卡 JSON。优先 V3(ccv3)，回落 V2(chara)。

铁律：**不丢未知键**(V2 spec「Character editors MUST NOT destroy unknown key-value pairs」)，
整份 data + 顶层 extensions 原样带走。
"""
import base64
import json
import struct
import hashlib

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _iter_png_chunks(raw: bytes):
    if raw[:8] != PNG_SIG:
        raise ValueError("不是 PNG（角色卡必须是 PNG，像素是装饰、元数据才是载荷）")
    i = 8
    n = len(raw)
    while i + 8 <= n:
        (length,) = struct.unpack(">I", raw[i : i + 4])
        ctype = raw[i + 4 : i + 8]
        data = raw[i + 8 : i + 8 + length]
        yield ctype, data
        i += 8 + length + 4  # length + type + data + crc
        if ctype == b"IEND":
            break


def _read_text_chunks(raw: bytes) -> dict:
    """返回 {keyword: text}，覆盖 tEXt(未压缩) 与 iTXt(可能压缩)。"""
    out = {}
    for ctype, data in _iter_png_chunks(raw):
        if ctype == b"tEXt":
            kw, _, txt = data.partition(b"\x00")
            out[kw.decode("latin-1")] = txt.decode("latin-1")
        elif ctype == b"iTXt":
            # keyword\0 compflag\0 compmethod\0 langtag\0 transkw\0 text
            try:
                kw, rest = data.split(b"\x00", 1)
                comp_flag = rest[0]
                rest = rest[1:]
                # comp_method(1) + langtag\0 + transkw\0
                rest = rest[1:]
                _lang, rest = rest.split(b"\x00", 1)
                _trans, rest = rest.split(b"\x00", 1)
                if comp_flag == 1:
                    import zlib

                    text = zlib.decompress(rest).decode("utf-8", "replace")
                else:
                    text = rest.decode("utf-8", "replace")
                out.setdefault(kw.decode("latin-1"), text)
            except Exception:
                continue
    return out


def _decode_card_payload(text_chunks: dict) -> dict:
    for key in ("ccv3", "chara"):  # V3 优先
        if key in text_chunks:
            blob = text_chunks[key].strip()
            # tEXt 按 latin-1 读进来（字节安全的 1:1 映射）、iTXt 已是 utf-8 unicode。
            # 先还原成原始字节，再判断 base64 还是明文 JSON——否则明文 UTF-8 卡会被
            # 当 latin-1 直接 json.loads，中文全乱码（「鹿念念」bug，2026-06-29）。
            try:
                raw = blob.encode("latin-1")   # tEXt 路径：还原原始字节
            except UnicodeEncodeError:
                raw = blob.encode("utf-8")     # iTXt 路径：已是 unicode
            try:
                raw = base64.b64decode(raw, validate=True)  # 绝大多数卡 base64(json)
            except Exception:
                pass  # 个别卡直接塞明文 JSON（raw 已是原始 UTF-8 字节）
            return json.loads(raw.decode("utf-8"))
    raise ValueError("PNG 里没有 chara/ccv3 角色卡数据")


_STR_FIELDS = (
    "name", "description", "personality", "scenario",
    "first_mes", "mes_example", "system_prompt", "post_history_instructions",
    "creator", "character_version", "nickname",
)


def normalize_card(card_obj: dict) -> dict:
    """V1/V2/V3 → tavern 内部统一形态。保留 extensions + 原始 data。"""
    data = card_obj.get("data") if isinstance(card_obj.get("data"), dict) else card_obj
    out = {"spec": card_obj.get("spec", "chara_card_v2")}
    for f in _STR_FIELDS:
        out[f] = data.get(f, "") or ""
    out["alternate_greetings"] = data.get("alternate_greetings") or []
    out["tags"] = data.get("tags") or []
    # 出处标记:import_card(PNG/Chub)→「chub」、import_card_json(原创/粘贴)→「agent」,
    # 由 server 的事件入口按导入渠道打(normalize_card 路径无关、分不清渠道)。卡 JSON 自带
    # 的 source 先保留(不丢未知键),server 再按渠道覆盖。显示优先 creator,无 creator 才看 source。
    out["source"] = data.get("source") or ""
    # 世界书可能内嵌在卡里(character_book)——带走，建剧组时可转成独立 worldbook
    if isinstance(data.get("character_book"), dict):
        out["character_book"] = data["character_book"]
    out["extensions"] = data.get("extensions") or {}  # 铁律：不丢未知键
    cid = "card_" + hashlib.sha1(
        (out["name"] + "|" + out["description"][:200]).encode("utf-8")
    ).hexdigest()[:12]
    out["id"] = cid
    return out


def import_card_bytes(png_bytes: bytes) -> dict:
    return normalize_card(_decode_card_payload(_read_text_chunks(png_bytes)))


def import_card_b64(png_b64: str) -> dict:
    return import_card_bytes(base64.b64decode(png_b64))


if __name__ == "__main__":
    import sys

    with open(sys.argv[1], "rb") as f:
        c = import_card_bytes(f.read())
    print(json.dumps(c, ensure_ascii=False, indent=2))
