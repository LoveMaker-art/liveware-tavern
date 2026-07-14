"""server — 酒馆演员运行时的同源 server（stdlib http.server，仿 digest）。

serve 控制台静态页(web/) + /api/*（同源，浏览器同源策略天然满足，模型 creds 留 server 端）。
状态全落 /opt/data/tavern-state 下 JSON 文件，永不写能力服务器/member-backend。

跑：TAVERN_MODEL_KEY=... python3 server.py [--port 8799]
"""
import base64
import binascii
import json
import hashlib
import os
import secrets
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import yaml
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import actor  # noqa: E402
import card_import  # noqa: E402

STATE = os.environ.get("TAVERN_STATE_DIR", "/opt/data/tavern-state")
READER = os.path.join(HERE, "web")
SEED_ACTOR = os.path.join(HERE, "actor_self.md")
for sub in ("cards", "worldbooks", "productions"):
    os.makedirs(os.path.join(STATE, sub), exist_ok=True)

CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
                 ".png": "image/png", ".svg": "image/svg+xml"}

TTS_BASE = str(os.environ.get("TAVERN_TTS_BASE") or actor.MODEL_BASE or "").strip().rstrip("/")
TTS_MODEL = "clawling/qwen-tts"
TTS_MODEL_NAME = "Qwen TTS"
TTS_DEFAULT_VOICE = os.environ.get("TAVERN_TTS_VOICE", "vivian").strip().lower()
TTS_TIMEOUT = max(30, int(os.environ.get("TAVERN_TTS_TIMEOUT", "240")))
TTS_MAX_CHARS = min(4096, max(1, int(os.environ.get("TAVERN_TTS_MAX_CHARS", "4096"))))
TTS_CACHE_LIMIT = max(1, int(os.environ.get("TAVERN_TTS_CACHE_LIMIT", "32")))
TTS_CONFIG_PATH = os.path.join(STATE, "tts_config.json")
TTS_REFERENCE_DIR = os.path.join(STATE, "tts-references")
TTS_REFERENCE_MAX_BYTES = 10 * 1024 * 1024
TTS_VOICE_CACHE_TTL = 300
TTS_DEFAULT_SPEED = 0.9
TTS_MAX_CLONES = 20
TTS_PREVIEW_TEXT = "欢迎来到故事的世界里"
TTS_FALLBACK_VOICES = (
    {"id": "vivian", "name": "Vivian", "model": TTS_MODEL, "description": "明亮、略带锐气的年轻女声。", "language": "chinese"},
    {"id": "serena", "name": "Serena", "model": TTS_MODEL, "description": "温暖柔和的年轻女声。", "language": "chinese"},
    {"id": "uncle_fu", "name": "Uncle_Fu", "model": TTS_MODEL, "description": "音色低沉醇厚的成熟男声。", "language": "chinese"},
    {"id": "dylan", "name": "Dylan", "model": TTS_MODEL, "description": "清晰自然的北京青年男声。", "language": "chinese"},
    {"id": "eric", "name": "Eric", "model": TTS_MODEL, "description": "活泼、略带沙哑明亮感的成都男声。", "language": "chinese"},
    {"id": "ryan", "name": "Ryan", "model": TTS_MODEL, "description": "富有节奏感的动态男声。", "language": "english"},
    {"id": "aiden", "name": "Aiden", "model": TTS_MODEL, "description": "清晰中频的阳光美式男声。", "language": "english"},
    {"id": "ono_anna", "name": "Ono_Anna", "model": TTS_MODEL, "description": "轻快灵活的俏皮日语女声。", "language": "japanese"},
    {"id": "sohee", "name": "Sohee", "model": TTS_MODEL, "description": "富含情感的温暖韩语女声。", "language": "korean"},
)
os.makedirs(TTS_REFERENCE_DIR, exist_ok=True)
_tts_voice_cache = {"at": 0.0, "voices": list(TTS_FALLBACK_VOICES)}
_tts_voice_cache_lock = threading.Lock()
_tts_cache = {}
_tts_cache_order = []
_tts_cache_lock = threading.Lock()

DESTRUCTIVE_CONFIRM_TTL = 600
_destructive_confirmations = {}
_destructive_confirmation_lock = threading.Lock()


def _prepare_destructive_confirmation(action, resource_id):
    now = time.time()
    token = secrets.token_urlsafe(8)
    with _destructive_confirmation_lock:
        expired = [key for key, item in _destructive_confirmations.items()
                   if item["expires_at"] <= now]
        for key in expired:
            _destructive_confirmations.pop(key, None)
        _destructive_confirmations[token] = {
            "action": action,
            "resource_id": resource_id,
            "expires_at": now + DESTRUCTIVE_CONFIRM_TTL,
        }
    return token


def _consume_destructive_confirmation(token, action, resource_id):
    if not token:
        raise ValueError("confirmation token is required; prepare this operation first")
    with _destructive_confirmation_lock:
        item = _destructive_confirmations.pop(str(token), None)
    if not item or item["expires_at"] <= time.time():
        raise ValueError("confirmation token is invalid or expired")
    if item["action"] != action or item["resource_id"] != resource_id:
        raise ValueError("confirmation token does not match this operation")


DEFAULT_IDENTITY = {
    "persona_name": "主理人",
    "tavern_name": "酒馆",
    "actor_name": "故事档案",
    "persona_name_en": "Curator",
    "tavern_name_en": "Tarven",
    "actor_name_en": "Story Profile",
}


def _clawchat_agent_profile():
    """Best-effort local ClawChat profile metadata for name/avatar sync."""
    path = "/opt/data/memories/owner.md"
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            in_meta = False
            for line in f:
                line = line.rstrip("\n")
                if line.strip() == "<!-- clawchat:metadata:start -->":
                    in_meta = True
                    continue
                if line.strip() == "<!-- clawchat:metadata:end -->":
                    break
                if in_meta and ":" in line:
                    k, v = line.split(":", 1)
                    out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def app_identity():
    data = dict(DEFAULT_IDENTITY)
    raw = _read(os.path.join(STATE, "app_identity.json"), {})
    if isinstance(raw, dict):
        for k in data:
            v = raw.get(k)
            if isinstance(v, str) and v.strip():
                data[k] = v.strip()
    profile = _clawchat_agent_profile()
    nick = (profile.get("agent_nickname") or "").strip()
    if nick:
        data["persona_name"] = nick
        data["persona_name_en"] = nick
    data["tavern_name_en"] = "Tarven"
    data["actor_name_en"] = "Story Profile"
    return data


# ---------- state helpers ----------
def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def _write(path, obj):
    tmp = path + ".tmp." + secrets.token_hex(4)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def _tts_key():
    """Use the Tavern/Clawling credential without exposing it to the reader."""
    return (os.environ.get("TAVERN_TTS_KEY")
            or os.environ.get("CLAWLING_API_KEY")
            or actor.MODEL_KEY
            or "").strip()


def _tts_voices(force=False):
    now = time.time()
    with _tts_voice_cache_lock:
        cached = list(_tts_voice_cache["voices"])
        fresh = now - _tts_voice_cache["at"] < TTS_VOICE_CACHE_TTL
    if fresh and not force:
        return cached
    key = _tts_key()
    if not key or not TTS_BASE:
        return cached
    request = urllib.request.Request(
        f"{TTS_BASE}/audio/voices",
        headers={"Authorization": f"Bearer {key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        voices = [item for item in (data.get("data") or [])
                  if isinstance(item, dict) and item.get("model") == TTS_MODEL
                  and str(item.get("id") or "").strip()]
        if voices:
            with _tts_voice_cache_lock:
                _tts_voice_cache["at"] = now
                _tts_voice_cache["voices"] = voices
            return voices
    except Exception:
        pass
    return cached


def _tts_config():
    saved = _read(TTS_CONFIG_PATH, {})
    return saved if isinstance(saved, dict) else {}


def _normalize_tts_speed(value):
    try:
        speed = float(value)
    except (TypeError, ValueError):
        speed = TTS_DEFAULT_SPEED
    if not 0.25 <= speed <= 4:
        raise ValueError("speech speed must be between 0.25 and 4")
    return round(speed, 2)


def _normalize_tts_instructions(value):
    instructions = str(value or "").strip()
    if len(instructions) > 1000:
        raise ValueError("speech tone instructions are too long")
    return instructions


def _tts_clones(saved):
    raw = saved.get("clones")
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    legacy = saved.get("clone")
    if isinstance(legacy, dict) and legacy:
        clone = dict(legacy)
        clone["id"] = str(clone.get("id") or clone.get("token") or "")
        clone["speed"] = _normalize_tts_speed(clone.get("speed"))
        clone.pop("tone", None)
        return [clone]
    return []


def _tts_clone_ready(clone):
    path = _tts_clone_file(clone)
    return bool(path and os.path.isfile(path) and str((clone or {}).get("ref_text") or "").strip())


def _active_tts_clone(saved):
    clones = _tts_clones(saved)
    active_id = str(saved.get("active_clone_id") or "")
    for clone in clones:
        clone_id = str(clone.get("id") or clone.get("token") or "")
        if clone_id == active_id and _tts_clone_ready(clone):
            return clone
    return None


def _preset_tts_setting(saved, voice):
    settings = saved.get("preset_settings")
    setting = settings.get(voice) if isinstance(settings, dict) else None
    setting = setting if isinstance(setting, dict) else {}
    return {
        "speed": _normalize_tts_speed(setting.get("speed")),
        "instructions": _normalize_tts_instructions(setting.get("instructions")),
    }


def _tts_clone_file(clone):
    token = str((clone or {}).get("token") or "")
    ext = str((clone or {}).get("ext") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,64}", token):
        return ""
    if ext not in (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"):
        return ""
    return os.path.join(TTS_REFERENCE_DIR, token + ext)


def _tts_clone_data_url(clone):
    path = _tts_clone_file(clone)
    if not path or not os.path.isfile(path):
        raise ValueError("cloned voice reference audio is unavailable")
    mime = str((clone or {}).get("mime") or "audio/mpeg").strip().lower()
    with open(path, "rb") as file:
        encoded = base64.b64encode(file.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _remove_tts_clone_file(clone):
    path = _tts_clone_file(clone)
    if path:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def _tts_settings():
    saved = _tts_config()
    voices = _tts_voices()
    voice_ids = {item["id"] for item in voices}
    default_voice = TTS_DEFAULT_VOICE if TTS_DEFAULT_VOICE in voice_ids else voices[0]["id"]
    voice = str(saved.get("voice") or default_voice).strip().lower()
    if voice not in voice_ids:
        voice = default_voice
    clones = [clone for clone in _tts_clones(saved) if _tts_clone_ready(clone)]
    active_clone = _active_tts_clone(saved)
    mode = "clone" if saved.get("mode") == "clone" and active_clone else "preset"

    def public_clone(clone):
        return {
            "id": str(clone.get("id") or clone.get("token") or ""),
            "configured": True,
            "name": str(clone.get("name") or "").strip(),
            "ref_text": str(clone.get("ref_text") or "").strip(),
            "speed": _normalize_tts_speed(clone.get("speed")),
        }

    public_clones = [public_clone(clone) for clone in clones]
    public_active = public_clone(active_clone) if active_clone else {}
    return {
        "model": TTS_MODEL,
        "model_name": TTS_MODEL_NAME,
        "active_voice": voice,
        "active_clone_id": public_active.get("id", ""),
        "mode": mode,
        "voices": voices,
        "preset_settings": {item["id"]: _preset_tts_setting(saved, item["id"])
                            for item in voices},
        "clones": public_clones,
        "clone": public_active,
    }


def _save_tts_voice(voice):
    saved = _tts_config()
    voices = _tts_voices()
    voice = str(voice or "").strip().lower()
    if voice not in {item["id"] for item in voices}:
        raise ValueError("unsupported voice")
    saved.update({"voice": voice, "mode": "preset"})
    saved.pop("model", None)
    _write(TTS_CONFIG_PATH, saved)
    return voice


def _save_tts_preset_settings(voice, speed=None, instructions=None):
    saved = _tts_config()
    voice = str(voice or "").strip().lower()
    if voice not in {item["id"] for item in _tts_voices()}:
        raise ValueError("unsupported voice")
    settings = saved.get("preset_settings")
    settings = dict(settings) if isinstance(settings, dict) else {}
    settings[voice] = {
        "speed": _normalize_tts_speed(speed),
        "instructions": _normalize_tts_instructions(instructions),
    }
    saved["preset_settings"] = settings
    _write(TTS_CONFIG_PATH, saved)
    return _tts_settings()


def _save_tts_clone(audio_data, ref_text, name, speed=None):
    ref_text = str(ref_text or "").strip()
    name = str(name or "").strip()[:40] or "My Voice"
    if not ref_text:
        raise ValueError("reference transcript is required")
    if len(ref_text) > 4096:
        raise ValueError("reference transcript is too long")
    speed = _normalize_tts_speed(speed)
    match = re.fullmatch(r"data:(audio/[A-Za-z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)",
                         str(audio_data or ""), re.DOTALL)
    if not match:
        raise ValueError("reference audio must be an uploaded audio file")
    mime = match.group(1).lower()
    extensions = {
        "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav",
        "audio/x-wav": ".wav", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a",
        "audio/aac": ".aac", "audio/ogg": ".ogg", "audio/flac": ".flac",
    }
    ext = extensions.get(mime)
    if not ext:
        raise ValueError("unsupported reference audio format")
    try:
        audio = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("reference audio is invalid") from error
    if not audio or len(audio) > TTS_REFERENCE_MAX_BYTES:
        raise ValueError("reference audio must be between 1 byte and 10 MB")

    saved = _tts_config()
    clones = _tts_clones(saved)
    if len(clones) >= TTS_MAX_CLONES:
        raise ValueError(f"no more than {TTS_MAX_CLONES} cloned voices are allowed")
    token = secrets.token_urlsafe(32)
    path = os.path.join(TTS_REFERENCE_DIR, token + ext)
    with open(path, "wb") as file:
        file.write(audio)
    clone = {"id": token, "token": token, "ext": ext, "mime": mime, "name": name,
             "ref_text": ref_text, "speed": speed}
    clones.append(clone)
    saved.update({"mode": "clone", "clones": clones, "active_clone_id": token})
    saved.pop("clone", None)
    saved.pop("model", None)
    try:
        _write(TTS_CONFIG_PATH, saved)
    except Exception:
        _remove_tts_clone_file(clone)
        raise
    return _tts_settings()


def _use_tts_clone(clone_id):
    saved = _tts_config()
    clone_id = str(clone_id or "")
    clone = next((item for item in _tts_clones(saved)
                  if str(item.get("id") or item.get("token") or "") == clone_id), None)
    if not clone or not _tts_clone_ready(clone):
        raise ValueError("cloned voice is not configured")
    saved.update({"mode": "clone", "active_clone_id": clone_id})
    _write(TTS_CONFIG_PATH, saved)
    return _tts_settings()


def _delete_tts_clone(clone_id):
    saved = _tts_config()
    clone_id = str(clone_id or "")
    clones = _tts_clones(saved)
    clone = next((item for item in clones
                  if str(item.get("id") or item.get("token") or "") == clone_id), None)
    if not clone:
        raise ValueError("cloned voice is not configured")
    saved["clones"] = [item for item in clones if item is not clone]
    saved.pop("clone", None)
    if str(saved.get("active_clone_id") or "") == clone_id:
        saved.pop("active_clone_id", None)
        saved["mode"] = "preset"
    _write(TTS_CONFIG_PATH, saved)
    _remove_tts_clone_file(clone)
    return _tts_settings()


def _migrate_tts_config():
    saved = _tts_config()
    changed = saved.pop("model", None) is not None
    legacy = saved.pop("clone", None)
    clones = _tts_clones({"clones": saved.get("clones")})
    if isinstance(legacy, dict) and legacy:
        migrated = dict(legacy)
        migrated["id"] = str(migrated.get("id") or migrated.get("token") or "")
        migrated["speed"] = _normalize_tts_speed(migrated.get("speed"))
        migrated.pop("tone", None)
        clones.append(migrated)
        saved["active_clone_id"] = migrated["id"]
        changed = True
    normalized_clones = []
    for clone in clones:
        clone["id"] = str(clone.get("id") or clone.get("token") or "")
        clone["speed"] = _normalize_tts_speed(clone.get("speed"))
        if clone.pop("tone", None) is not None:
            changed = True
        normalized_clones.append(clone)
    if normalized_clones != saved.get("clones"):
        saved["clones"] = normalized_clones
        changed = True
    voice_ids = {item["id"] for item in TTS_FALLBACK_VOICES}
    if saved.get("voice") not in voice_ids:
        saved["voice"] = TTS_DEFAULT_VOICE if TTS_DEFAULT_VOICE in voice_ids else "vivian"
        changed = True
    if saved.get("mode") not in ("preset", "clone"):
        saved["mode"] = "preset"
        changed = True
    if changed:
        _write(TTS_CONFIG_PATH, saved)


def _speech_text(text):
    """Remove Tavern display markers while preserving the spoken story text."""
    text = str(text or "").strip()
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    return text.replace("*", "").strip()


def _generate_speech(text, voice=None, speed=None, instructions=None, force_preset=False):
    text = _speech_text(text)
    if not text:
        raise ValueError("speech text is empty")
    if len(text) > TTS_MAX_CHARS:
        raise ValueError(f"speech text is too long (max {TTS_MAX_CHARS} characters)")
    settings = _tts_settings()
    voice = str(voice or settings["active_voice"]).strip().lower()
    if voice not in {item["id"] for item in settings["voices"]}:
        raise ValueError("unsupported voice")
    key = _tts_key()
    if not key:
        raise ValueError("Clawling TTS key is missing")
    if not TTS_BASE:
        raise ValueError("TTS service endpoint is missing")

    saved = _tts_config()
    clone = _active_tts_clone(saved) if settings["mode"] == "clone" and not force_preset else None
    clone_token = str((clone or {}).get("token") or "")
    if clone:
        speed = _normalize_tts_speed(clone.get("speed"))
        instructions = ""
    else:
        preset = _preset_tts_setting(saved, voice)
        speed = _normalize_tts_speed(speed if speed is not None else preset["speed"])
        instructions = _normalize_tts_instructions(
            instructions if instructions is not None else preset["instructions"])
    request_voice = "custom" if clone else voice
    cache_key = hashlib.sha256(
        f"{TTS_MODEL}\0{request_voice}\0{clone_token}\0{speed}\0{instructions}\0{text}".encode("utf-8")
    ).hexdigest()
    with _tts_cache_lock:
        cached = _tts_cache.get(cache_key)
    if cached is not None:
        return cached

    request_data = {
        "model": TTS_MODEL,
        "voice": request_voice,
        "input": text,
        "response_format": "mp3",
        "speed": speed,
    }
    if clone:
        request_data["ref_audio"] = _tts_clone_data_url(clone)
        request_data["ref_text"] = clone["ref_text"]
    elif instructions:
        request_data["instructions"] = instructions
    payload = json.dumps(request_data, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{TTS_BASE}/audio/speech",
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TTS_TIMEOUT) as response:
            audio = response.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise ValueError(f"TTS request failed (HTTP {e.code}): {detail}") from e
    except urllib.error.URLError as e:
        raise ValueError(f"TTS connection failed: {e.reason}") from e
    if not audio:
        raise ValueError("TTS returned empty audio")

    with _tts_cache_lock:
        _tts_cache[cache_key] = audio
        _tts_cache_order.append(cache_key)
        while len(_tts_cache_order) > TTS_CACHE_LIMIT:
            _tts_cache.pop(_tts_cache_order.pop(0), None)
    return audio


def _state_path():
    return os.path.join(STATE, "state.json")


def _get_state():
    return _read(_state_path(), {"active_production_id": None})


def _set_active(pid):
    s = _get_state()
    s["active_production_id"] = pid
    _write(_state_path(), s)


def actor_self_text():
    rt = os.path.join(STATE, "actor_self.md")
    if not os.path.exists(rt):  # 首次：种子 → 运行时副本(成长改这份，不动种子)
        with open(SEED_ACTOR, encoding="utf-8") as f:
            seed = f.read()
        with open(rt, "w", encoding="utf-8") as f:
            f.write(seed)
    with open(rt, encoding="utf-8") as f:
        return f.read()


def liveware_version():
    release_marker = os.path.join(HERE, ".tavern-release-version")
    try:
        with open(release_marker, encoding="utf-8") as f:
            version = f.read().strip()
        if version:
            return version
    except OSError:
        pass

    # 旧安装没有 release marker 时，回落到技能 frontmatter。
    skill_md = "/opt/data/skills/creative/tavern/SKILL.md"
    for path in (skill_md, os.path.join(HERE, "SKILL.md")):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("version:"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            continue
    return ""


def agent_user_id():
    """主理人在 ClawChat 里的身份 id(usr_…)——用于复盘入口的最终兜底深链。
    env 优先(dev/测试);容器里从 hermes config.yaml 文本扫描 `user_id: usr_…`。"""
    envv = os.environ.get("TAVERN_AGENT_USER_ID", "").strip()
    if envv:
        return envv
    try:
        with open("/opt/data/config.yaml", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("user_id:"):
                    v = s.split(":", 1)[1].strip().strip("'\"")
                    if v.startswith("usr_"):
                        return v
    except OSError:
        pass
    return ""


# ---------- 演员卡聚合（actor-card surface）----------
# 纯聚合读现有 state，零新后端。词汇 canon（liveware-frontend §术语表）：
# 戏路 = 演过的角色数（不是"搭档"）；搭档 = 你；亲密度由 轮数 + 权重×年表条数 驱动。
INTIMACY_W = int(os.environ.get("ACTOR_INTIMACY_W", "8"))
# 阶梯（名, 分阈值）。env 后续可覆盖；先常量。
INTIMACY_LADDER = [("初见", 0), ("相识", 15), ("搭档", 40), ("默契", 100), ("知己", 250)]
INTIMACY_BLURB = {"初见": "刚认识，还在摸你的脾气", "相识": "演过几场，记住了你几样",
                  "搭档": "有默契雏形，接得住你的球", "默契": "一个眼神就懂，越演越顺",
                  "知己": "最懂你怎么玩的那个演员"}
# 级名/blurb 的多语言表(locale contract:reader 带 ?lang= 来取——它们是 UI 标签,不是内容;
# 中文名是 canonical(技艺层/CLI 用),其他语言只在下发时映射)。
# 给二创主理人的「加语言」入口②:reader 的 STRINGS 加完,在这两张表加同 code 的项(全量 5 级),
# 缺表回落 en。①在 reader/i18n.js,教程见 SKILL.md「帮用户加界面语言」。
INTIMACY_LEVEL_I18N = {
    "en": {"初见": "First Meeting", "相识": "Acquainted", "搭档": "Partners",
           "默契": "In Sync", "知己": "Confidant"},
}
INTIMACY_BLURB_I18N = {
    "en": {"初见": "Just met — still learning your rhythms",
           "相识": "A few scenes in — noted a few of your tastes",
           "搭档": "Early chemistry — I can catch what you throw",
           "默契": "One glance is enough — smoother every scene",
           "知己": "The actor who knows exactly how you play"},
}


def _sections(md):
    """把 actor_self.md 按 '# ' 一级标题切成 {标题: [正文行]}。"""
    secs, cur = {}, None
    for line in md.splitlines():
        if line.startswith("# "):
            cur = line[2:].strip()
            secs[cur] = []
        elif cur is not None:
            secs[cur].append(line)
    return secs


def _bullets(lines):
    return [s[2:].strip() for s in (ln.strip() for ln in lines) if s.startswith("- ")]


def parse_actor_self(md):
    """从技艺层拆出：tagline（底色）、口味（我对你的了解，合并档）、年表（成长记，累计）。"""
    secs = _sections(md)

    def find(key):
        for k, v in secs.items():
            if key in k:
                return v
        return []

    tagline = ""
    for line in find("我是谁"):
        if "演员" in line and "——" in line:
            after = line.split("——", 1)[1]
            if "而是" in after:
                after = after.split("而是", 1)[1]
            tagline = after.strip().strip("。").lstrip("那个").strip()
            break
    knows = [b for b in _bullets(find("我对你的了解")) if not b.startswith("（")]
    timeline = []
    for b in _bullets(find("成长记")):
        if b.startswith("（"):
            continue
        has_date = len(b) >= 10 and b[4] == "-" and b[7] == "-"
        date = b[:10] if has_date else ""
        rest = (b[10:] if has_date else b).strip()
        if "→" in rest:
            reason, change = rest.split("→", 1)
            timeline.append({"date": date, "reason": reason.strip(), "change": change.strip()})
        else:
            timeline.append({"date": date, "reason": "", "change": rest})
    return tagline, knows, timeline


def _intimacy(score, lang="zh"):
    cur, cur_thr = INTIMACY_LADDER[0]
    nxt, nxt_thr = None, None
    for i, (name, thr) in enumerate(INTIMACY_LADDER):
        if score >= thr:
            cur, cur_thr = name, thr
            if i + 1 < len(INTIMACY_LADDER):
                nxt, nxt_thr = INTIMACY_LADDER[i + 1]
            else:
                nxt, nxt_thr = None, None
    lvl_map = INTIMACY_LEVEL_I18N.get(lang) or INTIMACY_LEVEL_I18N["en"]
    blurb_map = INTIMACY_BLURB_I18N.get(lang) or INTIMACY_BLURB_I18N["en"]

    def loc(name):  # 级名本地化(zh 是 canonical,其他查表;缺表/缺项回落 en/原名)
        return name if lang == "zh" or name is None else lvl_map.get(name, name)
    blurb = (INTIMACY_BLURB if lang == "zh" else blurb_map).get(cur, "")
    if nxt_thr is None:  # 已到顶
        return {"level": loc(cur), "score": score, "next": None, "to_next": 0, "progress": 1.0,
                "blurb": blurb}
    span = nxt_thr - cur_thr
    prog = 0.0 if span <= 0 else max(0.0, min(1.0, (score - cur_thr) / span))
    return {"level": loc(cur), "score": score, "next": loc(nxt), "to_next": nxt_thr - score,
            "progress": round(prog, 3), "blurb": blurb}


def actor_card_data(lang="zh"):
    """演员卡聚合数据（/api/actor_card?lang=）。全部从现有 state 算，无写、无新事件。
    lang 只影响 server 下发的 UI 标签（级名/blurb/name 兜底）；内容层（口味/年表/tagline）
    是主理人写的东西，不翻。"""
    prods = _list("productions")
    total_turns, total_words, role_ids, debut = 0, 0, set(), None
    roles_played = {}  # card_id -> 轮数（v1.1 角色名录）
    for p in prods:
        story = p.get("story", [])
        ca = p.get("created_at")
        if ca and (debut is None or ca < debut):
            debut = ca
        cid = p.get("card_id")
        if cid:
            role_ids.add(cid)
        uturns = 0
        for i, m in enumerate(story):
            if m.get("role") == "user":
                uturns += 1
            elif i > 0:  # 排除 story[0] 开场白（first_mes 是卡作者写的，非主理人生成）
                total_words += len(m.get("text") or "")
        total_turns += uturns
        if cid:
            roles_played[cid] = roles_played.get(cid, 0) + uturns
    debut_days = 0 if debut is None else max(0, (int(time.time()) - int(debut)) // 86400)
    tagline, knows, timeline = parse_actor_self(actor_self_text())
    intim = _intimacy(total_turns + INTIMACY_W * len(timeline), lang)
    intim["turns"] = total_turns
    intim["log"] = len(timeline)
    cards = {c["id"]: c for c in _list("cards")}
    roles = sorted(({"name": (cards.get(cid) or {}).get("name") or "角色", "turns": t}
                    for cid, t in roles_played.items()), key=lambda r: -r["turns"])
    specs = []
    for cid in role_ids:  # 擅长题材 = 各卡 tags 聚合（v1.1）
        for t in (cards.get(cid) or {}).get("tags", []) or []:
            if t not in specs:
                specs.append(t)
    return {
        # name/tagline 兜底走统一身份配置;tagline 仍来自 actor_self.md 优先。
        "name": app_identity()["persona_name"] if lang == "zh" else app_identity()["persona_name_en"],
        "tagline": tagline or ("你的故事主理人"
                               if lang == "zh" else "Your story lead"),
        "career": {"debut_days": debut_days, "productions": len(prods),
                   "turns": total_turns, "words": total_words, "roles": len(role_ids)},
        "intimacy": intim,
        "knows": knows,
        "timeline": list(reversed(timeline)),  # 最近在前
        "specialties": specs[:8],
        "roles_played": roles,
        "version": liveware_version(),
        "actor_url": (f"https://{_actor_host()}/" if _actor_host() else ""),  # 演员卡活件公网地址
    }


def _actor_host():
    """演员卡活件 app 的域名（第二个活件卡入口）。存 state/actor_host.txt，重启/bringup 不丢；
    env TAVERN_ACTOR_HOST 兜底。为空 = 没注册第二个 app（`/` 一律控制台）。"""
    try:
        with open(os.path.join(STATE, "actor_host.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return os.environ.get("TAVERN_ACTOR_HOST", "").strip()


def load_card(cid):
    return _read(os.path.join(STATE, "cards", cid + ".json"))


def load_worldbook(wid):
    return _read(os.path.join(STATE, "worldbooks", wid + ".json"))


def load_production(pid):
    p = _read(os.path.join(STATE, "productions", pid + ".json"))
    return _ensure_production_session(p)


_PRODUCTION_LOCKS = {}
_PRODUCTION_LOCKS_GUARD = threading.Lock()


def _production_lock(pid):
    with _PRODUCTION_LOCKS_GUARD:
        return _PRODUCTION_LOCKS.setdefault(pid, threading.RLock())


def save_production(p):
    with _production_lock(p["id"]):
        record = dict(p)
        record.pop("worldbooks", None)
        _write(os.path.join(STATE, "productions", p["id"] + ".json"), record)


def _story_revision(p):
    story = (p or {}).get("story") or []
    return len(story), (story[-1].get("id") if story else None)


def _merge_production_fields(pid, expected_story_revision=None, **fields):
    """Merge background results into the latest world without replacing its story."""
    with _production_lock(pid):
        current = load_production(pid)
        if not current:
            return None
        if expected_story_revision is not None and _story_revision(current) != expected_story_revision:
            return None
        current.update(fields)
        record = dict(current)
        record.pop("worldbooks", None)
        _write(os.path.join(STATE, "productions", pid + ".json"), record)
        return current


def _locale_code(value):
    return "zh" if str(value or "").lower().startswith("zh") else "en"


def _interface_language(locale):
    """Chinese UI uses Chinese prompts; every other declared UI locale uses English."""
    raw = str(locale or "").lower().strip()
    if not raw:
        return None
    return "zh" if raw.startswith("zh") else "en"


def _text_language(text):
    """Deterministic zh/en detection. Returns (language, confidence) or (None, 0)."""
    text = str(text or "")
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    total = cjk + latin
    if total < 12:
        return None, 0.0
    ratio = cjk / total
    if cjk >= 8 and ratio >= 0.28:
        return "zh", min(1.0, 0.55 + ratio)
    if latin >= 24 and ratio <= 0.08:
        return "en", min(1.0, 0.65 + (latin / max(80, latin)) * 0.25)
    return None, 0.0


def _localized_field(obj, field, locale):
    if not isinstance(obj, dict):
        return ""
    pack = (obj.get("i18n") or {}).get(locale) or {}
    return str(pack.get(field) or obj.get(field) or "")


def _world_language_evidence(p, locale):
    interface_language = _interface_language(locale)
    if interface_language:
        return interface_language, 1.0, "liveware_locale"

    card_parts = []
    for card in p.get("cards") or []:
        for field in ("name", "description", "personality", "scenario", "first_mes", "mes_example"):
            card_parts.append(_localized_field(card, field, locale))
    detected = _text_language("\n".join(card_parts))
    if detected[0]:
        return detected[0], detected[1], "character_cards"

    lore_parts = []
    for wb in p.get("worldbooks") or []:
        lore_parts.append(_localized_field(wb, "name", locale))
        for entry in wb.get("entries") or []:
            lore_parts.append(_localized_field(entry, "content", locale))
    detected = _text_language("\n".join(lore_parts))
    if detected[0]:
        return detected[0], detected[1], "worldbooks"

    opening = []
    for message in (p.get("story") or [])[:2]:
        opening.append(message.get("text") or "")
    detected = _text_language("\n".join(opening))
    if detected[0]:
        return detected[0], detected[1], "opening"
    return "zh", 0.45, "default"


def _ensure_world_language(p, locale=None):
    current = str(p.get("response_language") or "").lower()
    mode = str(p.get("language_mode") or "ui").lower()
    if mode == "auto":
        mode = "ui"
        p["language_mode"] = mode
    if mode == "manual" and current in ("zh", "en"):
        return current

    interface_language = _interface_language(locale)
    if interface_language:
        if current != interface_language or p.get("language_source") != "liveware_locale" or mode != "ui":
            p["language_mode"] = "ui"
            p["response_language"] = interface_language
            p["language_confidence"] = 1.0
            p["language_source"] = "liveware_locale"
            runtime = p.setdefault("runtime", {})
            runtime.pop("language_candidate", None)
            runtime.pop("language_candidate_streak", None)
        return interface_language

    if current in ("zh", "en"):
        p.setdefault("language_mode", "ui")
        return current
    language, confidence, source = _world_language_evidence(p, locale)
    p["language_mode"] = "ui"
    p["response_language"] = language
    p["language_confidence"] = round(float(confidence), 3)
    p["language_source"] = source
    return language


def _explicit_language_request(text):
    raw = str(text or "")
    low = raw.lower()
    if re.search(r"(?:用|改用|切换到?|请用).{0,6}(?:英文|英语)", raw) or re.search(r"\b(?:switch|reply|continue|write|speak|use)\b.{0,20}\benglish\b", low):
        return "en"
    if re.search(r"(?:用|改用|切换到?|请用).{0,6}(?:中文|汉语)", raw) or re.search(r"\b(?:switch|reply|continue|write|speak|use)\b.{0,20}\bchinese\b", low):
        return "zh"
    return None


def _set_world_language(p, language, confidence=1.0, source="explicit", mode=None):
    p["language_mode"] = mode or ("manual" if source == "explicit" else "ui")
    p["response_language"] = _locale_code(language)
    p["language_confidence"] = round(float(confidence), 3)
    p["language_source"] = source
    runtime = p.setdefault("runtime", {})
    runtime.pop("language_candidate", None)
    runtime.pop("language_candidate_streak", None)


def _observe_user_language(p, text, locale=None):
    current = _ensure_world_language(p, locale)
    explicit = _explicit_language_request(text)
    if explicit:
        _set_world_language(p, explicit, mode="manual")
        return p["response_language"]

    if p.get("language_mode") == "manual" or _interface_language(locale):
        runtime = p.setdefault("runtime", {})
        runtime.pop("language_candidate", None)
        runtime.pop("language_candidate_streak", None)
        return current

    detected, confidence = _text_language(text)
    runtime = p.setdefault("runtime", {})
    if not detected or detected == current or confidence < 0.75:
        runtime.pop("language_candidate", None)
        runtime.pop("language_candidate_streak", None)
        return current

    prior_user_turns = sum(1 for m in p.get("story") or [] if m.get("role") == "user")
    if prior_user_turns == 0 and p.get("language_source") == "default":
        _set_world_language(p, detected, confidence, "first_user_message", mode="ui")
        return detected

    streak = int(runtime.get("language_candidate_streak") or 0) + 1 if runtime.get("language_candidate") == detected else 1
    runtime["language_candidate"] = detected
    runtime["language_candidate_streak"] = streak
    if streak >= 2:
        _set_world_language(p, detected, confidence, "consecutive_user_messages", mode="ui")
        return detected
    return current


def _list(sub):
    d = os.path.join(STATE, sub)
    out = []
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            out.append(_read(os.path.join(d, fn)))
    return out


def _list_productions():
    """Return productions hydrated from their canonical worldbook files."""
    d = os.path.join(STATE, "productions")
    out = []
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            p = load_production(fn[:-5])
            if p:
                out.append(p)
    return out


def _is_runtime_worldbook(wb):
    return str((wb or {}).get("id") or "").startswith("wb_prod_")


def _runtime_worldbook_id(pid, source_id):
    digest = hashlib.sha1(str(source_id or "worldbook").encode("utf-8", "ignore")).hexdigest()[:10]
    return f"wb_prod_{pid}_{digest}"


def _clone_worldbook_for_production(pid, source_id, source=None):
    """Materialize a reusable template as one production-owned canonical file."""
    source = source or load_worldbook(source_id)
    if not source:
        return None
    if source.get("owner_production_id") == pid and _is_runtime_worldbook(source):
        return source["id"]
    original_id = source.get("source_worldbook_id") or source.get("id") or source_id
    runtime_id = _runtime_worldbook_id(pid, original_id)
    existing = load_worldbook(runtime_id)
    if existing and existing.get("owner_production_id") == pid:
        return runtime_id
    clone = json.loads(json.dumps(source, ensure_ascii=False))
    clone["id"] = runtime_id
    clone["source_worldbook_id"] = original_id
    clone["owner_production_id"] = pid
    _write(os.path.join(STATE, "worldbooks", runtime_id + ".json"), clone)
    return runtime_id


def _materialize_worldbook_ids(pid, source_ids):
    out = []
    for source_id in source_ids or []:
        runtime_id = _clone_worldbook_for_production(pid, source_id)
        if runtime_id and runtime_id not in out:
            out.append(runtime_id)
    return out


def _library_cards():
    # 角色卡库：所有可复用角色模板。加入/移出某个世界不会删除这里的卡。
    return [c for c in _list("cards") if c]


def _library_worldbooks():
    # 世界书库：只放可复用世界模板；当前世界运行时设定本(wb_prod_*)不进入库。
    return [w for w in _list("worldbooks") if w and not _is_runtime_worldbook(w)]


def _production_worldbooks(pid):
    p = load_production(pid)
    if not p:
        return []
    _ensure_production_session(p)
    return [w for w in (p.get("worldbooks") or []) if isinstance(w, dict)]


def _msg(role, text):
    return {"id": secrets.token_hex(4), "role": role, "text": text,
            "ts": int(time.time()), "alts": [text], "active_alt": 0}


_CANCELLED_GENERATIONS = {}
_CANCELLED_GENERATIONS_LOCK = threading.Lock()


def ev_cancel_generation(ev):
    request_id = str(ev.get("request_id") or "").strip()
    if not request_id:
        raise ValueError("request_id is required")
    now = time.time()
    with _CANCELLED_GENERATIONS_LOCK:
        expired = [rid for rid, ts in _CANCELLED_GENERATIONS.items() if now - ts > 600]
        for rid in expired:
            _CANCELLED_GENERATIONS.pop(rid, None)
        _CANCELLED_GENERATIONS[request_id] = now
    return {"cancelled": True, "request_id": request_id}


def _raise_if_generation_cancelled(ev):
    request_id = str(ev.get("request_id") or "").strip()
    if not request_id:
        return
    with _CANCELLED_GENERATIONS_LOCK:
        cancelled = _CANCELLED_GENERATIONS.pop(request_id, None) is not None
    if cancelled:
        raise RuntimeError("generation cancelled")


# ---------- event handlers ----------
def _store_card(card, source=""):
    # source = 导入渠道(出处):chub=导入真卡 / agent=原创。creator(卡作者)仍透传,
    # 信息面板优先显 creator,无 creator 才回落 source(Task 2 角色卡出处)。
    if source:
        card["source"] = source
    if str(card.get("source") or "").startswith("builtin:"):
        lang = (((card.get("extensions") or {}).get("tavern") or {}).get("language") or "zh")
        identity = app_identity()
        card["creator"] = identity["tavern_name"] if lang == "zh" else identity["tavern_name_en"]
    _write(os.path.join(STATE, "cards", card["id"] + ".json"), card)
    # 卡内嵌世界书 → 落成独立 worldbook
    if card.get("character_book"):
        wb = {"id": "wb_" + card["id"], "name": card["character_book"].get("name") or card["name"],
              "recursive": False, "entries": card["character_book"].get("entries", [])}
        _write(os.path.join(STATE, "worldbooks", wb["id"] + ".json"), wb)
    return {"card": card}


def ev_import_card(ev):
    # PNG 路径：吃一张 V2/V3 角色卡 PNG（base64）。真实卡走这条，编码天然正确。出处=chub。
    return _store_card(card_import.import_card_b64(ev["png_base64"]), "chub")


def ev_import_card_json(ev):
    # JSON 路径：吃一份卡 JSON（V1/V2/V3 形态，带 data 包或裸 obj 都行）。
    # 给 agent「原创/自造」角色卡用——不手搓 PNG，绕开 btoa(UTF-8) 把中文搞乱码的坑。出处=agent。
    return _store_card(card_import.normalize_card(ev["card"]), ev.get("source") or "agent")


def ev_create_card(ev):
    name = (ev.get("name") or "未命名角色").strip() or "未命名角色"
    desc = (ev.get("description") or "").strip()
    personality = (ev.get("personality") or "").strip()
    scenario = (ev.get("scenario") or "").strip()
    first_mes = (ev.get("first_mes") or "").strip()
    card = {
        "id": "card_" + secrets.token_hex(4),
        "name": name,
        "description": desc,
        "personality": personality,
        "scenario": scenario,
        "first_mes": first_mes,
        "tags": ["手动创建"],
    }
    return _store_card(card, "agent")


def ev_import_worldbook(ev):
    wb = ev["worldbook"]
    wb.setdefault("id", "wb_" + secrets.token_hex(4))
    _write(os.path.join(STATE, "worldbooks", wb["id"] + ".json"), wb)
    return {"worldbook": wb}


def ev_attach_worldbook(ev):
    # Reusable books are cloned into a production-owned canonical file.
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    wid = ev["worldbook_id"]
    if not load_worldbook(wid):
        raise ValueError("worldbook not found: " + wid)
    runtime_id = _clone_worldbook_for_production(p["id"], wid)
    if runtime_id and runtime_id not in p["worldbook_ids"]:
        p["worldbook_ids"].append(runtime_id)
    _ensure_production_session(p)
    _mark_story_state_stale(p, "worldbook_changed")
    save_production(p)
    return {"production": p}


def _prod_worldbook_id(pid):
    return "wb_prod_" + pid


def _simple_keys(text, cards):
    keys = []
    for c in cards or []:
        name = str(c.get("name") or "").strip()
        if name and name in text:
            keys.append(name)
    for token in ("阁楼", "旧物", "铜扣", "失踪案", "二楼", "旅馆", "雨", "钥匙", "旧客", "秘密"):
        if token in text and token not in keys:
            keys.append(token)
    if not keys:
        keys = [x for x in text.replace("，", " ").replace("。", " ").replace("、", " ").split() if 1 < len(x) <= 8][:4]
    return keys[:8]


def _normalize_lore_entry(raw, text, cards):
    if not isinstance(raw, dict):
        raw = {}
    def arr(key, fallback=None, limit=8):
        vals = raw.get(key)
        if vals is None:
            vals = fallback or []
        if isinstance(vals, str):
            vals = [vals]
        out = []
        for v in vals or []:
            x = str(v).strip().lstrip("-•").strip()
            if x and x not in out:
                out.append(x[:40])
        return out[:limit]
    content = str(raw.get("content") or text or "").strip()
    keys = arr("keys", _simple_keys(content, cards))
    secondary = arr("secondary_keys", [], 6)
    category = str(raw.get("category") or "setting").strip()[:40]
    try:
        priority = int(raw.get("priority", 5))
    except Exception:
        priority = 5
    priority = max(1, min(10, priority))
    position = str(raw.get("position") or "before_char").strip()
    if position not in ("before_char", "after_char"):
        position = "before_char"
    selective = bool(raw.get("selective"))
    if not raw.get("selective") and secondary:
        selective = True
    entry = {
        "id": "lore_" + secrets.token_hex(4),
        "keys": keys,
        "content": content,
        "enabled": True,
        "constant": bool(raw.get("constant", False)),
        "selective": selective,
        "secondary_keys": secondary,
        "exclusion_keys": arr("exclusion_keys", [], 6),
        "priority": priority,
        "insertion_order": int(raw.get("insertion_order", priority * 10) or priority * 10),
        "position": position,
        "category": category,
        "source": "user_lore",
        "created_at": int(time.time()),
    }
    known_by = arr("known_by", [], 8)
    hidden_from = arr("hidden_from", [], 8)
    if known_by or hidden_from:
        entry["visibility"] = {"known_by": known_by, "hidden_from": hidden_from}
    return entry


def _classify_lore_entry(text, p, cards):
    names = [c.get("name", "") for c in cards or []]
    language = _ensure_world_language(p)
    sys = ((
        "Organize the user's natural-language story setting into a worldbook entry. Keep content and keyword values in English. "
        "Output strict JSON with optional category, content, keys, secondary_keys, selective, exclusion_keys, priority, position, constant, known_by, and hidden_from. "
        "Preserve the user's facts in content; keys are trigger terms; priority is 1-10; position is only before_char or after_char."
    ) if language == "en" else (
        "把用户的一条自然语言故事设定整理成世界书条目，content 与关键词值使用简体中文。"
        "输出严格 JSON，字段可包含 category、content、keys、secondary_keys、selective、"
        "exclusion_keys、priority、position、constant、known_by、hidden_from。"
        "content 保留用户设定的事实；keys 是触发词；priority 1-10；"
        "position 只能是 before_char 或 after_char。"
    ))
    user = json.dumps({
        "text": text,
        "characters": names,
        "response_language": language,
        "scene_state": p.get("scene_state") or {},
        "story_state": p.get("story_state") or {},
    }, ensure_ascii=False)
    try:
        out = actor.chat([{ "role": "system", "content": sys }, { "role": "user", "content": user }],
                         temperature=0.1, model=_active_model()).strip()
        raw = _json_from_model_text(out)
    except Exception:
        raw = {}
    return _normalize_lore_entry(raw, text, cards)


def ev_add_lore(ev):
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    text = (ev.get("content") or ev.get("text") or "").strip()
    if not text:
        raise ValueError("content is required")
    cards, _, _, _ = _loadout(p)
    if "content" in ev or "constant" in ev or "keys" in ev:
        constant = bool(ev.get("constant"))
        keys = ev.get("keys") or []
        if isinstance(keys, str):
            keys = [x.strip() for x in re.split(r"[,，、]", keys) if x.strip()]
        if not constant and not keys:
            raise ValueError("trigger keys are required")
        entry = _normalize_lore_entry({
            "content": text,
            "constant": constant,
            "keys": [] if constant else keys,
            "position": "before_char",
            "category": "setting",
        }, text, cards)
    else:
        entry = _classify_lore_entry(text, p, cards)
    wid = _prod_worldbook_id(p["id"])
    wb = next((w for w in (p.get("worldbooks") or []) if w.get("id") == wid), None)
    if wb is None:
        wb = load_worldbook(wid) or {
            "id": wid,
            "name": p.get("name", "当前世界") + " · 设定",
            "recursive": False,
            "entries": [],
            "owner_production_id": p["id"],
            "source_worldbook_id": wid,
        }
        p.setdefault("worldbooks", []).append(wb)
    wb.setdefault("entries", []).append(entry)
    _write(os.path.join(STATE, "worldbooks", wid + ".json"), wb)
    if wid not in p.get("worldbook_ids", []):
        p.setdefault("worldbook_ids", []).append(wid)
    p["turn_plan"] = {}
    save_production(p)
    return {"production": p, "worldbook": wb, "entry": entry}

def _find_world_lore(p, worldbook_id=None, entry_id=None, entry_index=None):
    for wb in p.get("worldbooks") or []:
        if worldbook_id and str(wb.get("id")) != str(worldbook_id):
            continue
        entries = wb.get("entries") or []
        if entry_id:
            for index, entry in enumerate(entries):
                if str(entry.get("id")) == str(entry_id):
                    return wb, entries, index, entry
        if entry_index is not None:
            try:
                index = int(entry_index)
            except (TypeError, ValueError):
                index = -1
            if 0 <= index < len(entries):
                return wb, entries, index, entries[index]
    return None, None, None, None


def _persist_runtime_worldbook(wb):
    if wb and _is_runtime_worldbook(wb):
        _write(os.path.join(STATE, "worldbooks", wb["id"] + ".json"), wb)


def ev_update_lore(ev):
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    wb, _, _, entry = _find_world_lore(
        p, ev.get("worldbook_id"), ev.get("entry_id"), ev.get("entry_index"))
    if not entry:
        raise ValueError("lore entry not found")
    content = (ev.get("content") or "").strip()
    if not content:
        raise ValueError("content is required")
    constant = bool(ev.get("constant"))
    keys = ev.get("keys") or []
    if isinstance(keys, str):
        keys = [x.strip() for x in re.split(r"[,，、]", keys) if x.strip()]
    if not constant and not keys:
        raise ValueError("trigger keys are required")
    entry["content"] = content
    entry["constant"] = constant
    entry["keys"] = [] if constant else keys[:8]
    entry["updated_at"] = int(time.time())
    _persist_runtime_worldbook(wb)
    p["turn_plan"] = {}
    save_production(p)
    return {"production": p, "worldbook": wb, "entry": entry}


def ev_delete_lore(ev):
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    wb, entries, index, _ = _find_world_lore(
        p, ev.get("worldbook_id"), ev.get("entry_id"), ev.get("entry_index"))
    if wb is None:
        raise ValueError("lore entry not found")
    deleted = entries.pop(index)
    _persist_runtime_worldbook(wb)
    p["turn_plan"] = {}
    save_production(p)
    return {"production": p, "worldbook": wb, "deleted": deleted.get("id") or index}


def ev_create_production(ev):
    requested = ev.get("card_ids") or [ev.get("card_id")]
    card_ids = []
    cards = []
    for cid in requested:
        if not cid or cid in card_ids:
            continue
        card = load_card(cid)
        if not card:
            raise ValueError("card not found: " + cid)
        card_ids.append(cid)
        cards.append(card)
    if not cards:
        raise ValueError("card_id is required")
    card = cards[0]
    pid = "prod_" + secrets.token_hex(4)
    wbs = ev.get("worldbook_ids")
    if wbs is None:
        wbs = []
        for c in cards:
            if c.get("character_book"):
                wid = "wb_" + c["id"]
                if wid not in wbs:
                    wbs.append(wid)
    greeting = ev.get("first_mes") or card.get("first_mes") or ""
    runtime_wbs = _materialize_worldbook_ids(pid, wbs or [])
    p = {"id": pid, "name": ev.get("name") or card.get("name"),
         "card_id": card["id"], "card_ids": card_ids, "worldbook_ids": runtime_wbs,
         "cards": cards,
         "persona_id": ev.get("persona_id"), "persona": ev.get("persona") or {},
         "created_at": int(time.time()), "status": "active", "runtime": {},
         "story": [_msg("char", greeting)] if greeting else []}
    _ensure_world_language(p, ev.get("locale"))
    _ensure_production_session(p)
    save_production(p)
    _set_active(pid)
    return {"production": p}


def ev_create_blank_production(ev):
    name = (ev.get("name") or "未命名世界").strip() or "未命名世界"
    pid = "prod_" + secrets.token_hex(4)
    wb_ids = ev.get("worldbook_ids") or []
    runtime_wbs = _materialize_worldbook_ids(pid, wb_ids)
    p = {"id": pid, "name": name,
         "card_id": None, "card_ids": [], "worldbook_ids": runtime_wbs,
         "cards": [],
         "persona_id": ev.get("persona_id"), "persona": ev.get("persona") or {},
         "created_at": int(time.time()), "status": "active", "runtime": {}, "story": []}
    _ensure_world_language(p, ev.get("locale"))
    _ensure_production_session(p)
    save_production(p)
    _set_active(pid)
    return {"production": p}


def ev_attach_card(ev):
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    cid = ev.get("card_id")
    card = load_card(cid)
    if not card:
        raise ValueError("card not found: " + str(cid))
    ids = _production_card_ids(p)
    if cid not in ids:
        ids.append(cid)
    p["card_ids"] = ids
    p.setdefault("card_id", ids[0])
    session_cards = [c for c in (p.get("cards") or []) if isinstance(c, dict) and c.get("id") != cid]
    session_cards.append(card)
    p["cards"] = session_cards
    wid = "wb_" + cid
    if load_worldbook(wid) and wid not in p.get("worldbook_ids", []):
        runtime_id = _clone_worldbook_for_production(p["id"], wid)
        if runtime_id and runtime_id not in p.get("worldbook_ids", []):
            p.setdefault("worldbook_ids", []).append(runtime_id)
        _ensure_production_session(p)
    _mark_story_state_stale(p, "loadout_changed")
    save_production(p)
    return {"production": p}


def ev_update_cast(ev):
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    cid = ev.get("card_id")
    card = next((c for c in (p.get("cards") or []) if c.get("id") == cid), None)
    if not card:
        raise ValueError("character not found in current world")
    fields = ("name", "description", "personality", "scenario")
    for field in fields:
        if field in ev:
            card[field] = str(ev.get(field) or "").strip()
    if not card.get("name"):
        raise ValueError("name is required")
    card["updated_at"] = int(time.time())
    p["turn_plan"] = {}
    save_production(p)
    return {"production": p, "card": card}


def ev_detach_card(ev):
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    cid = ev.get("card_id")
    ids = [x for x in _production_card_ids(p) if x != cid]
    p["card_ids"] = ids
    p["card_id"] = ids[0] if ids else None
    p["cards"] = [c for c in (p.get("cards") or []) if isinstance(c, dict) and c.get("id") != cid]
    source_wid = "wb_" + str(cid)
    kept_worldbook_ids = []
    for wid in p.get("worldbook_ids", []):
        wb = load_worldbook(wid)
        if wb and wb.get("owner_production_id") == p["id"] and wb.get("source_worldbook_id") == source_wid:
            try:
                os.remove(os.path.join(STATE, "worldbooks", wid + ".json"))
            except OSError:
                pass
            continue
        kept_worldbook_ids.append(wid)
    p["worldbook_ids"] = kept_worldbook_ids
    _ensure_production_session(p)
    _mark_story_state_stale(p, "loadout_changed")
    save_production(p)
    return {"production": p}


def ev_delete_card(ev):
    cid = ev.get("card_id")
    if not cid:
        raise ValueError("card_id is required")
    path = os.path.join(STATE, "cards", cid + ".json")
    if not os.path.exists(path):
        raise ValueError("card not found: " + str(cid))
    os.remove(path)
    wb_path = os.path.join(STATE, "worldbooks", "wb_" + cid + ".json")
    if os.path.exists(wb_path):
        os.remove(wb_path)
    changed = []
    for prod in _list_productions():
        if not prod:
            continue
        ids = [x for x in _production_card_ids(prod) if x != cid]
        source_wid = "wb_" + cid
        wids = []
        for wid in prod.get("worldbook_ids", []):
            wb = load_worldbook(wid)
            if wb and wb.get("owner_production_id") == prod["id"] and wb.get("source_worldbook_id") == source_wid:
                try:
                    os.remove(os.path.join(STATE, "worldbooks", wid + ".json"))
                except OSError:
                    pass
                continue
            wids.append(wid)
        if ids != _production_card_ids(prod) or wids != prod.get("worldbook_ids", []):
            prod["card_ids"] = ids
            prod["card_id"] = ids[0] if ids else None
            prod["worldbook_ids"] = wids
            save_production(prod)
            changed.append(prod["id"])
    return {"deleted": cid, "updated_productions": changed}


# Q_C：切走剧组时后台自动复盘（达阈值才做），不阻塞切换、不靠主理人自觉（结构性 > 软性）。
AUTO_REFLECT_MIN = int(os.environ.get("ACTOR_AUTO_REFLECT_MIN", "4"))      # 至少这么多轮才值得复盘
AUTO_REFLECT_EVERY = int(os.environ.get("ACTOR_AUTO_REFLECT_EVERY", "6"))  # 距上次复盘再攒这么多轮


def _maybe_auto_reflect(pid):
    p = load_production(pid)
    if not p:
        return
    uturns = sum(1 for m in p.get("story", []) if m.get("role") == "user")
    done = p.get("reflected_at_turns", 0)
    if uturns < AUTO_REFLECT_MIN or uturns - done < AUTO_REFLECT_EVERY:
        return
    try:
        _reflect_production(p)
        _merge_production_fields(pid, reflected_at_turns=uturns)
    except Exception:
        pass  # 后台尽力而为，失败不影响任何前台操作


def ev_switch_loadout(ev):
    prev = _get_state().get("active_production_id")
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    language_before = (p.get("language_mode"), p.get("response_language"), p.get("language_source"))
    _ensure_world_language(p, ev.get("locale"))
    language_after = (p.get("language_mode"), p.get("response_language"), p.get("language_source"))
    if language_after != language_before:
        save_production(p)
    _set_active(p["id"])
    if prev and prev != p["id"]:  # Q_C：离开一场戏 = 复盘它的自然时机（后台线程，不阻塞切换）
        threading.Thread(target=_maybe_auto_reflect, args=(prev,), daemon=True).start()
    return {"production": p}


def ev_delete_production(ev):
    # 删一个剧组(连同它的故事线 story)——不可逆,前端走二次确认(Task 4)。
    # 删的若是当前活跃剧组,active 切到剩下的第一个、没有则清空。
    pid = ev["production_id"]
    p = load_production(pid)
    if not p:
        raise ValueError("production not found")
    _consume_destructive_confirmation(
        ev.get("confirmation_token"), "delete_production", pid
    )
    path = os.path.join(STATE, "productions", pid + ".json")
    try:
        os.remove(path)
    except OSError:
        pass
    # Delete every production-owned canonical book; reusable templates remain.
    for wid in p.get("worldbook_ids", []):
        wb = load_worldbook(wid)
        if wb and wb.get("owner_production_id") == pid:
            try:
                os.remove(os.path.join(STATE, "worldbooks", wid + ".json"))
            except OSError:
                pass
    new_active = _get_state().get("active_production_id")
    if new_active == pid:
        remaining = [x for x in _list("productions") if x]
        new_active = remaining[0]["id"] if remaining else None
        _set_active(new_active)
    return {"deleted": pid, "active": new_active}


def ev_prepare_delete_production(ev):
    pid = ev.get("production_id")
    p = load_production(pid) if pid else None
    if not p:
        raise ValueError("production not found")
    token = _prepare_destructive_confirmation("delete_production", pid)
    return {
        "confirmation_token": token,
        "expires_in": DESTRUCTIVE_CONFIRM_TTL,
        "production": {
            "id": p["id"],
            "name": p.get("name") or "未命名世界",
            "story_count": len(p.get("story") or []),
        },
    }


def _production_card_ids(p):
    ids = p.get("card_ids") or ([] if not p.get("card_id") else [p.get("card_id")])
    out = []
    for cid in ids:
        if cid and cid not in out:
            out.append(cid)
    return out


def _snapshot_worldbooks(ids):
    out = []
    for wid in ids or []:
        wb = load_worldbook(wid)
        if wb:
            out.append(wb)
    return out


def _migrate_worldbook_storage():
    """Move legacy embedded snapshots into production-owned canonical files."""
    migrated = 0
    for raw in _list("productions"):
        if not raw:
            continue
        pid = raw.get("id")
        if not pid:
            continue
        embedded = [w for w in (raw.get("worldbooks") or []) if isinstance(w, dict)]
        embedded_by_id = {str(w.get("id") or ""): w for w in embedded}
        ordered_ids = list(raw.get("worldbook_ids") or [])
        for wb in embedded:
            wid = wb.get("id")
            if wid and wid not in ordered_ids:
                ordered_ids.append(wid)
        canonical_ids = []
        for wid in ordered_ids:
            wb = embedded_by_id.get(str(wid)) or load_worldbook(wid)
            if not wb:
                continue
            owned = wb.get("owner_production_id") == pid and _is_runtime_worldbook(wb)
            legacy_local = wid == _prod_worldbook_id(pid)
            if owned or legacy_local:
                canonical_id = wid
                canonical = json.loads(json.dumps(wb, ensure_ascii=False))
                canonical["id"] = canonical_id
                canonical["owner_production_id"] = pid
                canonical.setdefault("source_worldbook_id", wid)
                _write(os.path.join(STATE, "worldbooks", canonical_id + ".json"), canonical)
            else:
                source_id = wb.get("source_worldbook_id") or wid
                canonical_id = _runtime_worldbook_id(pid, source_id)
                canonical = json.loads(json.dumps(wb, ensure_ascii=False))
                canonical["id"] = canonical_id
                canonical["source_worldbook_id"] = source_id
                canonical["owner_production_id"] = pid
                _write(os.path.join(STATE, "worldbooks", canonical_id + ".json"), canonical)
            if canonical_id not in canonical_ids:
                canonical_ids.append(canonical_id)
        changed = raw.get("worldbooks") is not None or canonical_ids != list(raw.get("worldbook_ids") or [])
        if changed:
            raw["worldbook_ids"] = canonical_ids
            raw.pop("worldbooks", None)
            _write(os.path.join(STATE, "productions", pid + ".json"), raw)
            migrated += 1
    return migrated


def _ensure_production_session(p):
    """Hydrate current-story data; worldbook files are the sole lore authority."""
    if p is None:
        return p
    if not isinstance(p.get("cards"), list):
        cards = [load_card(cid) for cid in _production_card_ids(p)]
        p["cards"] = [c for c in cards if c]
    p["worldbooks"] = _snapshot_worldbooks(p.get("worldbook_ids") or [])
    if not isinstance(p.get("persona"), dict):
        p["persona"] = {}
    p.setdefault("story", [])
    p.setdefault("runtime", {})
    return p


def _mark_story_state_stale(p, reason="history_changed"):
    p["turn_plan"] = {}
    p.setdefault("runtime", {})["state_stale_reason"] = reason
    p["runtime"].pop("last_prompt_debug", None)
    if isinstance(p.get("story_state"), dict):
        p["story_state"]["stale"] = True
    if isinstance(p.get("scene_state"), dict):
        p["scene_state"]["stale"] = True


def _loadout(p):
    """一回合演出要喂的料:当前故事角色快照 + 世界书快照 + 人设 + 作者注释。"""
    _ensure_production_session(p)
    cards = [c for c in (p.get("cards") or []) if isinstance(c, dict)]
    wbs = [w for w in (p.get("worldbooks") or []) if isinstance(w, dict)]
    persona = p.get("persona") or {}
    note = p.get("author_note", "")
    return cards, wbs, persona, note


def _perform_into(p):
    cards, wbs, persona, note = _loadout(p)
    turn_plan = _prepare_turn_plan(p, cards)
    language = _ensure_world_language(p)
    return actor.perform(cards, wbs, persona, p["story"], note,
                         model=_active_model(), story_state=p.get("story_state"),
                         scene_state=p.get("scene_state"), turn_plan=turn_plan,
                         response_language=language)  # 用户自配大模型;None=内置模型


def ev_send_message(ev):
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    _observe_user_language(p, ev["text"], ev.get("locale"))
    user_msg = _msg("user", ev["text"])
    p["story"].append(user_msg)
    cards, wbs, persona, note = _loadout(p)
    reply = _ensure_actor_reply(p, cards, wbs, persona, note, _perform_into(p))
    _raise_if_generation_cancelled(ev)
    m = _msg("char", reply)
    p["story"].append(m)
    save_production(p)
    _schedule_story_state(p["id"])
    _schedule_scene_state(p["id"])
    return {"reply": reply, "message": m, "user_message": user_msg, "production_id": p["id"]}


def ev_regenerate(ev):
    p = load_production(ev["production_id"])
    if not p or not p["story"]:
        raise ValueError("nothing to regenerate")
    _ensure_world_language(p, ev.get("locale"))
    # 砍掉最后一条 char，重演（保留为 alt）
    last = p["story"][-1]
    if last["role"] != "char":
        raise ValueError("last message is not the actor's")
    trimmed = p["story"][:-1]
    saved_story = p["story"]
    p["story"] = trimmed
    _mark_story_state_stale(p, "regenerate")
    cards, wbs, persona, note = _loadout(p)
    reply = _ensure_actor_reply(p, cards, wbs, persona, note, _perform_into(p))
    _raise_if_generation_cancelled(ev)
    last["alts"].append(reply)
    last["active_alt"] = len(last["alts"]) - 1
    last["text"] = reply
    p["story"] = saved_story
    save_production(p)
    _schedule_story_state(p["id"])
    _schedule_scene_state(p["id"])
    return {"message": last, "production_id": p["id"]}


def _continue_note(note: str = "", response_language: str = "zh") -> str:
    if _locale_code(response_language) == "en":
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


def _format_actor_paragraph(para: str) -> str:
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


def _normalize_actor_reply(text: str) -> str:
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
    formatted = [_format_actor_paragraph(p) for p in paras]
    return "\n\n".join(p for p in formatted if p)

def _ensure_actor_reply(p, cards, wbs, persona, note, text):
    text = _normalize_actor_reply(text)
    if text:
        return text
    language = _ensure_world_language(p)
    retry_instruction = ("Continue from the user's latest message with one coherent story response in English. Keep action, environment, and character dialogue naturally connected."
                         if language == "en" else
                         "承接最后一条用户输入，使用简体中文续写当前故事的一段内容。动作、环境与角色对白要自然连贯。")
    retry_note = (note + "\n" if note else "") + retry_instruction
    try:
        text = _normalize_actor_reply(actor.perform(cards, wbs, persona, p["story"], retry_note,
                                                    model=_active_model(), story_state=p.get("story_state"),
                                                    scene_state=p.get("scene_state"), turn_plan=_prepare_turn_plan(p, cards),
                                                    response_language=language))
    except Exception as e:
        print("actor retry failed:", repr(e), file=sys.stderr, flush=True)
        raise RuntimeError("模型暂时没有返回内容，请稍后重试。")
    if not text:
        print("actor retry returned empty", file=sys.stderr, flush=True)
        raise RuntimeError("模型暂时没有返回内容，请稍后重试。")
    return text

def ev_continue(ev):
    """场景继续：真实追加一条用户侧 *剧情继续*，再让角色接着演。"""
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    language = _ensure_world_language(p, ev.get("locale"))
    user_msg = _msg("user", ev.get("text") or ("*Continue the story.*" if language == "en" else "*剧情继续*"))
    p["story"].append(user_msg)
    cards, wbs, persona, note = _loadout(p)
    turn_plan = _prepare_turn_plan(p, cards)
    continue_note = _continue_note(note, language)
    reply = actor.perform(cards, wbs, persona, p["story"], continue_note,
                          model=_active_model(), story_state=p.get("story_state"),
                          scene_state=p.get("scene_state"), turn_plan=turn_plan,
                          response_language=language)
    reply = _ensure_actor_reply(p, cards, wbs, persona, continue_note, reply)
    _raise_if_generation_cancelled(ev)
    m = _msg("char", reply)
    p["story"].append(m)
    save_production(p)
    _schedule_story_state(p["id"])
    _schedule_scene_state(p["id"])
    return {"reply": reply, "user_message": user_msg, "message": m, "production_id": p["id"]}


def _compact_story_context(card, story, max_turns=8, response_language="zh"):
    lines = []
    en = _locale_code(response_language) == "en"
    cname = card.get("name", "Character" if en else "角色")
    for m in (story or [])[-max_turns:]:
        who = ("User" if en else "用户") if m.get("role") == "user" else cname
        text = (m.get("text") or "").strip().replace("\r\n", "\n")
        lines.append(f"{who}: {text[:700]}")
    return "\n".join(lines)


def _parse_suggestions(raw):
    raw = (raw or "").strip()
    suggestions = []
    try:
        data = json.loads(raw)
    except Exception:
        start, end = raw.find("["), raw.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(raw[start:end + 1])
            except Exception:
                data = None
        else:
            data = None
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                item = item.get("text") or item.get("reply") or item.get("content")
            x = _normalize_actor_reply(str(item or ""))
            if x:
                suggestions.append(x)
        return suggestions

    # Fallback for older models: accept only explicit bullet/numbered items.
    # Never split plain prose by line, otherwise one incomplete answer becomes 3 fake suggestions.
    for ln in raw.splitlines():
        x = ln.strip()
        if not x:
            continue
        item = None
        if x.startswith("- "):
            item = x[2:].strip()
        elif len(x) >= 2 and x[0].isdigit() and x[1] in ".、)）":
            item = x[2:].strip()
        if item:
            item = _normalize_actor_reply(item)
            if item:
                suggestions.append(item)
    return suggestions if len(suggestions) >= 3 else []


def ev_suggest(ev):
    """根据当前上下文，生成 3 条用户可选回复，供用户点选填入输入框。不修改 story。"""
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    language = _ensure_world_language(p, ev.get("locale"))
    en = language == "en"
    cards, wbs, persona, note = _loadout(p)
    lore = actor.select_lore(wbs, p["story"])
    lore_txt = "\n".join("- " + (e.get("content") or "")[:500] for e in lore[:4])
    persona_txt = ""
    if persona:
        persona_txt = (f"Name: {persona.get('name','')}\nDescription: {persona.get('description','')[:500]}" if en else
                       f"名字：{persona.get('name','')}\n描述：{persona.get('description','')[:500]}")
    primary = cards[0] if cards else {}
    ctx = _compact_story_context(primary, p["story"], response_language=language)
    if en:
        prompt = f"""# Character
Name: {primary.get('name','')}
Personality: {(primary.get('personality') or '')[:700]}
Scenario: {(primary.get('scenario') or '')[:700]}

# User persona
{persona_txt or '(Not set)'}

# Relevant world lore
{lore_txt or '(None)'}

# Recent story
{ctx}

Write exactly three complete messages the user could send next. Every option must respond directly to the final character message above.
Use three distinct directions:
1. Emotional response: engage with the character's current feeling or attitude.
2. Character interaction: ask, test, approach, offer, or act in a way that develops the relationship.
3. Plot movement: take an action, change the scene, or trigger the next event.

Format rules:
{actor.user_input_format_rules(language)}
- Make every option specific to this story rather than a reusable template.
- Do not invent intimacy, shared history, physical contact, or facts that have not appeared.
- Output only a valid JSON array containing exactly three strings. No Markdown, numbering, or explanation.
- Example: ["*I stop beside the stone steps and lower my voice.*\n\n「What would you like me to call you?」", "Second complete reply", "Third complete reply"]
"""
        system = "You generate smart reply options for a roleplay scene. Write only the user's next sendable messages, grounded in the current story, in English."
        repair_system = "Output only a valid JSON array containing exactly three English strings. No Markdown or explanation."
        repair_user = "Rewrite the content below as three complete messages the user can send. Return only a valid JSON array; do not truncate any item.\n\n"
    else:
        prompt = f"""# 角色
名字：{primary.get('name','')}
性格：{(primary.get('personality') or '')[:700]}
场景：{(primary.get('scenario') or '')[:700]}

# 用户扮演者
{persona_txt or '（未设置）'}

# 相关世界设定
{lore_txt or '（无）'}

# 最近剧情
{ctx}

请给出 3 条用户接下来可直接发送的完整回复，必须紧扣【最近剧情】最后一条角色回复。
三条方向不同：
1. 情绪回应：接住角色此刻情绪或态度。
2. 人物互动：用靠近、追问、试探、递动作等方式推进两人关系。
3. 剧情推进：提出行动、改变场景或触发下一步事件。

规则：
{actor.user_input_format_rules(language)}
- 每条都必须是完整用户输入，不是短句提示；可以包含多段动作、心理和对白。
- 每条都必须能看出它来自当前剧情，不要泛泛模板。
- 不要假定未出现的亲密关系、共同过去、身体接触或剧情事实。
- 只输出 JSON 数组，数组内正好 3 个字符串；不要 Markdown，不要编号，不要解释。
- 示例：["*我在石阶旁停下，放轻声音。*\n\n「那你希望我怎么称呼你？」", "第二条完整回复", "第三条完整回复"]
"""
        system = "你是角色扮演场景的智能回复建议器。你只帮用户写下一句可发送输入。必须结合当前剧情，全部使用简体中文，不要泛泛模板。"
        repair_system = "只输出合法 JSON 数组，正好 3 个简体中文字符串。不要 Markdown，不要解释。"
        repair_user = "把下面内容改写为 3 条完整、可直接发送的简体中文用户回复。只输出合法 JSON 数组，每条必须完整，不能截断。\n\n"
    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    raw = actor.chat(msgs, temperature=0.75, model=_active_model())
    suggestions = _parse_suggestions(raw)
    if not suggestions:
        repair = [
            {"role": "system", "content": repair_system},
            {"role": "user", "content": repair_user + raw},
        ]
        raw = actor.chat(repair, temperature=0.35, model=_active_model())
        suggestions = _parse_suggestions(raw)
    return {"suggestions": suggestions[:3]}


def ev_swipe(ev):
    # 在已有备选回复(alts)间切换 active_alt(非破坏性,dir ∈ -1/+1,边界夹住)。
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    for m in p["story"]:
        if m["id"] == ev["message_id"]:
            alts = m.get("alts") or [m.get("text", "")]
            cur = m.get("active_alt", 0)
            nxt = max(0, min(len(alts) - 1, cur + int(ev.get("dir", 0))))
            m["active_alt"] = nxt
            m["text"] = alts[nxt]
            save_production(p)
            return {"message": m}
    raise ValueError("message not found")


def ev_edit_message(ev):
    """Edit a turn and branch from that point: later turns are discarded.

    Editing in RP is a rewind, not an in-place typo fix. Once a user/char turn changes,
    every later turn was generated from the old text and must be removed so the next
    send/continue starts from the edited position.
    """
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    story = p.get("story") or []
    for i, m in enumerate(story):
        if m.get("id") == ev["message_id"]:
            text = ev.get("text", "")
            m["text"] = text
            alts = m.get("alts")
            if isinstance(alts, list) and alts:
                idx = max(0, min(len(alts) - 1, int(m.get("active_alt", 0))))
                m["active_alt"] = idx
                alts[idx] = text
            else:
                m["alts"] = [text]
                m["active_alt"] = 0
            removed = len(story) - i - 1
            p["story"] = story[:i + 1]
            if m.get("role") == "user" and text.strip():
                _observe_user_language(p, text, ev.get("locale"))
            _mark_story_state_stale(p, "edit_message")
            reply_msg = None
            if ev.get("continue_after") and m.get("role") == "user" and text.strip():
                cards, wbs, persona, note = _loadout(p)
                reply = _ensure_actor_reply(p, cards, wbs, persona, note, _perform_into(p))
                _raise_if_generation_cancelled(ev)
                reply_msg = _msg("char", reply)
                p["story"].append(reply_msg)
                _schedule_story_state(p["id"])
                _schedule_scene_state(p["id"])
            save_production(p)
            return {"message": m, "reply": reply_msg, "story": p["story"], "truncated": removed}
    raise ValueError("message not found")


# ---------- Q_B：合并写入 + 生涯年表审计 ----------
# 越演越懂你的引擎：learn/reflect 不再尾部堆流水账,而是①把新学到的**合并进「我对你的了解」**
# (有界、去重、精化——actor.merge_knows)②在「成长记」记一行审计(生涯年表的资产)。
# 「我对你的了解」供主理人推荐与故事档案展示；不注入故事正文生成。
KNOWS_PLACEHOLDER = "- （还不了解你。等我们演几场，我会把你的口味记到这里。）"
_ACTOR_SELF_LOCK = threading.RLock()


def _write_actor_self(md):
    rt = os.path.join(STATE, "actor_self.md")
    tmp = rt + ".tmp." + secrets.token_hex(4)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        os.replace(tmp, rt)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def _replace_section(md, key, body_lines):
    """把 md 中标题含 key 的一级段落正文替换为 body_lines（保留标题 + 前后空行）。"""
    lines, out, i, n, done = md.splitlines(), [], 0, len(md.splitlines()), False
    while i < n:
        line = lines[i]
        if not done and line.startswith("# ") and key in line:
            out += [line, ""] + list(body_lines)
            i += 1
            while i < n and not lines[i].startswith("# "):
                i += 1
            if i < n:
                out.append("")
            done = True
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _merge_into_knows(addition):
    """把新学到的并进「我对你的了解」段（合并、去重、有界），写回，返回合并后清单。"""
    md = actor_self_text()
    merged = actor.merge_knows(parse_actor_self(md)[1], addition)
    body = ["- " + k for k in merged] if merged else [KNOWS_PLACEHOLDER]
    _write_actor_self(_replace_section(md, "我对你的了解", body))
    return merged


def _append_growth(meta, change, ts=None):
    """在「成长记」尾追加**一行**生涯年表审计（成长记是最后一段，追加到尾即落在它下面）。
    change 可能是多行（reflect 蒸馏出多条）——折成一行（`；` 连、去 bullet），否则年表会裂成多条、掉日期。"""
    stamp = time.strftime("%Y-%m-%d", time.localtime(ts or time.time()))
    change = "；".join(s.strip().lstrip("-•").strip()
                       for s in str(change).splitlines() if s.strip())
    meta = " ".join(str(meta).split())
    line = f"- {stamp} {meta} → {change}"
    _write_actor_self(actor_self_text().rstrip() + "\n" + line + "\n")
    return line


def _record_actor_learning(change, reason, ts=None):
    with _ACTOR_SELF_LOCK:
        merged = _merge_into_knows(change)
        audit = _append_growth(reason, change, ts)
    return merged, audit


def ev_actor_grow(ev):
    """learn：把对用户的了解/演法调整**合并进「我对你的了解」** + 记一笔生涯年表（带人话理由）。Q_B。"""
    change = ev.get("change", "")
    merged, audit = _record_actor_learning(
        change, ev.get("reason", "") or "(无理由)", ev.get("ts"))
    return {"ok": True, "knows": merged, "appended": audit}


def _json_from_model_text(out):
    try:
        return json.loads(out)
    except Exception:
        start, end = out.find("{"), out.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(out[start:end + 1])
            except Exception:
                return {}
    return {}


def _card_names(cards):
    return [str(c.get("name") or "角色").strip() for c in cards if str(c.get("name") or "").strip()]




def _closest_card_name(value, names):
    s = str(value or "").strip()
    if not s:
        return ""
    if s in names:
        return s
    for n in names:
        if n and (n in s or s in n):
            return n
    aliases = {"德尔特": "德尔塔", "Delta": "德尔塔", "Alpha": "阿尔法", "Beta": "贝塔", "Gamma": "伽玛", "Epsilon": "伊普西龙", "Zeta": "泽塔", "Eta": "伊塔"}
    a = aliases.get(s)
    return a if a in names else ""

def _normalize_scene_state(raw, cards, response_language="zh"):
    if not isinstance(raw, dict):
        raw = {}
    names = _card_names(cards)

    def text(key, fallback=""):
        return str(raw.get(key) or fallback or "").strip()[:160]

    def arr(key, fallback=None, limit=8, normalize_names=False):
        vals = raw.get(key)
        if vals is None:
            vals = fallback or []
        if isinstance(vals, str):
            vals = [vals]
        out = []
        for v in vals or []:
            x = str(v).strip().lstrip("-•").strip()
            if normalize_names:
                x = _closest_card_name(x, names)
            if x and x not in out:
                out.append(x[:120])
        return out[:limit]

    present = arr("present_characters", normalize_names=True)
    nearby = arr("nearby_characters", normalize_names=True)
    hidden = arr("hidden_characters", normalize_names=True)
    if not present and names:
        present.append(names[0])
    unknown = "Unspecified" if _locale_code(response_language) == "en" else "未明确"
    return {
        "location": text("location", unknown),
        "time": text("time", unknown),
        "mood": text("mood", unknown),
        "current_focus": text("current_focus"),
        "present_characters": present[:8],
        "nearby_characters": nearby[:8],
        "hidden_characters": hidden[:8],
        "open_threads": arr("open_threads", limit=10),
        "updated_at": int(time.time()),
    }


def _scene_story_excerpt(p, max_items=12, response_language=None):
    cards, _, _, _ = _loadout(p)
    language = response_language or _ensure_world_language(p)
    en = language == "en"
    cname = "/".join(c.get("name", "Character" if en else "角色") for c in cards[:4]) or ("Character" if en else "角色")
    lines = []
    for m in (p.get("story") or [])[-max_items:]:
        who = ("User" if en else "用户") if m.get("role") == "user" else cname
        text = (m.get("text") or "").strip().replace("\r\n", "\n")
        if text:
            lines.append(f"{who}: {text[:700]}")
    return "\n".join(lines)


def _build_turn_plan(p, cards):
    if len(cards) <= 1:
        return {}
    language = _ensure_world_language(p)
    en = language == "en"
    names = _card_names(cards)
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
    user = json.dumps({
        "characters": names,
        "scene_state": p.get("scene_state") or {},
        "story_state": p.get("story_state") or {},
        "response_language": language,
        "recent_story": _scene_story_excerpt(p, response_language=language),
    }, ensure_ascii=False)
    out = actor.chat([{"role": "system", "content": sys}, {"role": "user", "content": user}],
                     temperature=0.15, model=_active_model()).strip()
    raw = _json_from_model_text(out)

    def clean_arr(v, limit=6):
        if isinstance(v, str):
            v = [v]
        out = []
        for x in v or []:
            s = str(x).strip().lstrip("-•").strip()
            fixed = _closest_card_name(s, names) or s[:120]
            if fixed and fixed not in out:
                out.append(fixed)
        return out[:limit]

    primary = _closest_card_name(raw.get("primary_speaker"), names)
    return {
        "primary_speaker": primary,
        "supporting_characters": clean_arr(raw.get("supporting_characters")),
        "silent_characters": clean_arr(raw.get("silent_characters")),
        "narration_goal": str(raw.get("narration_goal") or "").strip()[:180],
        "do_not": clean_arr(raw.get("do_not")),
    }


def _prepare_turn_plan(p, cards):
    try:
        return _build_turn_plan(p, cards)
    except Exception:
        return {}


def _update_scene_state(p):
    cards, _, _, _ = _loadout(p)
    if not cards:
        return p.get("scene_state") or {}
    revision = _story_revision(p)
    language = _ensure_world_language(p)
    en = language == "en"
    sys = ((
        "You are the continuity recorder for an interactive story. Update the current scene state from the recent story and write all textual values in English. "
        "Record only events that clearly happened or are strongly established; do not add literary commentary. Output strict JSON with only location, time, mood, current_focus, present_characters, nearby_characters, hidden_characters, and open_threads. "
        "present means clearly onstage now; nearby means close enough to enter naturally; hidden means offstage or not yet revealed."
    ) if en else (
        "你是互动故事的场记。根据最近剧情更新当前场景状态，所有文本值使用简体中文。"
        "只记录已经明确发生或强烈成立的内容，不要写文学点评。"
        "输出严格 JSON，字段只有 location、time、mood、current_focus、present_characters、"
        "nearby_characters、hidden_characters、open_threads。"
        "present=此刻明确在场；nearby=附近或可自然引入；hidden=暂不出场/未显身。"
    ))
    user = json.dumps({
        "characters": _card_names(cards),
        "previous_scene_state": p.get("scene_state") or {},
        "response_language": language,
        "recent_story": _scene_story_excerpt(p, response_language=language),
    }, ensure_ascii=False)
    out = actor.chat([{"role": "system", "content": sys}, {"role": "user", "content": user}],
                     temperature=0.1, model=_memory_model()).strip()
    state = _normalize_scene_state(_json_from_model_text(out), cards, language)
    updated = _merge_production_fields(
        p["id"], expected_story_revision=revision, scene_state=state)
    if updated is None:
        return p.get("scene_state") or {}
    p["scene_state"] = state
    return state


def _maybe_update_scene_state(pid):
    p = load_production(pid)
    if not p:
        return
    try:
        _update_scene_state(p)
    except Exception:
        pass


def _schedule_scene_state(pid):
    threading.Thread(target=_maybe_update_scene_state, args=(pid,), daemon=True).start()


def _world_turns(story):
    return sum(1 for m in story or [] if m.get("role") == "user")


STORY_STATE_CHUNK_TOKENS = int(os.environ.get("TAVERN_STORY_STATE_CHUNK_TOKENS", "7000"))
STORY_STATE_OVERLAP_TOKENS = int(os.environ.get("TAVERN_STORY_STATE_OVERLAP_TOKENS", "800"))


def _story_lines_for_state(p, from_tokens=0, to_tokens=None,
                           max_items=140, max_chars=42000):
    """Return one bounded story chunk for story_state merging.

    The original story is never modified. The chunk boundaries are token-estimate
    based, with a caller-provided overlap handled outside this function.
    """
    cards, _, _, _ = _loadout(p)
    cname = "/".join(c.get("name", "角色") for c in cards[:4]) or "角色"
    start_at = max(0, int(from_tokens or 0))
    stop_at = int(to_tokens) if to_tokens is not None else None
    lines = []
    total_chars = 0
    seen_tokens = 0
    for m in (p.get("story") or []):
        text = (m.get("text") or "").strip().replace("\r\n", "\n")
        msg_tokens = _estimate_text_tokens(text)
        next_tokens = seen_tokens + msg_tokens
        if next_tokens <= start_at:
            seen_tokens = next_tokens
            continue
        if stop_at is not None and seen_tokens >= stop_at:
            break
        if text:
            who = "用户" if m.get("role") == "user" else cname
            line = f"{who}: {text[:1400]}"
            lines.append(line)
            total_chars += len(line)
        seen_tokens = next_tokens
        if len(lines) >= max_items or total_chars >= max_chars:
            break
    return "\n".join(lines)


def _estimate_text_tokens(text):
    """Cheap trigger-only token estimate: CJK ~= 1 token, other text ~= 4 chars/token."""
    cjk = 0
    other = 0
    for ch in text or "":
        if "一" <= ch <= "鿿" or "぀" <= ch <= "ヿ" or "가" <= ch <= "힯":
            cjk += 1
        elif not ch.isspace():
            other += 1
    return cjk + max(1, (other + 3) // 4) if (cjk or other) else 0


def _story_token_estimate(story):
    return sum(_estimate_text_tokens(m.get("text") or "") for m in story or [])


def _clip_memory_text(value, limit):
    text = str(value or "").strip().lstrip("-•").strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    # Drop obvious generated loops before they become permanent memory.
    for pat in ("痛苦煎熬", "天道好轮回", "源头治理", "越来越"):
        if text.count(pat) >= 4:
            i = text.find(pat)
            text = text[:i + len(pat)]
            break
    return text[:limit].rstrip()


def _normalize_story_state(raw, turns, source_tokens):
    if not isinstance(raw, dict):
        raw = {}

    limits = {
        "timeline": (20, 120),
        "facts": (20, 120),
        "open_threads": (20, 140),
        "relationships": (20, 140),
        "user_state": (12, 140),
        "scene_anchor": (10, 140),
        "objects": (12, 140),
        "secrets": (12, 140),
        "style_notes": (8, 120),
    }

    def arr(key):
        max_items, max_len = limits[key]
        vals = raw.get(key) or []
        if isinstance(vals, str):
            vals = [vals]
        out = []
        for v in vals:
            x = _clip_memory_text(v, max_len)
            if x and x not in out:
                out.append(x)
            if len(out) >= max_items:
                break
        return out

    def _arr_from_value(obj, key, limit=8, max_len=150):
        vals = obj.get(key) or []
        if isinstance(vals, str):
            vals = [vals]
        out = []
        for v in vals:
            x = _clip_memory_text(v, max_len)
            if x and x not in out:
                out.append(x)
            if len(out) >= limit:
                break
        return out

    def dict_arr(key, max_keys=12, item_limit=8):
        vals = raw.get(key) or {}
        out = {}
        if isinstance(vals, list):
            for item in vals:
                if isinstance(item, dict):
                    name = str(item.get("name") or item.get("角色") or item.get("character") or "").strip()
                    notes = item.get("state") or item.get("notes") or item.get("items") or item.get("状态") or []
                    if name:
                        out[name[:40]] = _arr_from_value({"_": notes}, "_", item_limit)
        elif isinstance(vals, dict):
            for name, notes in vals.items():
                n = str(name).strip()[:40]
                if n:
                    out[n] = _arr_from_value({"_": notes}, "_", item_limit)
        clean = {}
        for name, notes in out.items():
            if notes:
                clean[name] = notes
            if len(clean) >= max_keys:
                break
        return clean

    state = {
        "timeline": arr("timeline"),
        "facts": arr("facts"),
        "open_threads": arr("open_threads"),
        "relationships": arr("relationships"),
        "character_state": dict_arr("character_state"),
        "user_state": arr("user_state"),
        "scene_anchor": arr("scene_anchor"),
        "objects": arr("objects"),
        "secrets": arr("secrets"),
        "style_notes": arr("style_notes"),
        "turns": turns,
        "source_tokens": source_tokens,
        "updated_at": int(time.time()),
    }
    return state


def _story_state_has_memory(state):
    return any(state.get(k) for k in (
        "timeline", "facts", "open_threads", "relationships", "character_state",
        "user_state", "scene_anchor", "objects", "secrets", "style_notes"
    ))


def _merge_story_state_chunk(prev, chunk, turns, from_tokens, to_tokens, response_language="zh"):
    language = _locale_code(response_language)
    if language == "en":
        sys_prompt = (
            "You are the high-fidelity continuity recorder for an interactive story. Merge previous_state and new_story_chunk into an updated story ledger. "
            "Write every textual value in English, translating older ledger values when necessary while preserving names and facts. Record only facts, relationships, secrets, objects, open threads, and style information that affect future continuation. "
            "Do not add literary commentary or infer events that did not happen. Output strict JSON using only timeline, facts, open_threads, relationships, character_state, user_state, scene_anchor, objects, secrets, and style_notes. "
            "Keep entries short, concrete, unique, and non-prose. Keep at most 6 entries per array and at most 4 characters in character_state. Keep timeline/facts under 20 words and relationships/open_threads under 28 words. "
            "If new_story_chunk is non-empty, never return an entirely empty JSON object."
        )
    else:
        sys_prompt = (
            "你是互动故事的高保真场记。把 previous_state 与 new_story_chunk 合并成新的剧情账本，所有文本值使用简体中文；必要时翻译旧账本内容，同时保留姓名与事实。"
            "只记录会影响后续续写的事实、关系、秘密、物件、伏笔和风格；不要文学点评，不猜测未发生内容。"
            "输出严格 JSON，对象字段只能是 timeline、facts、open_threads、relationships、character_state、"
            "user_state、scene_anchor、objects、secrets、style_notes。"
            "所有数组条目必须短而具体，禁止长篇散文，禁止重复。"
            "每个数组最多保留 6 条；character_state 最多 4 个角色。"
            "timeline/facts 每条不超过 60 个汉字；relationships/open_threads 每条不超过 80 个汉字；"
            "character_state 每个角色最多 6 条，每条不超过 80 个汉字。"
            "如果 new_story_chunk 非空，严禁返回全空 JSON。"
        )
    user = json.dumps({
        "previous_state": prev or {},
        "new_story_chunk": chunk,
        "response_language": language,
        "range": {
            "from_tokens": from_tokens,
            "to_tokens": to_tokens,
            "turns": turns,
        },
    }, ensure_ascii=False)
    out = ""
    last_error = None
    for mem_model in _memory_models():
        try:
            out = actor.chat([
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user},
            ], temperature=0.1, model=mem_model, max_tokens=6000).strip()
            if out:
                break
        except Exception as e:
            last_error = e
            print("story_state chunk model failed with %s:" % mem_model.get("model"), repr(e), file=__import__("sys").stderr, flush=True)
    if not out:
        print("story_state chunk model failed:", repr(last_error), file=__import__("sys").stderr, flush=True)
        return None

    try:
        raw = _json_from_model_text(out)
    except Exception:
        raw = None
        last_error = None
        for mem_model in _memory_models():
            try:
                repair_prompt = ((
                    "Repair the user's content into strict JSON and write all textual values in English. Output only a JSON object using timeline, facts, open_threads, relationships, character_state, user_state, scene_anchor, objects, secrets, and style_notes."
                ) if language == "en" else (
                    "把用户给出的内容修复为严格 JSON，所有文本值使用简体中文。只输出 JSON 对象。"
                    "字段只能是 timeline、facts、open_threads、relationships、character_state、"
                    "user_state、scene_anchor、objects、secrets、style_notes。"
                ))
                repair = actor.chat([
                    {"role": "system", "content": repair_prompt},
                    {"role": "user", "content": out[:9000]},
                ], temperature=0.0, model=mem_model, max_tokens=2500).strip()
                raw = _json_from_model_text(repair)
                break
            except Exception as e:
                last_error = e
                print("story_state chunk parse repair failed with %s:" % mem_model.get("model"), repr(e), file=__import__("sys").stderr, flush=True)
        if raw is None:
            print("story_state chunk parse failed:", repr(last_error), file=__import__("sys").stderr, flush=True)
            return None
    state = _normalize_story_state(raw, turns, to_tokens)
    state["response_language"] = language
    if not _story_state_has_memory(state):
        print("story_state chunk empty; keeping previous memory", file=__import__("sys").stderr, flush=True)
        return None
    return state


def _summarize_story_state(p, force_full=False):
    story = p.get("story") or []
    turns = _world_turns(story)
    source_tokens = _story_token_estimate(story)
    prev = p.get("story_state") or {}
    language = _ensure_world_language(p)
    done = 0 if force_full else int(prev.get("source_tokens") or 0)
    if done >= source_tokens:
        return prev

    state = {} if force_full else dict(prev)
    cursor = done
    while cursor < source_tokens:
        chunk_from = 0 if cursor == 0 else max(0, cursor - STORY_STATE_OVERLAP_TOKENS)
        chunk_to = min(source_tokens, max(cursor + STORY_STATE_CHUNK_TOKENS, STORY_STATE_CHUNK_TOKENS))
        chunk = _story_lines_for_state(p, from_tokens=chunk_from, to_tokens=chunk_to)
        if not chunk.strip():
            break
        merged = _merge_story_state_chunk(state, chunk, turns, chunk_from, chunk_to, language)
        if not merged:
            break
        state = merged
        cursor = chunk_to
        p["story_state"] = state
        _merge_production_fields(p["id"], story_state=state)

    return state if _story_state_has_memory(state) else (prev if prev else {})

def ev_story_state(ev):
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    if ev.get("refresh"):
        return {"story_state": _summarize_story_state(p, force_full=True), "production_id": p["id"]}
    return {"story_state": p.get("story_state") or {}, "production_id": p["id"]}


STORY_STATE_TRIGGER_TURNS = int(os.environ.get("TAVERN_STORY_STATE_TRIGER_TURNS", "15"))
STORY_STATE_DELTA_TURNS = int(os.environ.get("TAVERN_STORY_STATE_DELTA_TURNS", "15"))


def _maybe_auto_story_state(pid):
    p = load_production(pid)
    if not p:
        return
    story = p.get("story") or []
    turns = _world_turns(story)
    prev = p.get("story_state") or {}
    done_turns = int(prev.get("turns") or 0)

    turn_due = turns >= STORY_STATE_TRIGGER_TURNS and (
        not done_turns or turns - done_turns >= STORY_STATE_DELTA_TURNS
    )
    if not turn_due:
        return
    try:
        _summarize_story_state(p)
    except Exception:
        pass


def _schedule_story_state(pid):
    threading.Thread(target=_maybe_auto_story_state, args=(pid,), daemon=True).start()


def _reflect_production(p):
    """复盘一场戏 → 蒸馏偏好 → **合并进「我对你的了解」** + 记生涯年表。explicit + auto 共用。"""
    story = p.get("story", [])
    if sum(1 for m in story if m.get("role") == "user") < 2:
        return {"learned": None, "reason": "戏太短，没什么可学的"}
    cards, _, _, _ = _loadout(p)
    card = {"name": "、".join(c.get("name", "角色") for c in cards) or "角色"}
    learned = actor.reflect_on_play(card, story, actor_self_text(), model=_active_model())
    if not learned:
        return {"learned": None, "reason": "这场没看出明显偏好"}
    merged, _ = _record_actor_learning(
        learned, f"（复盘「{p.get('name', '')}」）")
    return {"learned": learned, "knows": merged, "production": p.get("name")}


def ev_reflect(ev):
    """复盘一场戏（显式触发）→ 蒸馏 + 合并进技艺层。「越演越懂你」的结构化触发（不靠 agent 临场）。"""
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    return _reflect_production(p)


def ev_reflect_preview(ev):
    """只预览复盘会学到什么，不写 actor_self.md。"""
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    story = p.get("story", [])
    if sum(1 for m in story if m.get("role") == "user") < 2:
        return {"learned": None, "reason": "戏太短，没什么可学的", "production": p.get("name")}
    cards, _, _, _ = _loadout(p)
    card = {"name": "、".join(c.get("name", "角色") for c in cards) or "角色"}
    learned = actor.reflect_on_play(card, story, actor_self_text(), model=_active_model())
    if not learned:
        return {"learned": None, "reason": "这场没看出足够明确的用户偏好", "production": p.get("name")}
    return {"learned": learned, "production": p.get("name"), "write": False}


def ev_set_persona(ev):
    persona = {"name": ev.get("name", "我"), "description": ev.get("description", "")}
    pid = ev.get("production_id")
    if pid:
        p = load_production(pid)
        if not p:
            raise ValueError("production not found")
        p["persona"] = persona
        save_production(p)
        return {"persona": persona, "production": p}
    _write(os.path.join(STATE, "persona.json"), persona)
    return {"persona": persona}


def ev_set_note(ev):
    """设/清本剧组的作者注释(导演提示)——当前场景方向,注入贴近生成点。
    结构化的「跟搭子说一句就长期生效」:agent 识别『回复短点/别用现代词』→ set_note。
    设计 canon:不暴露 UI 旋钮,由对话/agent 设。空串=清除。"""
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    p["author_note"] = (ev.get("note") or "").strip()
    save_production(p)
    return {"production_id": p["id"], "author_note": p["author_note"]}


# ---------- 大模型配置 ----------
# 用户自配的大模型（OpenAI-compatible 一种协议）。添加只走「对主理人说」→ CLI → 这里的 event；
# reader 界面只做管理（选中/删除）+ 教育。key 只落 server 端 state 文件（0600），
# 任何读端点一律脱敏——bridge「creds 只在 server 端，页面永不见」原则的延伸。
MODELS_PATH = os.path.join(STATE, "model_configs.json")

CLAWLING_MODELS = [
    "deepseek-v4-flash",
]


def _clawling_model_id(model_name):
    return "builtin" if model_name == actor.MODEL_NAME else "clawling:" + model_name


def _clawling_model_name(model_id):
    if model_id == "builtin":
        return actor.MODEL_NAME
    if model_id.startswith("clawling:"):
        return model_id.split(":", 1)[1]
    return ""


def _models_state():
    return _read(MODELS_PATH, {"configs": [], "active": "builtin"})


def _save_models(s):
    _write(MODELS_PATH, s)
    try:
        os.chmod(MODELS_PATH, 0o600)  # 存明文 key,别让同机其他用户读
    except OSError:
        pass


HERMES_CONFIG_PATH = os.environ.get("HERMES_CONFIG_PATH", "/opt/data/config.yaml")
MEMORY_PRIMARY_MODEL = "deepseek-v4-flash"


def _memory_model():
    """剧情账本固定使用 DeepSeek V4 Flash，不跟随演绎模型切换。"""
    return {
        "base": actor.MODEL_BASE,
        "key": actor.MODEL_KEY,
        "model": MEMORY_PRIMARY_MODEL,
    }


def _clawling_memory_fallbacks(primary):
    """Read Clawling fallback candidates from Hermes config, never from code constants."""
    try:
        with open(HERMES_CONFIG_PATH, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except (OSError, ValueError, TypeError, yaml.YAMLError) as e:
        print("memory fallback config unavailable:", repr(e), file=sys.stderr, flush=True)
        return []

    candidates = []
    seen = {str(primary.get("model") or "").strip()}

    def add(model, base=None):
        name = str(model or "").strip()
        if not name or name in seen:
            return
        seen.add(name)
        candidates.append({
            "base": str(base or actor.MODEL_BASE).strip() or actor.MODEL_BASE,
            "key": actor.MODEL_KEY,
            "model": name,
        })

    for item in config.get("fallback_providers") or []:
        if not isinstance(item, dict) or str(item.get("provider") or "").lower() != "clawling":
            continue
        add(item.get("model"), item.get("base_url"))

    # Configured Clawling catalog is the secondary source when no explicit
    # fallback order exists. Dict order is preserved by YAML/Python.
    if not candidates:
        clawling = ((config.get("providers") or {}).get("clawling") or {})
        for model in (clawling.get("models") or {}):
            add(model, clawling.get("api"))

    limit = max(1, int(os.environ.get("TAVERN_MEMORY_FALLBACK_LIMIT", "3")))
    return candidates[:limit]


def _memory_models():
    """Fixed primary plus config-driven Clawling fallbacks for story compression."""
    primary = _memory_model()
    return [primary, *_clawling_memory_fallbacks(primary)]


def _active_model():
    """当前生效模型。builtin/clawling:* 共用内置 Clawling key；自配模型走明文配置。"""
    s = _models_state()
    aid = s.get("active") or "builtin"
    cname = _clawling_model_name(aid)
    if cname in CLAWLING_MODELS:
        if aid == "builtin" and cname == actor.MODEL_NAME:
            return None
        return {"base": actor.MODEL_BASE, "key": actor.MODEL_KEY, "model": cname}
    for c in s["configs"]:
        if c["id"] == aid:
            return {"base": c["base"], "key": c["key"], "model": c["model"]}
    return None  # active 悬空(配置已删) → 回落默认 Clawling 模型


def _mask_key(k):
    return ("**" + k[-4:]) if len(k or "") >= 8 else "**"


def _public_models():
    """脱敏配置列表（reader / CLI list 用）。Clawling 内置模型恒在首组、不可删。"""
    s = _models_state()
    builtin_configs = [{
        "id": _clawling_model_id(m),
        "name": m,
        "model": m,
        "builtin": True,
        "provider": "Clawling",
        "default": m == actor.MODEL_NAME,
        "key_set": bool(actor.MODEL_KEY),
    } for m in CLAWLING_MODELS]
    custom_configs = [{"id": c["id"], "name": c["name"], "model": c["model"],
                       "base": c["base"], "key_masked": _mask_key(c.get("key")),
                       "added_at": c.get("added_at")} for c in s["configs"]]
    configs = builtin_configs + custom_configs
    aid = s.get("active") or "builtin"
    if not any(c["id"] == aid for c in configs):
        aid = "builtin"
    return {"configs": configs, "active": aid}


def _ping_or_raise(ov):
    """实测一份配置，失败转成人话错误（CLI/reader 直接给用户看）。"""
    try:
        return actor.ping(ov)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:200]
        hint = {401: "（key 无效或没权限）", 404: "（base_url 或 model 名不对）",
                429: "（限流/欠费）"}.get(e.code, "")
        raise ValueError(f"实测失败 HTTP {e.code}{hint}：{body}")
    except Exception as e:  # noqa: BLE001 — DNS/超时/拒连等,统一转人话
        raise ValueError(f"实测失败：{e}")


def ev_model_add(ev):
    """加一份用户自配模型：先实测（1 次极小请求），通了才落盘并自动切换。
    同名 = 更新（主理人「再配一次」= 换 key/model，id 不变）。"""
    name = (ev.get("name") or "").strip()
    base = (ev.get("base") or "").strip().rstrip("/")
    model_name = (ev.get("model") or "").strip()
    key = (ev.get("key") or "").strip()
    if not (name and base and model_name and key):
        raise ValueError("缺参数：name / base / model / key 都要")
    if name == "内置模型":
        raise ValueError("这个名字留给内置配置了，换一个")
    ms = _ping_or_raise({"base": base, "key": key, "model": model_name})
    s = _models_state()
    cfg = next((c for c in s["configs"] if c["name"] == name), None)
    if cfg:
        cfg.update({"base": base, "model": model_name, "key": key})
    else:
        cfg = {"id": "m_" + secrets.token_hex(3), "name": name, "base": base,
               "model": model_name, "key": key, "added_at": int(time.time())}
        s["configs"].append(cfg)
    s["active"] = cfg["id"]
    _save_models(s)
    return {"config": {"id": cfg["id"], "name": name, "model": model_name,
                       "key_masked": _mask_key(key)},
            "active": cfg["id"], "latency_ms": ms}


def _find_config(s, ref):
    """按 id 或名字找配置（CLI 让主理人用名字，reader 用 id）。"""
    return next((c for c in s["configs"] if c["id"] == ref or c["name"] == ref), None)


def ev_model_use(ev):
    ref = ev.get("id") or ""
    s = _models_state()
    cname = _clawling_model_name(ref)
    if ref in ("内置模型", actor.MODEL_NAME):
        ref = "builtin"
        cname = actor.MODEL_NAME
    if cname in CLAWLING_MODELS:
        s["active"] = _clawling_model_id(cname)
        _save_models(s)
        return {"active": s["active"], "name": cname}
    cfg = _find_config(s, ref)
    if not cfg:
        raise ValueError("没有这份配置：%s" % ref)
    s["active"] = cfg["id"]
    _save_models(s)
    return {"active": cfg["id"], "name": cfg["name"]}


def ev_model_delete(ev):
    ref = ev.get("id") or ""
    if ref in ("builtin", "内置模型"):
        raise ValueError("内置模型不可删除")
    s = _models_state()
    cfg = _find_config(s, ref)
    if not cfg:
        raise ValueError("没有这份配置：%s" % ref)
    s["configs"] = [c for c in s["configs"] if c["id"] != cfg["id"]]
    if s.get("active") == cfg["id"]:
        s["active"] = "builtin"  # 删掉在用的 → 回落内置模型
    _save_models(s)
    return {"deleted": cfg["id"], "name": cfg["name"], "active": s["active"]}


def ev_model_test(ev):
    """实测某份已存配置（或 builtin）。返回耗时；失败走统一人话错误。"""
    ref = ev.get("id") or "builtin"
    if ref in ("builtin", "内置模型"):
        ov = None
    else:
        s = _models_state()
        cfg = _find_config(s, ref)
        if not cfg:
            raise ValueError("没有这份配置：%s" % ref)
        ov = {"base": cfg["base"], "key": cfg["key"], "model": cfg["model"]}
    ms = _ping_or_raise(ov)
    return {"latency_ms": ms, **actor.model_info(ov)}


def ev_tts_voice_use(ev):
    voice = _save_tts_voice(ev.get("voice"))
    return {"voice": voice, "tts": _tts_settings()}


def ev_tts_preset_settings(ev):
    return {"tts": _save_tts_preset_settings(
        ev.get("voice"), ev.get("speed"), ev.get("instructions"))}


def ev_tts_clone_use(ev):
    return {"tts": _use_tts_clone(ev.get("clone_id"))}


def ev_tts_clone_delete(ev):
    return {"tts": _delete_tts_clone(ev.get("clone_id"))}


EVENTS = {
    "cancel_generation": ev_cancel_generation,
    "import_card": ev_import_card, "import_card_json": ev_import_card_json, "create_card": ev_create_card,
    "import_worldbook": ev_import_worldbook, "attach_worldbook": ev_attach_worldbook,
    "add_lore": ev_add_lore, "update_lore": ev_update_lore, "delete_lore": ev_delete_lore,
    "attach_card": ev_attach_card, "update_cast": ev_update_cast, "detach_card": ev_detach_card, "delete_card": ev_delete_card,
    "create_production": ev_create_production, "create_blank_production": ev_create_blank_production,
    "switch_loadout": ev_switch_loadout,
    "prepare_delete_production": ev_prepare_delete_production,
    "delete_production": ev_delete_production,
    "send_message": ev_send_message,
    "regenerate": ev_regenerate,
    "continue": ev_continue, "suggest": ev_suggest,
    "story_state": ev_story_state,
    "swipe": ev_swipe, "edit_message": ev_edit_message, "actor_grow": ev_actor_grow,
    "reflect": ev_reflect, "reflect_preview": ev_reflect_preview,
    "set_persona": ev_set_persona, "set_note": ev_set_note,
    "model_add": ev_model_add, "model_use": ev_model_use,
    "model_delete": ev_model_delete, "model_test": ev_model_test,
    "tts_voice_use": ev_tts_voice_use,
    "tts_preset_settings": ev_tts_preset_settings,
    "tts_clone_use": ev_tts_clone_use, "tts_clone_delete": ev_tts_clone_delete,
}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", CONTENT_TYPES[".json"])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _audio(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, max-age=3600")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _tts_reference(self, token):
        clone = next((item for item in _tts_clones(_tts_config())
                      if secrets.compare_digest(str(item.get("token") or ""),
                                                str(token or ""))), None)
        if not clone:
            return self._json(404, {"error": "not found"})
        path = _tts_clone_file(clone)
        if not path or not os.path.isfile(path):
            return self._json(404, {"error": "not found"})
        with open(path, "rb") as file:
            body = file.read()
        self.send_response(200)
        self.send_header("Content-Type", clone.get("mime") or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, max-age=300")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _file(self, path):
        if not os.path.isfile(path):
            return self._json(404, {"error": "not found"})
        ext = os.path.splitext(path)[1]
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        # reader 是活件页面、随 agent 迭代频繁更新——禁缓存,否则 WKWebView/WebView2 可能
        # serve 旧 app.js,改动不生效(反馈 2026-06-30「还是不行」的头号嫌疑)。
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _serve_html(self, name, assets):
        # 注入版本化资源引用破 relay 缓存:clawling relay/CDN 把 .js/.css 强制缓存成
        # `public, max-age=2592000, immutable`(30天,覆盖源站 no-store)→ 改动不生效。
        # html 自身是 no-store(relay 透传)永远新,所以给资源 URL 挂 ?v=<token>。
        # 文件名 + 纳秒 mtime + size 做稳定指纹；不能 XOR 秒级 mtime，多文件同秒更新
        # 会彼此抵消，导致 relay 继续命中旧的 immutable 资源。
        try:
            with open(os.path.join(READER, name), encoding="utf-8") as f:
                html = f.read()
        except OSError:
            return self._json(404, {"error": "not found"})
        fingerprint = hashlib.sha256()
        for fn in (name,) + tuple(assets):
            try:
                stat = os.stat(os.path.join(READER, fn))
                fingerprint.update(f"{fn}\0{stat.st_mtime_ns}\0{stat.st_size}\n".encode("utf-8"))
            except OSError:
                fingerprint.update(f"{fn}\0missing\n".encode("utf-8"))
        v = fingerprint.hexdigest()[:12]
        for a in assets:
            # Replace both bare assets and assets that already carry an older
            # cache token, while limiting the match to quoted HTML attributes.
            pattern = r"([\"'])" + re.escape(a) + r"(?:\?v=[^\"']*)?\1"
            html = re.sub(pattern, lambda m: f"{m.group(1)}{a}?v={v}{m.group(1)}", html)
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES[".html"])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


    def _clawchat_redirect(self):
        q = parse_qs(urlparse(self.path).query)
        draft = (q.get("draft", [""])[0] or "").strip()
        uid = agent_user_id()
        if not uid:
            body = f"{app_identity().get('persona_name', '角色')}的 ClawChat 身份还没有就绪。".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        target = f"clawchat://u/{quote(uid)}?chat=1&draft={quote(draft)}"
        js_target = json.dumps(target, ensure_ascii=False)
        safe_target = target.replace("&", "&amp;").replace('"', "&quot;")
        body = f"""<!doctype html>
<html lang=\"zh-CN\"><head><meta charset=\"utf-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>打开{app_identity().get("persona_name", "角色")}</title>
<style>body{{font:15px -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#181611;color:#eee;padding:24px;line-height:1.7}}a{{color:#ff8a3d}}</style>
<script>setTimeout(function(){{ location.href = {js_target}; }}, 30);</script>
</head><body>
<p>正在打开{app_identity().get("persona_name", "角色")}的聊天窗口…</p>
<p><a href=\"{safe_target}\">如果没有自动跳转，点这里继续</a></p>
</body></html>""".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        return self.do_GET()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/clawchat/agent":
            return self._clawchat_redirect()
        if path == "/api/health":
            # model_info 传 active override → health 反映当前实际生效的模型
            return self._json(200, {"ok": True, "dry_run": False, "tts_base": TTS_BASE,
                                    **actor.model_info(_active_model())})
        if path == "/api/models":
            # 大模型配置列表(脱敏,key 永不出 server)——reader 管理面 + CLI model list 共用
            return self._json(200, _public_models())
        if path == "/api/tts/config":
            return self._json(200, _tts_settings())
        if path.startswith("/api/tts/reference/"):
            return self._tts_reference(path.rsplit("/", 1)[-1])
        if path == "/api/cards":
            return self._json(200, {"cards": _list("cards")})
        if path == "/api/worldbooks":
            return self._json(200, {"worldbooks": _list("worldbooks")})
        if path == "/api/library/cards":
            return self._json(200, {"cards": _library_cards()})
        if path == "/api/library/worldbooks":
            return self._json(200, {"worldbooks": _library_worldbooks()})
        if path == "/api/production/worldbooks":
            pid = parse_qs(urlparse(self.path).query).get("production_id", [""])[0]
            return self._json(200, {"worldbooks": _production_worldbooks(pid)})
        if path == "/api/productions":
            return self._json(200, {"productions": _list_productions(),
                                    "active": _get_state().get("active_production_id")})
        if path == "/api/identity":
            return self._json(200, {**app_identity(), "agent_user_id": agent_user_id()})
        if path == "/api/actor":
            # 兼容技能/旧前端的故事档案原文与应用元数据；当前控制台使用轻量 /api/identity。
            return self._json(200, {"actor_self": actor_self_text(), "version": liveware_version(),
                                    "agent_user_id": agent_user_id(),
                                    "actor_url": (f"https://{_actor_host()}/" if _actor_host() else "")})
        if path == "/api/persona":
            # Persona is now scoped to each world. Keep this endpoint for older frontends,
            # but never return the legacy global persona because that causes cross-world bleed.
            return self._json(200, {})
        if path == "/api/actor_card":
            # 演员卡聚合（生涯数值、亲密度、口味、年表），只读。
            # ?lang= 只换 UI 标签(级名/blurb);非 zh 一律走 en 表(回落链对齐 reader)。
            q = parse_qs(urlparse(self.path).query)
            lang = (q.get("lang", ["zh"])[0] or "zh")[:2].lower()
            return self._json(200, actor_card_data(lang))
        # static reader（*.html 走版本化注入,破 relay 的 immutable 缓存）
        rel = path.lstrip("/") or "index.html"
        if rel == "index.html":
            # 一台 server 服务两个活件 app（同 :8799，靠 tunnel 透传的 X-Forwarded-Host 分流）：
            # 控制台 app 的 / → index；演员卡 app（第二个活件卡入口）的 / → actor.html。
            fwd = self.headers.get("X-Forwarded-Host", "") or self.headers.get("X-Original-Host", "")
            ah = _actor_host()
            if ah and ah in fwd:
                return self._serve_html("actor.html", ("console.css", "i18n.js", "actor.js"))
            return self._serve_html("index.html", ("console.css", "i18n.js", "bridge.js", "app.js"))
        if path == "/actor" or rel == "actor.html":  # 直达路径也保留（任一 app 域名 + /actor 都能开）
            return self._serve_html("actor.html", ("console.css", "i18n.js", "actor.js"))
        return self._file(os.path.join(READER, rel))

    def _read_body(self):
        # Content-Length path (direct calls + most proxies).
        cl = self.headers.get("Content-Length")
        if cl is not None:
            try:
                return self.rfile.read(int(cl))
            except Exception:
                return b""
        # The liveware gRPC relay re-chunks POST bodies and drops Content-Length,
        # so a Content-Length-only read returns 0 bytes (type=None). Read the
        # chunked stream when that header is present.
        te = (self.headers.get("Transfer-Encoding") or "").lower()
        if "chunked" in te:
            chunks = []
            while True:
                size_line = self.rfile.readline().strip()
                if not size_line:
                    break
                try:
                    size = int(size_line.split(b";")[0], 16)
                except ValueError:
                    break
                if size == 0:
                    self.rfile.readline()  # consume trailing CRLF
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.readline()  # CRLF after each chunk
            return b"".join(chunks)
        return b""

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/stream":
            return self._json(410, {"ok": False, "error": "streaming disabled"})
        if path == "/api/tts":
            try:
                ev = json.loads(self._read_body() or b"{}")
                return self._audio(_generate_speech(ev.get("text")))
            except Exception as e:
                return self._json(502, {"ok": False, "error": str(e)})
        if path == "/api/tts/preview":
            try:
                ev = json.loads(self._read_body() or b"{}")
                audio = _generate_speech(
                    TTS_PREVIEW_TEXT, voice=ev.get("voice"), speed=ev.get("speed"),
                    instructions=ev.get("instructions"), force_preset=True)
                return self._audio(audio)
            except ValueError as e:
                return self._json(400, {"ok": False, "error": str(e)})
            except Exception as e:
                return self._json(502, {"ok": False, "error": str(e)})
        if path == "/api/tts/clone":
            try:
                ev = json.loads(self._read_body() or b"{}")
                settings = _save_tts_clone(ev.get("audio"), ev.get("ref_text"), ev.get("name"),
                                           ev.get("speed"))
                return self._json(200, {"ok": True, "tts": settings})
            except ValueError as e:
                return self._json(400, {"ok": False, "error": str(e)})
            except Exception as e:
                return self._json(500, {"ok": False, "error": str(e)})
        if path != "/api/event":
            return self._json(404, {"error": "unknown endpoint"})
        try:
            ev = json.loads(self._read_body() or b"{}")
        except Exception:
            return self._json(400, {"error": "bad json"})
        fn = EVENTS.get(ev.get("type"))
        if not fn:
            return self._json(400, {"error": "unknown event type: %s" % ev.get("type")})
        try:
            return self._json(200, {"ok": True, **fn(ev)})
        except Exception as e:
            return self._json(500, {"ok": False, "error": str(e)})


def main():
    port = 8799
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    elif os.environ.get("TAVERN_PORT"):
        port = int(os.environ["TAVERN_PORT"])
    host = os.environ.get("TAVERN_HOST", "127.0.0.1")
    _migrate_tts_config()
    migrated = _migrate_worldbook_storage()
    if migrated:
        print(f"worldbook storage migrated: {migrated} production(s)", flush=True)
    print("酒馆演员运行时 → http://%s:%d  (model=%s, key=%s)" % (
        host, port, actor.MODEL_NAME, "set" if actor.MODEL_KEY else "MISSING"))
    ThreadingHTTPServer((host, port), H).serve_forever()


if __name__ == "__main__":
    main()
