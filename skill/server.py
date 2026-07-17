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
TTS_CACHE_DIR = os.path.join(STATE, "tts-cache")
TTS_CACHE_RETENTION_DAYS = max(1, int(os.environ.get("TAVERN_TTS_CACHE_RETENTION_DAYS", "15")))
TTS_CACHE_CLEANUP_INTERVAL = 24 * 60 * 60
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
for directory in (TTS_REFERENCE_DIR, TTS_CACHE_DIR):
    os.makedirs(directory, mode=0o700, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
_tts_voice_cache = {"at": 0.0, "voices": list(TTS_FALLBACK_VOICES)}
_tts_voice_cache_lock = threading.Lock()
_tts_cache = {}
_tts_cache_order = []
_tts_cache_lock = threading.Lock()
_tts_cache_cleanup_lock = threading.Lock()
_tts_cache_last_cleanup = 0.0
_tts_generation_locks = tuple(threading.Lock() for _ in range(32))

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


def _tts_cache_path(cache_key):
    if not re.fullmatch(r"[0-9a-f]{64}", str(cache_key or "")):
        raise ValueError("invalid speech cache key")
    return os.path.join(TTS_CACHE_DIR, cache_key + ".mp3")


def _remember_tts_audio(cache_key, audio):
    with _tts_cache_lock:
        _tts_cache[cache_key] = audio
        try:
            _tts_cache_order.remove(cache_key)
        except ValueError:
            pass
        _tts_cache_order.append(cache_key)
        while len(_tts_cache_order) > TTS_CACHE_LIMIT:
            _tts_cache.pop(_tts_cache_order.pop(0), None)


def _store_tts_disk_cache(cache_key, audio):
    path = _tts_cache_path(cache_key)
    tmp = path + ".tmp." + secrets.token_hex(4)
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(audio)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def _load_tts_disk_cache(cache_key):
    path = _tts_cache_path(cache_key)
    try:
        with open(path, "rb") as file:
            audio = file.read()
        if not audio:
            os.remove(path)
            return None
        os.utime(path, None)
        return audio
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _cached_tts_audio(cache_key):
    with _tts_cache_lock:
        audio = _tts_cache.get(cache_key)
    if audio is not None:
        path = _tts_cache_path(cache_key)
        try:
            os.utime(path, None)
        except FileNotFoundError:
            _store_tts_disk_cache(cache_key, audio)
        except OSError:
            pass
        return audio
    audio = _load_tts_disk_cache(cache_key)
    if audio is not None:
        _remember_tts_audio(cache_key, audio)
    return audio


def _cleanup_tts_disk_cache(force=False, now=None):
    global _tts_cache_last_cleanup
    now = float(now if now is not None else time.time())
    with _tts_cache_cleanup_lock:
        if not force and now - _tts_cache_last_cleanup < TTS_CACHE_CLEANUP_INTERVAL:
            return 0
        _tts_cache_last_cleanup = now
        cutoff = now - TTS_CACHE_RETENTION_DAYS * 24 * 60 * 60
        removed_keys = []
        try:
            entries = list(os.scandir(TTS_CACHE_DIR))
        except OSError:
            return 0
        for entry in entries:
            match = re.fullmatch(r"([0-9a-f]{64})\.mp3", entry.name)
            if not match or not entry.is_file(follow_symlinks=False):
                continue
            try:
                if entry.stat(follow_symlinks=False).st_mtime >= cutoff:
                    continue
                os.remove(entry.path)
                removed_keys.append(match.group(1))
            except FileNotFoundError:
                pass
            except OSError:
                continue
        if removed_keys:
            removed = set(removed_keys)
            with _tts_cache_lock:
                for cache_key in removed:
                    _tts_cache.pop(cache_key, None)
                _tts_cache_order[:] = [key for key in _tts_cache_order if key not in removed]
        return len(removed_keys)


def _generate_speech(text, voice=None, speed=None, instructions=None, force_preset=False):
    _cleanup_tts_disk_cache()
    text = _speech_text(text)
    if not text:
        raise ValueError("speech text is empty")
    if len(text) > TTS_MAX_CHARS:
        raise ValueError(f"speech text is too long (max {TTS_MAX_CHARS} characters)")
    settings = _tts_settings()
    voice = str(voice or settings["active_voice"]).strip().lower()
    if voice not in {item["id"] for item in settings["voices"]}:
        raise ValueError("unsupported voice")
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
    cached = _cached_tts_audio(cache_key)
    if cached is not None:
        return cached

    generation_lock = _tts_generation_locks[int(cache_key[:8], 16) % len(_tts_generation_locks)]
    with generation_lock:
        cached = _cached_tts_audio(cache_key)
        if cached is not None:
            return cached
        key = _tts_key()
        if not key:
            raise ValueError("Clawling TTS key is missing")
        if not TTS_BASE:
            raise ValueError("TTS service endpoint is missing")
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
        _store_tts_disk_cache(cache_key, audio)
        _remember_tts_audio(cache_key, audio)
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
    if not tagline:
        for line in find("故事档案"):
            line = line.strip()
            if line and not line.startswith("-"):
                tagline = line.strip("。")
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
    card = _read(os.path.join(STATE, "cards", cid + ".json"))
    if isinstance(card, dict):
        card["profile"] = card_import.canonical_profile(card)
        card["entry"] = card_import.canonical_entry(card)
        card["performance"] = card_import.canonical_performance(card)
    return card


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
        record = _production_record(p)
        _write(os.path.join(STATE, "productions", p["id"] + ".json"), record)


def _production_record(p):
    """Strip hydrated projections before persisting a production."""
    record = dict(p)
    record.pop("worldbooks", None)
    if isinstance(record.get("persona"), dict):
        persona = dict(record["persona"])
        persona.pop("persistent_status", None)
        record["persona"] = persona
    if isinstance(record.get("runtime_cast"), dict):
        record.pop("cards", None)
    return record


def _story_content_signature(story):
    payload = [(m.get("id"), m.get("role"), m.get("text") or "") for m in story or []]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()


def _commit_foreground_story(p, expected_story_signature):
    """Commit generated story changes without overwriting newer background state."""
    pid = p["id"]
    with _production_lock(pid):
        current = load_production(pid)
        if not current:
            raise ValueError("production not found")
        if _story_content_signature(current.get("story") or []) != expected_story_signature:
            raise RuntimeError("故事已在另一项操作中更新，请重试。")

        incoming_story = p.get("story") or []
        current["story"] = incoming_story
        for key in ("response_language", "language_mode", "language_confidence", "language_source"):
            if key in p:
                current[key] = p[key]

        runtime = dict(current.get("runtime") or {})
        incoming_runtime = dict(p.get("runtime") or {})
        for key, value in incoming_runtime.items():
            if key != "story_state_error":
                runtime[key] = value
        if "last_prompt_debug" not in incoming_runtime:
            runtime.pop("last_prompt_debug", None)
        current["runtime"] = runtime

        current_state = current.get("story_state") or {}
        incoming_state = p.get("story_state") or {}
        if _validated_story_state(current_state, incoming_story):
            current["story_state"] = current_state
        elif _validated_story_state(incoming_state, incoming_story):
            current["story_state"] = incoming_state
        else:
            current["story_state"] = {}

        record = _production_record(current)
        _write(os.path.join(STATE, "productions", pid + ".json"), record)
        p.clear()
        p.update(current)
        return current


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
        record = _production_record(current)
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
    cards = []
    for raw in _list("cards"):
        if not isinstance(raw, dict):
            continue
        raw["profile"] = card_import.canonical_profile(raw)
        raw["entry"] = card_import.canonical_entry(raw)
        raw["performance"] = card_import.canonical_performance(raw)
        cards.append(raw)
    return cards


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
    card["profile"] = card_import.canonical_profile(card)
    card["entry"] = card_import.canonical_entry(card)
    card["performance"] = card_import.canonical_performance(card)
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
    _mark_context_state_stale(p, "worldbook_changed")
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
    runtime_cast = _ensure_runtime_cast(p)
    characters = [c for c in runtime_cast.get("characters") or []
                  if isinstance(c, dict) and c.get("id") != cid]
    characters.append(_runtime_character(card))
    runtime_cast["characters"] = characters
    runtime_cast["revision"] = int(runtime_cast.get("revision") or 0) + 1
    runtime_cast["updated_at"] = int(time.time())
    _hydrate_runtime_cards(p)
    wid = "wb_" + cid
    if load_worldbook(wid) and wid not in p.get("worldbook_ids", []):
        runtime_id = _clone_worldbook_for_production(p["id"], wid)
        if runtime_id and runtime_id not in p.get("worldbook_ids", []):
            p.setdefault("worldbook_ids", []).append(runtime_id)
        _ensure_production_session(p)
    _mark_context_state_stale(p, "loadout_changed")
    save_production(p)
    return {"production": p}


def ev_update_cast(ev):
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    cid = ev.get("card_id")
    runtime_cast = _ensure_runtime_cast(p)
    card = next((c for c in (runtime_cast.get("characters") or []) if c.get("id") == cid), None)
    if not card:
        raise ValueError("character not found in current world")
    if "profile" in ev and isinstance(ev.get("profile"), dict):
        merged_profile = json.loads(json.dumps(card.get("profile") or {}, ensure_ascii=False))
        for section, values in ev["profile"].items():
            if isinstance(values, dict):
                merged_profile.setdefault(section, {}).update(values)
        card["profile"] = card_import.canonical_profile({**card, "profile": merged_profile})
    else:
        fields = ("name", "description", "personality")
        for field in fields:
            if field in ev:
                card[field] = str(ev.get(field) or "").strip()
        card["profile"] = card_import.canonical_profile(card)
    identity = card["profile"]["identity"]
    card["name"] = identity.get("name") or ""
    card["description"] = identity.get("description") or ""
    card["personality"] = card["profile"]["personality"].get("summary") or ""
    if "entry" in ev and isinstance(ev.get("entry"), dict):
        merged_entry = dict(card.get("entry") or {})
        merged_entry.update(ev["entry"])
        card["entry"] = card_import.canonical_entry({**card, "entry": merged_entry})
        card["scenario"] = card["entry"].get("initial_scenario") or ""
    elif "scenario" in ev:
        card["scenario"] = str(ev.get("scenario") or "").strip()
        card["entry"] = card_import.canonical_entry(card)
    if not card["name"]:
        raise ValueError("name is required")
    if "persistent_status" in ev:
        card["persistent_status"] = _normalize_persistent_status(ev.get("persistent_status") or {})
        card["status_updated_turn"] = _world_turns(p.get("story") or [])
    if "relationships" in ev and isinstance(ev.get("relationships"), list):
        valid_targets = {str(c.get("id")) for c in (runtime_cast.get("characters") or []) if c.get("id")}
        valid_targets.add("__user__")
        kept = []
        for relation in runtime_cast.get("relationships") or []:
            participants = [str(x) for x in (relation.get("participants") or [])]
            if cid not in participants:
                kept.append(relation)
                continue
        incoming = []
        current_turn = _world_turns(p.get("story") or [])
        for raw in ev.get("relationships") or []:
            if not isinstance(raw, dict):
                continue
            target = str(raw.get("target_id") or "")
            description = _clip_memory_text(raw.get("description"), 300)
            if not target or target == cid or target not in valid_targets or not description:
                continue
            incoming.append({
                "participants": [cid, target],
                "description": description,
                "updated_turn": current_turn,
            })
        runtime_cast["relationships"] = _normalize_relationships(
            kept + incoming, runtime_cast.get("characters") or [], p.get("persona") or {})
    card["updated_at"] = int(time.time())
    runtime_cast["revision"] = int(runtime_cast.get("revision") or 0) + 1
    runtime_cast["updated_at"] = int(time.time())
    _hydrate_runtime_cards(p)
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
    runtime_cast = _ensure_runtime_cast(p)
    runtime_cast["characters"] = [c for c in (runtime_cast.get("characters") or [])
                                  if isinstance(c, dict) and c.get("id") != cid]
    runtime_cast["relationships"] = [r for r in (runtime_cast.get("relationships") or [])
                                     if cid not in (r.get("participants") or [])]
    runtime_cast["revision"] = int(runtime_cast.get("revision") or 0) + 1
    runtime_cast["updated_at"] = int(time.time())
    _hydrate_runtime_cards(p)
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
    _mark_context_state_stale(p, "loadout_changed")
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
            runtime_cast = _ensure_runtime_cast(prod)
            runtime_cast["characters"] = [c for c in (runtime_cast.get("characters") or [])
                                          if c.get("id") != cid]
            runtime_cast["relationships"] = [r for r in (runtime_cast.get("relationships") or [])
                                             if cid not in (r.get("participants") or [])]
            runtime_cast["revision"] = int(runtime_cast.get("revision") or 0) + 1
            _hydrate_runtime_cards(prod)
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


def _state_list(value, limit=12, max_len=180):
    values = value if isinstance(value, list) else ([value] if value else [])
    out = []
    for item in values:
        text = _clip_memory_text(item, max_len)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _stable_memory_id(prefix, value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return prefix + "_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _normalize_known_by(value, valid_ids=None):
    values = value if isinstance(value, list) else ([value] if value else [])
    out = []
    for item in values:
        cid = str(item or "").strip()
        if cid and (not valid_ids or cid in valid_ids) and cid not in out:
            out.append(cid)
    return out[:24]


def _normalize_fact_entry(value, valid_ids=None, secret=False):
    raw = value if isinstance(value, dict) else {"content": value}
    content = _clip_memory_text(raw.get("content") or raw.get("fact") or raw.get("summary"), 220)
    if not content:
        return None
    known_by = _normalize_known_by(raw.get("known_by"), valid_ids)
    return {
        "id": str(raw.get("id") or _stable_memory_id("secret" if secret else "fact", content)),
        "content": content,
        "known_by": known_by,
    }


def _normalize_object_entry(value, valid_ids=None):
    raw = value if isinstance(value, dict) else {"name": value}
    name = _clip_memory_text(raw.get("name") or raw.get("content") or raw.get("summary"), 160)
    if not name:
        return None
    holder = str(raw.get("holder") or "").strip()
    if holder and valid_ids and holder not in valid_ids:
        holder = ""
    return {
        "id": str(raw.get("id") or _stable_memory_id("object", name)),
        "name": name,
        "status": _clip_memory_text(raw.get("status"), 160),
        "holder": holder,
        "location": _clip_memory_text(raw.get("location"), 160),
    }


def _normalize_scene_participant(value, valid_ids=None):
    raw = value if isinstance(value, dict) else {}
    cid = str(raw.get("character_id") or raw.get("id") or "").strip()
    if not cid or (valid_ids and cid not in valid_ids):
        return None
    return {
        "character_id": cid,
        "location": _clip_memory_text(raw.get("location"), 160),
        "activity": _clip_memory_text(raw.get("activity") or raw.get("goal"), 180),
        "condition": _clip_memory_text(raw.get("condition"), 160),
    }


def _normalize_ledger_scene(value, valid_ids=None):
    raw = value if isinstance(value, dict) else {}
    participants = []
    seen = set()
    for item in raw.get("participants") or []:
        participant = _normalize_scene_participant(item, valid_ids)
        if participant and participant["character_id"] not in seen:
            seen.add(participant["character_id"])
            participants.append(participant)
    return {
        "time": _clip_memory_text(raw.get("time"), 160),
        "place": _clip_memory_text(raw.get("place") or raw.get("location"), 180),
        "participants": participants[:24],
    }


def _migrate_legacy_story_context(state, characters):
    """Move old per-card scene/knowledge state into the canonical story ledger."""
    ledger = dict(state or {})
    valid_ids = {str(c.get("id")) for c in characters if isinstance(c, dict) and c.get("id")}
    valid_ids.add("__user__")
    def entries(value):
        return [value] if isinstance(value, (str, dict)) else list(value or [])

    facts = []
    for item in entries(ledger.get("facts")):
        fact = _normalize_fact_entry(item, valid_ids)
        if fact and fact["id"] not in {x["id"] for x in facts}:
            facts.append(fact)
    scene = _normalize_ledger_scene(ledger.get("scene"), valid_ids)
    participants = {item["character_id"]: item for item in scene["participants"]}
    for character in characters:
        if not isinstance(character, dict):
            continue
        cid = str(character.get("id") or "")
        old = character.get("state") if isinstance(character.get("state"), dict) else {}
        if not cid:
            continue
        participant = participants.get(cid) or {
            "character_id": cid, "location": "", "activity": "", "condition": ""}
        participant["location"] = participant.get("location") or _clip_memory_text(old.get("location"), 160)
        participant["activity"] = participant.get("activity") or _clip_memory_text(old.get("goal"), 180)
        participant["condition"] = participant.get("condition") or _clip_memory_text(old.get("condition"), 160)
        scene_notes = card_import.canonical_scene_notes(character)
        if scene_notes and not participant["activity"]:
            participant["activity"] = _clip_memory_text("；".join(scene_notes), 180)
        if any(participant.get(key) for key in ("location", "activity", "condition")):
            participants[cid] = participant
        for memory in _state_list(old.get("knowledge"), 20, 220) + _state_list(old.get("notes"), 20, 220):
            fact = _normalize_fact_entry({"content": memory, "known_by": [cid]}, valid_ids)
            if fact and fact["id"] not in {x["id"] for x in facts}:
                facts.append(fact)
    scene["participants"] = list(participants.values())[:24]
    ledger["scene"] = scene
    ledger["facts"] = facts[:40]
    objects = []
    for item in entries(ledger.get("objects")):
        obj = _normalize_object_entry(item, valid_ids)
        if obj and obj["id"] not in {x["id"] for x in objects}:
            objects.append(obj)
    ledger["objects"] = objects[:24]
    secrets = []
    for item in entries(ledger.get("secrets")):
        fact = _normalize_fact_entry(item, valid_ids, secret=True)
        if fact and fact["id"] not in {x["id"] for x in secrets}:
            secrets.append(fact)
    ledger["secrets"] = secrets[:24]
    return ledger


def _normalize_persistent_status(value):
    raw = value if isinstance(value, dict) else {}
    identity_status = raw.get("identity_status")
    if identity_status is None:
        identity_status = "；".join(_state_list(raw.get("identity_changes"), 10, 180))
    physical_condition = raw.get("physical_condition")
    if physical_condition is None:
        physical_condition = "；".join(_state_list(raw.get("long_term_conditions"), 10, 180))
    return {
        "life_status": _clip_memory_text(raw.get("life_status"), 80),
        "identity_status": _clip_memory_text(identity_status, 600),
        "physical_condition": _clip_memory_text(physical_condition, 600),
    }


def _canonical_profile_snapshot(value):
    """Return one detached canonical profile suitable for per-world storage."""
    raw = value if isinstance(value, dict) else {}
    if any(key in raw for key in (
            "identity", "appearance", "personality", "expression",
            "capabilities", "background")):
        raw = {"profile": raw}
    return card_import.canonical_profile(raw)


def _profile_has_content(profile):
    return any(
        value
        for section in (profile or {}).values() if isinstance(section, dict)
        for value in section.values()
    )


def _normalize_persona(value):
    """Normalize the per-world user character without performance instructions."""
    raw = json.loads(json.dumps(value or {}, ensure_ascii=False)) if isinstance(value, dict) else {}
    profile = card_import.canonical_profile(raw)
    name = profile["identity"].get("name") or _clip_memory_text(raw.get("name"), 160)
    description = profile["identity"].get("description") or _clip_memory_text(raw.get("description"), 2500)
    profile["identity"]["name"] = name
    profile["identity"]["description"] = description
    persona = {"name": name, "description": description, "profile": profile}
    if raw.get("source_card_id"):
        persona["source_card_id"] = str(raw.get("source_card_id"))
    if isinstance(raw.get("persistent_status"), dict):
        persona["persistent_status"] = _normalize_persistent_status(raw.get("persistent_status"))
    return persona


def _runtime_character(card, legacy_notes=None, applied_turn=0):
    item = json.loads(json.dumps(card or {}, ensure_ascii=False))
    cid = str(item.get("id") or "card_" + secrets.token_hex(4))
    item["id"] = cid
    item.setdefault("source_card_id", cid)
    current_profile = _canonical_profile_snapshot(item.get("profile") or item)
    origin_profile = item.get("origin_profile")
    item["origin_profile"] = _canonical_profile_snapshot(
        origin_profile if isinstance(origin_profile, dict) else current_profile)
    item["profile"] = current_profile
    item["entry"] = card_import.canonical_entry(item)
    item["performance"] = card_import.canonical_performance(item)
    item["name"] = item["profile"]["identity"]["name"] or item.get("name") or ""
    item["persistent_status"] = _normalize_persistent_status(item.get("persistent_status") or {})
    item["profile_updated_turn"] = int(item.get("profile_updated_turn") or applied_turn or 0)
    item["status_updated_turn"] = int(
        item.get("status_updated_turn") or item.get("state_updated_turn") or applied_turn or 0)
    item.pop("state", None)
    item.pop("state_updated_turn", None)
    item.pop("relationships", None)
    item.pop("relationship_details", None)
    return item


def _normalize_relationships(value, characters, persona=None):
    valid_ids = {str(c.get("id")) for c in characters if c.get("id")}
    valid_ids.add("__user__")
    names_by_id = {str(c.get("id")): str(c.get("name") or "").strip()
                   for c in characters if c.get("id")}
    names = {str(c.get("name") or "").strip(): str(c.get("id")) for c in characters}
    names["用户"] = "__user__"
    names["User"] = "__user__"
    if (persona or {}).get("name"):
        names[str(persona.get("name")).strip()] = "__user__"
    out = []
    seen = set()
    values = value if isinstance(value, list) else []
    for raw in values:
        if isinstance(raw, str):
            participants = [cid for name, cid in names.items() if name and name in raw][:2]
            description = _clip_memory_text(raw, 300)
            updated_turn = 0
        elif isinstance(raw, dict):
            participants = [str(x) for x in (raw.get("participants") or []) if str(x) in valid_ids][:2]
            description = _clip_memory_text(
                raw.get("description") or raw.get("type") or raw.get("label") or raw.get("summary"), 300)
            legacy_attitude = _clip_memory_text(raw.get("attitude"), 120)
            if legacy_attitude and legacy_attitude not in description:
                description = _clip_memory_text(description + ("，" if description else "") + legacy_attitude, 300)
            updated_turn = int(raw.get("updated_turn") or 0)
        else:
            continue
        if len(participants) != 2 or participants[0] == participants[1] or not description:
            continue
        participants = sorted(participants)
        # Older snapshots often repeated both names inside the description,
        # producing UI such as "Delta: User and Delta: ...". The edge already
        # owns its participants, so retain only the human-readable predicate.
        subject, separator, predicate = description.partition("：")
        if not separator:
            subject, separator, predicate = description.partition(":")
        if separator and predicate.strip():
            subject_folded = subject.casefold()
            participant_aliases = []
            for participant in participants:
                if participant == "__user__":
                    aliases = ["用户", "user", str((persona or {}).get("name") or "").strip()]
                else:
                    aliases = [names_by_id.get(participant, "")]
                participant_aliases.append([alias.casefold() for alias in aliases if alias])
            if all(any(alias in subject_folded for alias in aliases)
                   for aliases in participant_aliases):
                description = predicate.strip()
        key = "|".join(participants)
        if key in seen:
            continue
        seen.add(key)
        out.append({"id": "rel_" + hashlib.sha1(key.encode()).hexdigest()[:12],
                    "participants": participants, "description": description,
                    "updated_turn": updated_turn})
    return out[:24]


def _relationships_from_cards(characters, persona=None):
    """Seed runtime relationships from card prose only when no live relationship state exists."""
    by_name = {str(c.get("name") or "").strip(): str(c.get("id")) for c in characters}
    user_names = {"你", "用户", "user"}
    if (persona or {}).get("name"):
        user_names.add(str(persona.get("name")).strip().lower())
    hints = []
    for character in characters:
        source_id = str(character.get("id") or "")
        for line in card_import.canonical_relationship_hints(character):
            parts = re.split(r"[：:]", line, maxsplit=1)
            label, detail = (parts[0], parts[1]) if len(parts) == 2 else (line, line)
            label = str(label).strip()
            target_id = ""
            if label.lower() in user_names or label.startswith("你"):
                target_id = "__user__"
            else:
                for name, cid in by_name.items():
                    if name and (label == name or label.startswith(name)):
                        target_id = cid
                        break
            if target_id and target_id != source_id:
                hints.append({"participants": [source_id, target_id],
                              "description": str(detail).strip(), "updated_turn": 0})
    return _normalize_relationships(hints, characters, persona)


def _ensure_runtime_cast(p):
    if p is None:
        return {}
    existing = p.get("runtime_cast") if isinstance(p.get("runtime_cast"), dict) else None
    if existing:
        applied_turn = int(existing.get("applied_turn") or 0)
        raw_characters = [c for c in (existing.get("characters") or []) if isinstance(c, dict)]
        migrated_characters = []
        for raw_character in raw_characters:
            character = json.loads(json.dumps(raw_character, ensure_ascii=False))
            if not isinstance(character.get("origin_profile"), dict):
                source_id = str(character.get("source_card_id") or character.get("id") or "")
                source_card = load_card(source_id) if source_id else None
                character["origin_profile"] = _canonical_profile_snapshot(
                    (source_card or {}).get("profile") or source_card or
                    character.get("profile") or character)
            migrated_characters.append(character)
        raw_characters = migrated_characters
        p["story_state"] = _migrate_legacy_story_context(p.get("story_state") or {}, raw_characters)
        characters = [_runtime_character(c, applied_turn=applied_turn) for c in raw_characters]
        runtime_cast = dict(existing)
    else:
        source_cards = p.get("cards") if isinstance(p.get("cards"), list) else None
        if source_cards is None:
            source_cards = [load_card(cid) for cid in _production_card_ids(p)]
        source_cards = [c for c in source_cards if isinstance(c, dict)]
        ledger = p.get("story_state") if isinstance(p.get("story_state"), dict) else {}
        applied_turn = int(ledger.get("turns") or 0)
        legacy_states = ledger.get("character_state") if isinstance(ledger.get("character_state"), dict) else {}
        characters = [_runtime_character(c, legacy_states.get(str(c.get("name") or "")), applied_turn)
                      for c in source_cards]
        runtime_cast = {
            "schema_version": 2,
            "applied_turn": applied_turn,
            "revision": 1,
            "characters": characters,
            "relationships": _normalize_relationships(ledger.get("relationships") or [], characters,
                                                        p.get("persona") or {}),
            "updated_at": int(time.time()),
        }
    runtime_cast["schema_version"] = 3
    runtime_cast["applied_turn"] = applied_turn
    runtime_cast["revision"] = max(1, int(runtime_cast.get("revision") or 1))
    runtime_cast["characters"] = characters
    persona_profile = _canonical_profile_snapshot((p.get("persona") or {}).get("profile") or
                                                   (p.get("persona") or {}))
    current_user_profile = runtime_cast.get("user_profile")
    runtime_cast["user_profile"] = _canonical_profile_snapshot(
        current_user_profile if isinstance(current_user_profile, dict) else persona_profile)
    origin_user_profile = runtime_cast.get("origin_user_profile")
    runtime_cast["origin_user_profile"] = _canonical_profile_snapshot(
        origin_user_profile if isinstance(origin_user_profile, dict)
        else runtime_cast["user_profile"])
    runtime_cast["user_profile_updated_turn"] = int(
        runtime_cast.get("user_profile_updated_turn") or 0)
    persona_status = ((p.get("persona") or {}).get("persistent_status")
                      if isinstance(p.get("persona"), dict) else {})
    runtime_cast["user_status"] = _normalize_persistent_status(
        runtime_cast.get("user_status") if "user_status" in runtime_cast else persona_status)
    runtime_cast["user_status_updated_turn"] = int(runtime_cast.get("user_status_updated_turn") or 0)
    runtime_cast["relationships"] = _normalize_relationships(
        runtime_cast.get("relationships") or [], characters, p.get("persona") or {})
    if not runtime_cast["relationships"]:
        runtime_cast["relationships"] = _relationships_from_cards(characters, p.get("persona") or {})
    p["runtime_cast"] = runtime_cast
    return runtime_cast


def _hydrate_runtime_cards(p):
    runtime_cast = _ensure_runtime_cast(p)
    characters = json.loads(json.dumps(runtime_cast.get("characters") or [], ensure_ascii=False))
    by_id = {str(c.get("id")): c for c in characters}
    persona_name = str((p.get("persona") or {}).get("name") or "用户")
    for relation in runtime_cast.get("relationships") or []:
        participants = relation.get("participants") or []
        if len(participants) != 2:
            continue
        for cid in participants:
            card = by_id.get(str(cid))
            if not card:
                continue
            other = participants[1] if participants[0] == cid else participants[0]
            other_name = persona_name if other == "__user__" else str((by_id.get(str(other)) or {}).get("name") or other)
            detail = {
                "id": relation.get("id"),
                "target_id": other,
                "target_name": other_name,
                "description": relation.get("description") or "",
            }
            card.setdefault("relationship_details", []).append(detail)
            card.setdefault("relationships", []).append(f"{other_name}：{detail['description']}")
    p["cards"] = characters
    return characters


def _hydrate_user_persona(p):
    runtime_cast = p.get("runtime_cast") if isinstance(p.get("runtime_cast"), dict) else {}
    stored = p.get("persona") if isinstance(p.get("persona"), dict) else {}
    current_profile = runtime_cast.get("user_profile")
    if isinstance(current_profile, dict):
        persona = _normalize_persona({"profile": current_profile})
        if stored.get("source_card_id"):
            persona["source_card_id"] = str(stored.get("source_card_id"))
    else:
        persona = _normalize_persona(stored)
    persona["persistent_status"] = _normalize_persistent_status(runtime_cast.get("user_status") or {})
    p["persona"] = persona
    return persona


def _ensure_production_session(p):
    """Hydrate current-story projections; runtime_cast is the sole cast authority."""
    if p is None:
        return p
    p["persona"] = _normalize_persona(p.get("persona") or {})
    _hydrate_runtime_cards(p)
    _hydrate_user_persona(p)
    p["worldbooks"] = _snapshot_worldbooks(p.get("worldbook_ids") or [])
    p.setdefault("story", [])
    p.setdefault("runtime", {})
    return p


def _mark_context_state_stale(p, reason="context_changed"):
    p["turn_plan"] = {}
    p.setdefault("runtime", {})["state_stale_reason"] = reason
    p["runtime"].pop("last_prompt_debug", None)
    if isinstance(p.get("scene_state"), dict):
        p["scene_state"]["stale"] = True


def _mark_story_state_stale(p, reason="history_changed"):
    _mark_context_state_stale(p, reason)
    if isinstance(p.get("story_state"), dict):
        p["story_state"]["stale"] = True


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
                         model=_active_model(), story_state=_effective_story_state(p),
                         scene_state=p.get("scene_state"), turn_plan=turn_plan,
                         response_language=language)  # 用户自配大模型;None=内置模型


def ev_send_message(ev):
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    expected_story_signature = _story_content_signature(p.get("story") or [])
    _observe_user_language(p, ev["text"], ev.get("locale"))
    user_msg = _msg("user", ev["text"])
    p["story"].append(user_msg)
    cards, wbs, persona, note = _loadout(p)
    reply = _ensure_actor_reply(p, cards, wbs, persona, note, _perform_into(p))
    _raise_if_generation_cancelled(ev)
    m = _msg("char", reply)
    p["story"].append(m)
    _commit_foreground_story(p, expected_story_signature)
    state_sync = _story_state_sync_trigger(p["id"])
    _schedule_story_state(p["id"])
    _schedule_scene_state(p["id"])
    return {"reply": reply, "message": m, "user_message": user_msg,
            "production_id": p["id"], "state_sync": state_sync}


def ev_regenerate(ev):
    p = load_production(ev["production_id"])
    if not p or not p["story"]:
        raise ValueError("nothing to regenerate")
    expected_story_signature = _story_content_signature(p.get("story") or [])
    _ensure_world_language(p, ev.get("locale"))
    # 砍掉最后一条 char，重演（保留为 alt）
    last = p["story"][-1]
    if last["role"] != "char":
        raise ValueError("last message is not the actor's")
    trimmed = p["story"][:-1]
    saved_story = p["story"]
    p["story"] = trimmed
    _mark_context_state_stale(p, "regenerate")
    cards, wbs, persona, note = _loadout(p)
    reply = _ensure_actor_reply(p, cards, wbs, persona, note, _perform_into(p))
    _raise_if_generation_cancelled(ev)
    last["alts"].append(reply)
    last["active_alt"] = len(last["alts"]) - 1
    last["text"] = reply
    p["story"] = saved_story
    _commit_foreground_story(p, expected_story_signature)
    state_sync = _story_state_sync_trigger(p["id"])
    _schedule_story_state(p["id"])
    _schedule_scene_state(p["id"])
    return {"message": last, "production_id": p["id"], "state_sync": state_sync}


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
                                                    model=_active_model(), story_state=_effective_story_state(p),
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
    expected_story_signature = _story_content_signature(p.get("story") or [])
    language = _ensure_world_language(p, ev.get("locale"))
    user_msg = _msg("user", ev.get("text") or ("*Continue the story.*" if language == "en" else "*剧情继续*"))
    p["story"].append(user_msg)
    cards, wbs, persona, note = _loadout(p)
    turn_plan = _prepare_turn_plan(p, cards)
    continue_note = _continue_note(note, language)
    reply = actor.perform(cards, wbs, persona, p["story"], continue_note,
                          model=_active_model(), story_state=_effective_story_state(p),
                          scene_state=p.get("scene_state"), turn_plan=turn_plan,
                          response_language=language)
    reply = _ensure_actor_reply(p, cards, wbs, persona, continue_note, reply)
    _raise_if_generation_cancelled(ev)
    m = _msg("char", reply)
    p["story"].append(m)
    _commit_foreground_story(p, expected_story_signature)
    state_sync = _story_state_sync_trigger(p["id"])
    _schedule_story_state(p["id"])
    _schedule_scene_state(p["id"])
    return {"reply": reply, "user_message": user_msg, "message": m,
            "production_id": p["id"], "state_sync": state_sync}


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
    persona_txt = actor.user_character_block(persona, language)
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
    expected_story_signature = _story_content_signature(p.get("story") or [])
    latest = p["story"][-1] if p.get("story") else None
    if not latest or latest.get("role") != "char" or latest.get("id") != ev.get("message_id"):
        raise ValueError("only the latest reply can switch alternatives")
    for m in (latest,):
        if m["id"] == ev["message_id"]:
            alts = m.get("alts") or [m.get("text", "")]
            cur = m.get("active_alt", 0)
            nxt = max(0, min(len(alts) - 1, cur + int(ev.get("dir", 0))))
            m["active_alt"] = nxt
            m["text"] = alts[nxt]
            _mark_context_state_stale(p, "swipe")
            _commit_foreground_story(p, expected_story_signature)
            return {"message": m}
    raise ValueError("message not found")


def ev_edit_message(ev):
    """Edit only the latest visible turn; confirmed compressed history is immutable."""
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    story = p.get("story") or []
    if not story:
        raise ValueError("message not found")
    expected_story_signature = _story_content_signature(story)
    editable_ids = {story[-1].get("id")}
    if story[-1].get("role") == "char" and len(story) >= 2 and story[-2].get("role") == "user":
        editable_ids.add(story[-2].get("id"))
    if ev.get("message_id") not in editable_ids:
        raise ValueError("only the latest turn can be edited")
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
            _mark_context_state_stale(p, "edit_message")
            reply_msg = None
            if ev.get("continue_after") and m.get("role") == "user" and text.strip():
                cards, wbs, persona, note = _loadout(p)
                reply = _ensure_actor_reply(p, cards, wbs, persona, note, _perform_into(p))
                _raise_if_generation_cancelled(ev)
                reply_msg = _msg("char", reply)
                p["story"].append(reply_msg)
            _commit_foreground_story(p, expected_story_signature)
            state_sync = {"watch": False, "revision": 0}
            if reply_msg:
                state_sync = _story_state_sync_trigger(p["id"])
                _schedule_story_state(p["id"])
                _schedule_scene_state(p["id"])
            return {"message": m, "reply": reply_msg, "story": p["story"],
                    "truncated": removed, "state_sync": state_sync}
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
    folded = s.casefold()
    for n in names:
        if n and str(n).casefold() == folded:
            return n
    for n in names:
        if n and (n in s or s in n):
            return n
    return ""

def _normalize_scene_state(raw, cards, response_language="zh"):
    if not isinstance(raw, dict):
        raw = {}

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

    valid_ids = {str(c.get("id")) for c in cards or [] if c.get("id")}
    participants = []
    for value in raw.get("participants") or []:
        participant = _normalize_scene_participant(value, valid_ids)
        if participant:
            participants.append(participant)
    unknown = "Unspecified" if _locale_code(response_language) == "en" else "未明确"
    return {
        "location": text("location", unknown),
        "time": text("time", unknown),
        "mood": text("mood", unknown),
        "current_focus": text("current_focus"),
        "open_threads": arr("open_threads", limit=10),
        "participants": participants[:24],
        "updated_at": int(time.time()),
    }


def _scene_story_excerpt(p, max_items=12, response_language=None):
    language = response_language or _ensure_world_language(p)
    en = language == "en"
    cname = "Story response" if en else "故事回复"
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
    scene = p.get("scene_state") or {}
    plot = _effective_story_state(p)
    user = json.dumps({
        "characters": [{"id": c.get("id"), "name": c.get("name"),
                        "profile": c.get("profile") or {},
                        "persistent_status": c.get("persistent_status") or {},
                        "relationships": c.get("relationships") or []} for c in cards],
        "scene_state": {key: scene.get(key) for key in
                        ("location", "time", "mood", "current_focus", "open_threads")},
        "story_state": {key: plot.get(key) for key in
                        ("timeline", "facts", "open_threads", "objects", "secrets", "scene", "style_notes")},
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
        "Record only events that clearly happened or are strongly established; do not add literary commentary. Output strict JSON with only location, time, mood, current_focus, open_threads, and participants. "
        "participants contains character_id, location, activity, and condition for characters clearly present or recently tracked. Do not record personality, identity, relationships, or learned facts."
    ) if en else (
        "你是互动故事的场记。根据最近剧情更新当前场景状态，所有文本值使用简体中文。"
        "只记录已经明确发生或强烈成立的内容，不要写文学点评。"
        "输出严格 JSON，字段只有 location、time、mood、current_focus、open_threads、participants。"
        "participants 记录明确在场或刚被追踪角色的 character_id、location、activity、condition。不要记录人物性格、身份、关系或已知事实。"
    ))
    user = json.dumps({
        "previous_scene_state": p.get("scene_state") or {},
        "roster": [{"id": c.get("id"), "name": c.get("name")} for c in cards],
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


def _compressible_story_turns(story):
    """Keep the latest user turn raw and compress only confirmed history."""
    return max(0, _world_turns(story) - 1)


STORY_STATE_BATCH_TURNS = int(os.environ.get("TAVERN_STORY_STATE_BATCH_TURNS", "15"))
STORY_STATE_MAX_CHARS = max(4000, int(os.environ.get("TAVERN_STORY_STATE_MAX_CHARS", "15000")))
STORY_STATE_BATCH_TOKEN_BUDGET = max(
    8000, int(os.environ.get("TAVERN_STORY_STATE_BATCH_TOKEN_BUDGET", "50000")))


def _story_messages_through_turn(story, end_turn):
    """Return complete messages from the opening through one user-turn boundary."""
    selected = []
    seen_turns = 0
    for message in story or []:
        if message.get("role") == "user":
            seen_turns += 1
            if seen_turns > end_turn:
                break
        selected.append(message)
    return selected


def _story_lines_for_turns(p, start_turn, end_turn):
    """Render complete story messages for an inclusive user-turn batch."""
    en = _ensure_world_language(p) == "en"
    cname = "Story response" if en else "故事回复"
    lines = []
    seen_turns = 0
    for message in p.get("story") or []:
        if message.get("role") == "user":
            seen_turns += 1
        if seen_turns < start_turn:
            if start_turn == 1 and seen_turns == 0:
                pass
            else:
                continue
        if seen_turns > end_turn:
            break
        text = (message.get("text") or "").strip().replace("\r\n", "\n")
        if not text:
            continue
        who = ("User" if en else "用户") if message.get("role") == "user" else cname
        turn_label = max(0, seen_turns)
        prefix = f"[Turn {turn_label} · {who}]" if en else f"[第 {turn_label} 轮 · {who}]"
        lines.append(f"{prefix}\n{text}")
    return "\n".join(lines)


def _story_batch_segments(p, start_turn, end_turn):
    """Split an oversized batch only at complete user-turn boundaries."""
    segments = []
    segment_start = start_turn
    segment_end = start_turn - 1
    segment_parts = []
    segment_tokens = 0
    for turn in range(start_turn, end_turn + 1):
        part = _story_lines_for_turns(p, turn, turn)
        part_tokens = _estimate_text_tokens(part)
        if segment_parts and segment_tokens + part_tokens > STORY_STATE_BATCH_TOKEN_BUDGET:
            segments.append((segment_start, segment_end, "\n".join(segment_parts)))
            segment_start = turn
            segment_parts = []
            segment_tokens = 0
        segment_parts.append(part)
        segment_tokens += part_tokens
        segment_end = turn
    if segment_parts:
        segments.append((segment_start, segment_end, "\n".join(segment_parts)))
    return segments


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
        "timeline": (12, 120),
        "open_threads": (12, 140),
        "style_notes": (6, 120),
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

    state = {
        "timeline": arr("timeline"),
        "facts": [],
        "open_threads": arr("open_threads"),
        "objects": [],
        "secrets": [],
        "scene": _normalize_ledger_scene(raw.get("scene")),
        "style_notes": arr("style_notes"),
        "turns": turns,
        "source_tokens": source_tokens,
        "updated_at": int(time.time()),
    }
    fact_values = raw.get("facts") or []
    if isinstance(fact_values, (str, dict)):
        fact_values = [fact_values]
    for value in fact_values:
        fact = _normalize_fact_entry(value)
        if fact and fact["id"] not in {item["id"] for item in state["facts"]}:
            state["facts"].append(fact)
        if len(state["facts"]) >= 24:
            break
    object_values = raw.get("objects") or []
    if isinstance(object_values, (str, dict)):
        object_values = [object_values]
    for value in object_values:
        obj = _normalize_object_entry(value)
        if obj and obj["id"] not in {item["id"] for item in state["objects"]}:
            state["objects"].append(obj)
        if len(state["objects"]) >= 16:
            break
    secret_values = raw.get("secrets") or []
    if isinstance(secret_values, (str, dict)):
        secret_values = [secret_values]
    for value in secret_values:
        secret = _normalize_fact_entry(value, secret=True)
        if secret and secret["id"] not in {item["id"] for item in state["secrets"]}:
            state["secrets"].append(secret)
        if len(state["secrets"]) >= 16:
            break
    return _trim_story_state_to_budget(state, STORY_STATE_MAX_CHARS)


def _story_state_chars(state):
    return len(json.dumps(state or {}, ensure_ascii=False, separators=(",", ":")))


def _trim_story_state_to_budget(state, max_chars):
    """Bound ledger size while removing transient details before protected memory."""
    state = dict(state or {})

    primary_order = (
        "style_notes", "timeline", "facts", "objects",
    )
    protected_order = ("open_threads", "secrets")
    while _story_state_chars(state) > max_chars:
        changed = False
        for key in primary_order:
            values = list(state.get(key) or [])
            if values:
                values.pop(0)
                state[key] = values
                changed = True
                break
        if not changed:
            for key in protected_order:
                values = list(state.get(key) or [])
                if values:
                    values.pop(0)
                    state[key] = values
                    changed = True
                    break
        if not changed:
            break
    return state


def _story_state_quality_ok(previous, current):
    """Reject catastrophic memory loss without adding another model call."""
    if not _story_state_has_memory(previous):
        return True

    def count(keys, state):
        return sum(len(state.get(key) or []) for key in keys)

    old_protected = count(("open_threads", "objects", "secrets"), previous)
    new_protected = count(("open_threads", "objects", "secrets"), current)
    if old_protected >= 6 and new_protected < 2:
        return False

    old_history = count(("timeline", "facts"), previous)
    new_history = count(("timeline", "facts"), current)
    if old_history >= 6 and new_history < 2:
        return False

    return True


def _story_state_has_memory(state):
    return any(state.get(k) for k in (
        "timeline", "facts", "open_threads", "objects", "secrets", "style_notes"
    ))


def _validated_story_state(state, story):
    """Return a ledger only when it safely replaces confirmed raw turns."""
    if not isinstance(state, dict) or state.get("stale") or not _story_state_has_memory(state):
        return {}
    try:
        covered_turns = int(state.get("turns") or 0)
    except (TypeError, ValueError):
        return {}
    if (covered_turns <= 0 or covered_turns % STORY_STATE_BATCH_TURNS
            or covered_turns > _compressible_story_turns(story)):
        return {}
    expected = str(state.get("covered_signature") or "").strip()
    if expected and _story_prefix_signature(story, covered_turns) != expected:
        return {}
    return state


def _effective_story_state(p):
    return _validated_story_state(
        (p or {}).get("story_state") or {}, (p or {}).get("story") or [])


def _merge_story_state_batch(prev, batch, start_turn, end_turn,
                             source_tokens, response_language="zh"):
    language = _locale_code(response_language)
    plot_keys = ("timeline", "facts", "open_threads", "objects", "secrets", "style_notes", "scene")
    prev = {key: (prev or {}).get(key) or ({} if key == "scene" else []) for key in plot_keys}
    if language == "en":
        sys_prompt = (
            "You are the high-fidelity continuity recorder for an interactive story. Merge previous_state and the complete new_story_batch into an updated story ledger. "
            "Write every textual value in English, translating older ledger values when necessary while preserving names and facts. Record only completed or ongoing plot events, causal facts, secrets, key objects, open threads, major promises, conflicts, turning points, and consequential choices. "
            "The ledger is the sole owner of scene location, participant positions and activities, story facts, knowledge boundaries, and object custody. "
            "Do not store personality, identity, abilities, durable identity changes, long-term conditions, or current relationship conclusions; those belong to the character registry. Relationship changes may appear only as timeline events. "
            "Output strict JSON using only timeline, facts, open_threads, objects, secrets, scene, and style_notes. facts and secrets contain objects with id, content, and known_by character ids. objects contain id, name, status, holder character id, and location. scene contains time, place, and participants; every participant has character_id, location, activity, and condition. "
            "Keep entries short, concrete, unique, and non-prose. Keep at most 12 entries per major array. Keep timeline/facts under 20 words and open_threads under 28 words. "
            "Never drop unresolved threads, unrevealed secrets, key objects, identity revelations, major promises, major conflicts, turning points, or consequential user choices unless the new batch explicitly resolves or changes them. "
            "Remove duplicates, expired scene details, completed minor actions, and details that cannot affect continuation before removing protected memory. Keep the complete JSON ledger within 15000 characters. "
            "The batch contains complete conversational turns and must be treated as one continuous semantic unit. "
            "If new_story_batch is non-empty, never return an entirely empty JSON object."
        )
    else:
        sys_prompt = (
            "你是互动故事的高保真场记。把 previous_state 与完整的 new_story_batch 合并成新的剧情账本，所有文本值使用简体中文；必要时翻译旧账本内容，同时保留姓名与事实。"
            "只记录已经发生或仍在推进的剧情事件、因果事实、秘密、关键物件、伏笔、重大承诺、冲突、转折与关键选择。"
            "剧情账本是场景地点、角色所处位置与行动、剧情事实、角色认知边界和物品归属的唯一来源。"
            "不要保存人物性格、身份、能力、长期身份变化、长期身体情况或当前关系结论；这些属于角色档案。关系变化只能作为时间线事件记录。"
            "不要文学点评，不猜测未发生内容。输出严格 JSON，对象字段只能是 timeline、facts、open_threads、objects、secrets、scene、style_notes。"
            "facts 与 secrets 的每项包含 id、content、known_by；known_by 只能填写角色 id 或 __user__。objects 的每项包含 id、name、status、holder、location。scene 包含 time、place、participants；每名参与者包含 character_id、location、activity、condition。"
            "所有数组条目必须短而具体，禁止长篇散文，禁止重复。"
            "主要数组最多保留 12 条；timeline/facts 每条不超过 60 个汉字；open_threads 每条不超过 80 个汉字。"
            "未解决线索、未揭露秘密、关键物品、身份揭露、重大承诺、核心冲突、剧情转折和用户关键选择，在新批次明确解决或改变之前不得删除。"
            "容量不足时，先删除重复表述、过时场景、已完成的小动作和不影响后续的细节，再考虑其他内容；完整 JSON 账本不得超过 15000 字符。"
            "这一批包含完整连续的对话轮次，必须作为一个语义整体理解，不得在事件中间切断。"
            "如果 new_story_batch 非空，严禁返回全空 JSON。"
        )
    user = json.dumps({
        "previous_state": prev or {},
        "new_story_batch": batch,
        "response_language": language,
        "range": {
            "start_turn": start_turn,
            "end_turn": end_turn,
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
            print("story_state batch model failed with %s:" % mem_model.get("model"), repr(e), file=sys.stderr, flush=True)
    if not out:
        print("story_state batch model failed:", repr(last_error), file=sys.stderr, flush=True)
        return None

    try:
        raw = _json_from_model_text(out)
    except Exception:
        raw = None
        last_error = None
        for mem_model in _memory_models():
            try:
                repair_prompt = ((
                    "Repair the user's content into strict JSON and write all textual values in English. Output only a JSON object using timeline, facts, open_threads, objects, secrets, scene, and style_notes."
                ) if language == "en" else (
                    "把用户给出的内容修复为严格 JSON，所有文本值使用简体中文。只输出 JSON 对象。"
                    "字段只能是 timeline、facts、open_threads、objects、secrets、scene、style_notes。"
                ))
                repair = actor.chat([
                    {"role": "system", "content": repair_prompt},
                    {"role": "user", "content": out[:9000]},
                ], temperature=0.0, model=mem_model, max_tokens=2500).strip()
                raw = _json_from_model_text(repair)
                break
            except Exception as e:
                last_error = e
                print("story_state batch parse repair failed with %s:" % mem_model.get("model"), repr(e), file=sys.stderr, flush=True)
        if raw is None:
            print("story_state batch parse failed:", repr(last_error), file=sys.stderr, flush=True)
            return None
    state = _normalize_story_state(raw, end_turn, source_tokens)
    state["response_language"] = language
    if not _story_state_has_memory(state):
        print("story_state batch empty; keeping previous memory", file=sys.stderr, flush=True)
        return None
    if not _story_state_quality_ok(prev or {}, state):
        print("story_state batch lost protected memory; keeping previous memory", file=sys.stderr, flush=True)
        return None
    return state


_PROFILE_CHANGE_FIELDS = {
    "identity": {
        "name", "aliases", "description", "gender", "age", "species",
        "occupation", "affiliations", "story_role",
    },
    "appearance": {"summary", "features"},
    "personality": {"summary", "traits", "values", "motivation", "fears", "boundaries"},
    "expression": {"speech_style", "habits", "mannerisms"},
    "capabilities": {"skills", "powers", "limitations"},
}
_PROFILE_LIST_FIELDS = {
    "aliases", "affiliations", "features", "traits", "values", "fears",
    "boundaries", "habits", "mannerisms", "skills", "powers", "limitations",
}


def _validated_change_evidence(value, start_turn, end_turn):
    values = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
    out = []
    for raw in values:
        if not isinstance(raw, dict):
            continue
        try:
            turn = int(raw.get("turn"))
        except (TypeError, ValueError):
            continue
        fact = _clip_memory_text(raw.get("fact"), 300)
        reason = _clip_memory_text(raw.get("reason"), 300)
        if start_turn <= turn <= end_turn and fact and reason:
            out.append({"turn": turn, "fact": fact, "reason": reason})
    return out[:6]


def _merge_profile_changes(current, changes):
    """Apply non-empty whitelisted fields to the current profile."""
    before = _canonical_profile_snapshot(current)
    merged = json.loads(json.dumps(before, ensure_ascii=False))
    incoming = changes if isinstance(changes, dict) else {}
    for section, allowed_fields in _PROFILE_CHANGE_FIELDS.items():
        section_changes = incoming.get(section)
        if not isinstance(section_changes, dict):
            section_changes = {}
        target = merged.setdefault(section, {})
        for field in allowed_fields:
            if field in section_changes:
                raw = section_changes.get(field)
            elif field != "summary":
                misplaced = [values.get(field) for values in incoming.values()
                             if isinstance(values, dict) and field in values]
                if not misplaced:
                    continue
                raw = misplaced[0]
            else:
                continue
            if field in _PROFILE_LIST_FIELDS:
                values = raw if isinstance(raw, list) else ([raw] if raw else [])
                cleaned = []
                for value in values:
                    text = _clip_memory_text(value, 240)
                    if text and text not in cleaned:
                        cleaned.append(text)
                if cleaned:
                    target[field] = cleaned[:12]
            else:
                limit = 2500 if field in ("description", "summary") else 600
                text = _clip_memory_text(raw, limit)
                if text:
                    target[field] = text
    old_name = str((before.get("identity") or {}).get("name") or "").strip()
    new_name = str((merged.get("identity") or {}).get("name") or "").strip()
    if old_name and new_name and old_name != new_name:
        aliases = list((merged.get("identity") or {}).get("aliases") or [])
        if old_name not in aliases:
            aliases.append(old_name)
        merged["identity"]["aliases"] = aliases[:8]
    result = _canonical_profile_snapshot(merged)
    return result, result != before


def _merge_persistent_status_changes(current, changes):
    before = _normalize_persistent_status(current or {})
    merged = dict(before)
    incoming = changes if isinstance(changes, dict) else {}
    for field, limit in (("life_status", 80), ("physical_condition", 600)):
        if field in incoming:
            text = _clip_memory_text(incoming.get(field), limit)
            if text:
                merged[field] = text
    result = _normalize_persistent_status(merged)
    return result, result != before


def _runtime_cast_missing_fields(raw):
    """List fields named by evidence but omitted from the emitted change payload."""
    raw = raw if isinstance(raw, dict) else {}
    candidates = []
    character_changes = raw.get("character_changes")
    if isinstance(character_changes, dict):
        candidates.extend(value for value in character_changes.values() if isinstance(value, dict))
    if isinstance(raw.get("user_changes"), dict):
        candidates.append(raw["user_changes"])
    field_names = set().union(*_PROFILE_CHANGE_FIELDS.values()) | {
        "life_status", "physical_condition",
    }
    missing = []
    for candidate in candidates:
        emitted = set()
        profile = candidate.get("profile") if isinstance(candidate.get("profile"), dict) else {}
        for values in profile.values():
            if isinstance(values, dict):
                emitted.update(str(key) for key in values)
        status = candidate.get("persistent_status")
        if isinstance(status, dict):
            emitted.update(str(key) for key in status)
        evidence_values = candidate.get("evidence")
        evidence_values = evidence_values if isinstance(evidence_values, list) else [evidence_values]
        evidence_text = " ".join(
            str(item.get("reason") or "") for item in evidence_values if isinstance(item, dict))
        for field in field_names:
            if re.search(r"(?<![A-Za-z0-9_])" + re.escape(field) + r"(?![A-Za-z0-9_])",
                         evidence_text) and field not in emitted:
                missing.append(field)
    return sorted(set(missing))


def _runtime_cast_change_set_consistent(raw):
    return not _runtime_cast_missing_fields(raw)


def _normalize_runtime_cast_result(raw, previous, start_turn, end_turn, persona=None):
    """Validate an evidence-backed change set and apply it to one durable cast snapshot."""
    raw = raw if isinstance(raw, dict) else {}
    previous = previous if isinstance(previous, dict) else {}
    raw_changes = raw.get("character_changes") if isinstance(raw.get("character_changes"), dict) else {}
    characters = []
    for old in previous.get("characters") or []:
        if not isinstance(old, dict):
            continue
        item = _runtime_character(old, applied_turn=int(previous.get("applied_turn") or 0))
        candidate = raw_changes.get(str(item.get("id")))
        evidence = _validated_change_evidence(
            candidate.get("evidence") if isinstance(candidate, dict) else None,
            start_turn, end_turn)
        profile_changed = status_changed = False
        if evidence:
            item["profile"], profile_changed = _merge_profile_changes(
                item.get("profile") or {}, candidate.get("profile") or {})
            item["persistent_status"], status_changed = _merge_persistent_status_changes(
                item.get("persistent_status") or {}, candidate.get("persistent_status") or {})
        if profile_changed:
            item["profile_updated_turn"] = end_turn
            item["last_change_evidence"] = evidence
        if status_changed:
            item["status_updated_turn"] = end_turn
            item["last_change_evidence"] = evidence
        identity = item["profile"]["identity"]
        item["name"] = identity.get("name") or item.get("name") or ""
        item["description"] = identity.get("description") or ""
        item["personality"] = item["profile"]["personality"].get("summary") or ""
        characters.append(item)

    previous_user_profile = _canonical_profile_snapshot(
        previous.get("user_profile") or (persona or {}).get("profile") or persona or {})
    previous_user_status = _normalize_persistent_status(previous.get("user_status") or {})
    user_profile = previous_user_profile
    user_status = previous_user_status
    user_profile_changed = user_status_changed = False
    user_candidate = raw.get("user_changes") if isinstance(raw.get("user_changes"), dict) else {}
    user_evidence = _validated_change_evidence(user_candidate.get("evidence"), start_turn, end_turn)
    if user_evidence:
        user_profile, user_profile_changed = _merge_profile_changes(
            previous_user_profile, user_candidate.get("profile") or {})
        user_status, user_status_changed = _merge_persistent_status_changes(
            previous_user_status, user_candidate.get("persistent_status") or {})

    previous_relationships = _normalize_relationships(
        previous.get("relationships") or [], characters, persona or {})
    relationships_by_key = {
        "|".join(item.get("participants") or []): dict(item)
        for item in previous_relationships
    }
    valid_ids = {str(item.get("id")) for item in characters if item.get("id")}
    valid_ids.add("__user__")
    relation_changes = raw.get("relationship_changes")
    if not isinstance(relation_changes, list):
        relation_changes = []
    for change in relation_changes:
        if not isinstance(change, dict):
            continue
        evidence = _validated_change_evidence(change.get("evidence"), start_turn, end_turn)
        participants = sorted({str(value) for value in (change.get("participants") or [])})
        if not evidence or len(participants) != 2 or any(value not in valid_ids for value in participants):
            continue
        key = "|".join(participants)
        action = str(change.get("action") or "upsert").strip().lower()
        if action == "remove":
            relationships_by_key.pop(key, None)
            continue
        description = _clip_memory_text(change.get("description"), 300)
        if action == "upsert" and description:
            relationships_by_key[key] = {
                "participants": participants,
                "description": description,
                "updated_turn": end_turn,
            }
    relationships = _normalize_relationships(
        list(relationships_by_key.values()), characters, persona or {})

    result = {
        "schema_version": 3,
        "applied_turn": end_turn,
        "revision": int(previous.get("revision") or 0) + 1,
        "characters": characters,
        "origin_user_profile": _canonical_profile_snapshot(
            previous.get("origin_user_profile") or previous_user_profile),
        "user_profile": user_profile,
        "user_profile_updated_turn": (
            end_turn if user_profile_changed
            else int(previous.get("user_profile_updated_turn") or 0)),
        "user_status": user_status,
        "user_status_updated_turn": (
            end_turn if user_status_changed
            else int(previous.get("user_status_updated_turn") or 0)),
        "relationships": relationships,
        "updated_at": int(time.time()),
    }
    if user_profile_changed or user_status_changed:
        result["user_last_change_evidence"] = user_evidence
    elif previous.get("user_last_change_evidence"):
        result["user_last_change_evidence"] = previous.get("user_last_change_evidence")
    return result


def _merge_runtime_cast_batch(previous, batch, start_turn, end_turn,
                              response_language="zh", persona=None):
    """Build the next cast snapshot from evidence-backed durable changes."""
    previous = previous if isinstance(previous, dict) else {}
    language = _locale_code(response_language)
    roster = [{"id": c.get("id"), "name": c.get("name")}
              for c in (previous.get("characters") or []) if isinstance(c, dict)]
    if not roster:
        result = dict(previous)
        result["applied_turn"] = end_turn
        result["revision"] = int(previous.get("revision") or 0) + 1
        result["updated_at"] = int(time.time())
        return result
    if language == "en":
        system_prompt = (
            "# Responsibility\n"
            "You maintain the long-lived character profiles for an interactive story. Compare each immutable origin_profile, the previous effective profile and status, and the complete numbered new_story_batch. Submit only durable changes explicitly established in this batch. Do not continue or summarize the story.\n"
            "# Boundaries\n"
            "origin_profile is read-only. current_profile is the only effective profile. Never add, remove, merge, or rename character ids. Temporary emotion, action, location, short-term goal, clothing, knowledge, and held objects belong to the story ledger.\n"
            "Names, aliases, identity, durable appearance, personality, expression, abilities, physical condition, and relationships may change only when the batch clearly establishes a lasting change. A passing mood, disguise, joke, claim, conversation, or co-presence is not enough. Use aliases for temporary codenames; change name only for a formal rename, identity reveal, or lasting adoption. Personality changes require repeated behavior, explicit self-transformation, or a consequential event.\n"
            "For the user character, record only facts explicitly chosen by the user or objectively completed in the story. Never infer the user's personality, feelings, intent, speech, action, or decision.\n"
            "# Allowed fields\n"
            "profile.identity: name, aliases, description, gender, age, species, occupation, affiliations, story_role. profile.appearance: summary, features. profile.personality: summary, traits, values, motivation, fears, boundaries. profile.expression: speech_style, habits, mannerisms. profile.capabilities: skills, powers, limitations. persistent_status: life_status, physical_condition.\n"
            "# Evidence\n"
            "Every submitted entity change needs evidence entries with turn, fact, and reason. turn must be within the supplied range and refer to a numbered turn in new_story_batch. If a reason names a field such as occupation, that exact field and its new value must also be present under profile or persistent_status. Never describe a change only in evidence. Without sufficient evidence, omit the change. Never use empty strings or empty arrays to erase existing data.\n"
            "# Output\n"
            "Output strict JSON only, with character_changes, user_changes, and relationship_changes. character_changes is keyed only by supplied character id. Each value may contain profile, persistent_status, and evidence. profile must preserve the exact section hierarchy listed above; for example occupation must be under profile.identity, never profile.capabilities. user_changes uses the same shape. Each relationship change contains participants, action (upsert or remove), description, and evidence. Output empty objects or arrays when nothing changed."
        )
    else:
        system_prompt = (
            "# 职责\n"
            "你维护互动故事的长期角色档案。对照每名角色不可修改的 origin_profile、上一版唯一生效档案与持续状态，以及带回合编号的完整 new_story_batch，只提交本批剧情已经明确成立的长期变化。不要续写或总结剧情。\n"
            "# 数据边界\n"
            "origin_profile 只用于理解和核对，绝不修改；current_profile 是当前唯一生效档案。不得增加、删除、合并角色或修改角色 id。临时情绪、当前动作、所在地点、短期目标、临时着装、认知和持有物属于剧情账本，不写入角色档案。\n"
            "姓名、别名、身份、长期外貌、性格、表达方式、能力、身体情况和关系可以变化，但必须是本批剧情明确建立且会影响后续演绎的持续变化。单次情绪、伪装、玩笑、单方面声称、交谈或同场均不足以构成长期变化。临时代号写入 aliases；只有正式改名、身份揭露或长期采用新名字时才修改 name。性格变化必须有反复表现、明确自我转变或重大事件作为依据。\n"
            "用户角色只记录用户明确选择或剧情已经客观完成的变化；不得推断用户的性格、感受、意图、对白、行动或决定。\n"
            "# 允许更新的字段\n"
            "profile.identity：name、aliases、description、gender、age、species、occupation、affiliations、story_role。profile.appearance：summary、features。profile.personality：summary、traits、values、motivation、fears、boundaries。profile.expression：speech_style、habits、mannerisms。profile.capabilities：skills、powers、limitations。persistent_status：life_status、physical_condition。\n"
            "# 证据要求\n"
            "每个提交的实体变化都必须提供 evidence，其中每项包含 turn、fact、reason。turn 必须位于给定 range 内，并对应 new_story_batch 中标注的回合。reason 如果点名 occupation 等字段，profile 或 persistent_status 中必须同时携带该字段及其新值，禁止只在证据里描述变化。证据不足就省略该变化。不得用空字符串或空数组覆盖已有内容。\n"
            "# 输出格式\n"
            "只输出严格 JSON，顶层字段只能是 character_changes、user_changes、relationship_changes。character_changes 只能以给定角色 id 为键，每项可包含 profile、persistent_status、evidence。profile 必须严格保持上文列出的分区层级，例如 occupation 必须位于 profile.identity，绝不能放入 profile.capabilities。user_changes 结构相同。relationship_changes 每项包含 participants、action（upsert 或 remove）、description、evidence。没有变化时输出空对象或空数组。"
        )
    payload = json.dumps({
        "roster": roster,
        "user_persona": persona or {},
        "previous_cast": {
            "characters": {str(c.get("id")): {
                               "origin_profile": c.get("origin_profile") or c.get("profile") or {},
                               "current_profile": c.get("profile") or {},
                               "persistent_status": c.get("persistent_status") or {},
                           }
                           for c in previous.get("characters") or [] if isinstance(c, dict)},
            "origin_user_profile": previous.get("origin_user_profile") or {},
            "current_user_profile": previous.get("user_profile") or (persona or {}).get("profile") or {},
            "user_status": previous.get("user_status") or {},
            "relationships": previous.get("relationships") or [],
        },
        "new_story_batch": batch,
        "range": {"start_turn": start_turn, "end_turn": end_turn},
    }, ensure_ascii=False)
    last_error = None
    for mem_model in _memory_models():
        try:
            out = actor.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": payload},
            ], temperature=0.1, model=mem_model, max_tokens=4500).strip()
            raw = _json_from_model_text(out)
            missing_fields = _runtime_cast_missing_fields(raw)
            if missing_fields:
                repair_prompt = ((
                    "Repair one character change-set JSON without re-analyzing or continuing the story. "
                    "Some evidence reasons name fields that are missing from the change payload. Put each explicitly established new value under the exact allowed profile hierarchy (for example profile.identity.occupation), or remove only the unsupported evidence. Never invent a value. Preserve valid changes and evidence. Output strict JSON only."
                ) if language == "en" else (
                    "修复一份角色变化集 JSON，不要重新分析或续写剧情。部分 evidence.reason 点名了字段，但变化对象漏掉了对应字段。"
                    "把证据中已经明确成立的新值放回正确的允许层级（例如 profile.identity.occupation）；如果证据无法确定新值，只删除那条无效证据。"
                    "不得猜测，不得删除其他有效变化。只输出严格 JSON。"
                ))
                repair_payload = json.dumps({
                    "missing_fields": missing_fields,
                    "change_set": raw,
                }, ensure_ascii=False)
                repaired = actor.chat([
                    {"role": "system", "content": repair_prompt},
                    {"role": "user", "content": repair_payload},
                ], temperature=0.0, model=mem_model, max_tokens=4500).strip()
                raw = _json_from_model_text(repaired)
            if not _runtime_cast_change_set_consistent(raw):
                raise ValueError("cast change evidence and emitted fields disagree after repair")
            result = _normalize_runtime_cast_result(
                raw, previous, start_turn, end_turn, persona)
            if len(result.get("characters") or []) == len(previous.get("characters") or []):
                return result
        except Exception as error:
            last_error = error
            print("runtime_cast batch failed with %s:" % mem_model.get("model"), repr(error),
                  file=sys.stderr, flush=True)
    print("runtime_cast batch failed:", repr(last_error), file=sys.stderr, flush=True)
    return None


_STORY_STATE_RUN_LOCKS = {}
_STORY_STATE_RUN_LOCKS_GUARD = threading.Lock()
_STORY_STATE_JOBS = set()
_STORY_STATE_PENDING = set()
_STORY_STATE_JOBS_LOCK = threading.Lock()


def _story_state_progress(p):
    story = (p or {}).get("story") or []
    compressible_turns = _compressible_story_turns(story)
    previous = _validated_story_state((p or {}).get("story_state") or {}, story)
    covered_turns = int(previous.get("turns") or 0)
    return compressible_turns, covered_turns


def _story_state_sync_trigger(pid):
    """Describe the checkpoint a client should watch without delaying the reply."""
    p = load_production(pid)
    if not p:
        return {"watch": False, "revision": 0}
    compressible_turns, covered_turns = _story_state_progress(p)
    runtime_cast = _ensure_runtime_cast(p)
    due = compressible_turns - covered_turns >= STORY_STATE_BATCH_TURNS
    return {
        "watch": due,
        "revision": int(runtime_cast.get("revision") or 0),
        "target_turn": covered_turns + STORY_STATE_BATCH_TURNS if due else covered_turns,
    }


def _story_state_sync_view(pid, since_revision=0):
    """Return a small polling response and projections only after a completed commit."""
    p = load_production(pid)
    if not p:
        return None
    compressible_turns, covered_turns = _story_state_progress(p)
    runtime_cast = _ensure_runtime_cast(p)
    revision = int(runtime_cast.get("revision") or 0)
    with _STORY_STATE_JOBS_LOCK:
        pending = pid in _STORY_STATE_JOBS
    changed = revision != int(since_revision or 0)
    result = {
        "production_id": pid,
        "pending": pending,
        "due": compressible_turns - covered_turns >= STORY_STATE_BATCH_TURNS,
        "changed": changed,
        "ready": changed and not pending,
        "revision": revision,
        "applied_turn": int(runtime_cast.get("applied_turn") or 0),
        "story_state_turns": covered_turns,
        "error": str(((p.get("runtime") or {}).get("story_state_error") or ""))[:500],
    }
    if result["ready"]:
        result.update({
            "runtime_cast": runtime_cast,
            "cards": p.get("cards") or [],
            "persona": p.get("persona") or {},
        })
    return result


def _story_state_run_lock(pid):
    with _STORY_STATE_RUN_LOCKS_GUARD:
        return _STORY_STATE_RUN_LOCKS.setdefault(pid, threading.Lock())


def _story_prefix_signature(story, end_turn):
    messages = _story_messages_through_turn(story, end_turn)
    payload = [(m.get("id"), m.get("role"), m.get("text") or "") for m in messages]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()


def _commit_story_state_batch(pid, state, runtime_cast, end_turn, expected_signature,
                              expected_cast_revision):
    """Atomically publish one complete plot ledger and cast snapshot checkpoint."""
    with _production_lock(pid):
        current = load_production(pid)
        if not current:
            return None
        if _story_prefix_signature(current.get("story") or [], end_turn) != expected_signature:
            return None
        current_cast = _ensure_runtime_cast(current)
        if int(current_cast.get("revision") or 0) != int(expected_cast_revision or 0):
            return None
        published = dict(state)
        published["turns"] = end_turn
        published["covered_signature"] = expected_signature
        published.pop("stale", None)
        current["story_state"] = published
        current["runtime_cast"] = runtime_cast
        _hydrate_runtime_cards(current)
        _hydrate_user_persona(current)
        runtime = dict(current.get("runtime") or {})
        runtime.pop("state_stale_reason", None)
        runtime.pop("story_state_error", None)
        current["runtime"] = runtime
        record = _production_record(current)
        _write(os.path.join(STATE, "productions", pid + ".json"), record)
        return current


def _record_story_state_error(pid, error):
    with _production_lock(pid):
        current = load_production(pid)
        if not current:
            return
        runtime = dict(current.get("runtime") or {})
        runtime["story_state_error"] = str(error)[:500]
        current["runtime"] = runtime
        record = _production_record(current)
        _write(os.path.join(STATE, "productions", pid + ".json"), record)


def _summarize_story_state(p, force_full=False):
    """Compress confirmed 15-turn batches and publish each batch only on success."""
    pid = p["id"]
    with _story_state_run_lock(pid):
        snapshot = load_production(pid) or p
        story = snapshot.get("story") or []
        compressible_turns = _compressible_story_turns(story)
        stored_previous = snapshot.get("story_state") or {}
        previous = _validated_story_state(stored_previous, story)
        rebuild = force_full or (bool(stored_previous) and not previous)
        state = {} if rebuild else dict(previous)
        covered_turns = 0 if rebuild else int(previous.get("turns") or 0)
        cast_state = _ensure_runtime_cast(snapshot)
        if rebuild:
            # A plot-ledger rebuild must never replay or reset character evolution.
            # Rebuild the ledger in memory, then atomically move the preserved cast
            # checkpoint to the rebuilt ledger boundary without a cast model call.
            rebuilt_state = {}
            rebuilt_turns = 0
            language = _ensure_world_language(snapshot)
            while compressible_turns - rebuilt_turns >= STORY_STATE_BATCH_TURNS:
                start_turn = rebuilt_turns + 1
                end_turn = rebuilt_turns + STORY_STATE_BATCH_TURNS
                segments = _story_batch_segments(snapshot, start_turn, end_turn)
                if not segments or not any(batch.strip() for _, _, batch in segments):
                    _record_story_state_error(pid, "empty story batch during ledger rebuild")
                    return previous if previous else {}
                merged = rebuilt_state
                for segment_start, segment_end, batch in segments:
                    prefix = _story_messages_through_turn(story, segment_end)
                    source_tokens = _story_token_estimate(prefix)
                    merged = _merge_story_state_batch(
                        merged, batch, segment_start, segment_end, source_tokens, language)
                    if not merged:
                        break
                if not merged:
                    _record_story_state_error(
                        pid, f"ledger rebuild failed for turns {start_turn}-{end_turn}")
                    return previous if previous else {}
                rebuilt_state = merged
                rebuilt_turns = end_turn
            if not rebuilt_turns:
                return previous if previous else {}
            preserved_cast = json.loads(json.dumps(cast_state, ensure_ascii=False))
            expected_cast_revision = int(cast_state.get("revision") or 0)
            preserved_cast["applied_turn"] = rebuilt_turns
            preserved_cast["revision"] = expected_cast_revision + 1
            preserved_cast["updated_at"] = int(time.time())
            signature = _story_prefix_signature(story, rebuilt_turns)
            committed = _commit_story_state_batch(
                pid, rebuilt_state, preserved_cast, rebuilt_turns, signature,
                expected_cast_revision)
            if not committed:
                _record_story_state_error(pid, "story or cast changed during ledger rebuild")
                return previous if previous else {}
            return rebuilt_state
        if int(cast_state.get("applied_turn") or 0) != covered_turns:
            _record_story_state_error(pid, "cast snapshot and plot ledger checkpoints differ")
            return previous if previous else {}
        language = _ensure_world_language(snapshot)

        while compressible_turns - covered_turns >= STORY_STATE_BATCH_TURNS:
            start_turn = covered_turns + 1
            end_turn = covered_turns + STORY_STATE_BATCH_TURNS
            segments = _story_batch_segments(snapshot, start_turn, end_turn)
            if not segments or not any(batch.strip() for _, _, batch in segments):
                _record_story_state_error(pid, "empty story batch")
                break
            signature = _story_prefix_signature(story, end_turn)
            merged = state
            for segment_start, segment_end, batch in segments:
                prefix = _story_messages_through_turn(story, segment_end)
                source_tokens = _story_token_estimate(prefix)
                merged = _merge_story_state_batch(
                    merged, batch, segment_start, segment_end, source_tokens, language)
                if not merged:
                    break
            if not merged:
                _record_story_state_error(pid, f"compression failed for turns {start_turn}-{end_turn}")
                break
            complete_batch = _story_lines_for_turns(snapshot, start_turn, end_turn)
            expected_cast_revision = int(cast_state.get("revision") or 0)
            merged_cast = _merge_runtime_cast_batch(
                cast_state, complete_batch, start_turn, end_turn, language,
                snapshot.get("persona") or {})
            if not merged_cast:
                _record_story_state_error(pid, f"cast snapshot failed for turns {start_turn}-{end_turn}")
                break
            committed = _commit_story_state_batch(
                pid, merged, merged_cast, end_turn, signature, expected_cast_revision)
            if not committed:
                _record_story_state_error(pid, f"story or cast changed while processing turns {start_turn}-{end_turn}")
                break
            state = merged
            cast_state = merged_cast
            covered_turns = end_turn

        return state if _story_state_has_memory(state) else (previous if previous else {})

def ev_story_state(ev):
    p = load_production(ev["production_id"])
    if not p:
        raise ValueError("production not found")
    if ev.get("refresh"):
        return {"story_state": _summarize_story_state(p, force_full=True), "production_id": p["id"]}
    return {"story_state": p.get("story_state") or {}, "production_id": p["id"]}


def _maybe_auto_story_state(pid):
    while True:
        p = load_production(pid)
        if not p:
            return
        story = p.get("story") or []
        compressible_turns = _compressible_story_turns(story)
        prev = _validated_story_state(p.get("story_state") or {}, story)
        done_turns = int(prev.get("turns") or 0)
        if compressible_turns - done_turns < STORY_STATE_BATCH_TURNS:
            return
        try:
            _summarize_story_state(p)
        except Exception as error:
            _record_story_state_error(pid, error)
            return
        latest = load_production(pid) or {}
        latest_state = latest.get("story_state") or {}
        latest_done = int(latest_state.get("turns") or 0)
        if latest_done <= done_turns:
            return


def _story_state_job(pid):
    try:
        while True:
            _maybe_auto_story_state(pid)
            with _STORY_STATE_JOBS_LOCK:
                if pid in _STORY_STATE_PENDING:
                    _STORY_STATE_PENDING.discard(pid)
                    continue
                _STORY_STATE_JOBS.discard(pid)
                return
    finally:
        with _STORY_STATE_JOBS_LOCK:
            _STORY_STATE_JOBS.discard(pid)
            _STORY_STATE_PENDING.discard(pid)


def _schedule_story_state(pid):
    with _STORY_STATE_JOBS_LOCK:
        if pid in _STORY_STATE_JOBS:
            _STORY_STATE_PENDING.add(pid)
            return False
        _STORY_STATE_JOBS.add(pid)
    threading.Thread(target=_story_state_job, args=(pid,), daemon=True).start()
    return True


def _schedule_story_state_backlog():
    directory = os.path.join(STATE, "productions")
    try:
        names = os.listdir(directory)
    except OSError:
        return
    for name in names:
        if name.startswith("prod_") and name.endswith(".json"):
            _schedule_story_state(name[:-5])


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
    pid = ev.get("production_id")
    if pid:
        p = load_production(pid)
        if not p:
            raise ValueError("production not found")
        source_card_id = str(ev.get("card_id") or "").strip()
        if source_card_id:
            source = load_card(source_card_id)
            if not source:
                raise ValueError("persona card not found")
            persona = _normalize_persona({**source, "source_card_id": source_card_id})
            status = _normalize_persistent_status({})
        else:
            current = _normalize_persona(p.get("persona") or {})
            merged_profile = json.loads(json.dumps(current.get("profile") or {}, ensure_ascii=False))
            incoming_profile = ev.get("profile") if isinstance(ev.get("profile"), dict) else {}
            for section, values in incoming_profile.items():
                if isinstance(values, dict):
                    merged_profile.setdefault(section, {}).update(values)
            if "name" in ev:
                merged_profile.setdefault("identity", {})["name"] = str(ev.get("name") or "").strip()
            if "description" in ev:
                merged_profile.setdefault("identity", {})["description"] = str(ev.get("description") or "").strip()
            persona = _normalize_persona({"profile": merged_profile})
            current_status = (p.get("runtime_cast") or {}).get("user_status") or {}
            status = _normalize_persistent_status(
                ev.get("persistent_status") if isinstance(ev.get("persistent_status"), dict)
                else current_status)
        p["persona"] = persona
        runtime_cast = _ensure_runtime_cast(p)
        current_profile = _canonical_profile_snapshot(persona.get("profile") or persona)
        runtime_cast["user_profile"] = current_profile
        runtime_cast["user_profile_updated_turn"] = _world_turns(p.get("story") or [])
        if (source_card_id or not _profile_has_content(runtime_cast.get("origin_user_profile") or {})
                or _world_turns(p.get("story") or []) == 0):
            runtime_cast["origin_user_profile"] = json.loads(json.dumps(
                current_profile, ensure_ascii=False))
        runtime_cast["user_status"] = status
        runtime_cast["revision"] = int(runtime_cast.get("revision") or 0) + 1
        runtime_cast["updated_at"] = int(time.time())
        p["turn_plan"] = {}
        _hydrate_user_persona(p)
        save_production(p)
        return {"persona": p["persona"], "production": p}
    persona = _normalize_persona({"name": ev.get("name", "我"), "description": ev.get("description", "")})
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
# 用户自配的大模型使用 OpenAI-compatible 协议。官方目录固定为 Tavern 支持的模型；
# 自定义配置可由 reader 或 CLI 写入。key 只落 server 端 state 文件（0600），
# 任何读端点一律脱敏。
MODELS_PATH = os.path.join(STATE, "model_configs.json")
HERMES_CONFIG_PATH = os.environ.get("HERMES_CONFIG_PATH", "/opt/data/config.yaml")
OFFICIAL_MODELS = ("deepseek-v4-flash",)


def _official_models():
    """Return the intentionally small Tavern official model catalog."""
    return list(OFFICIAL_MODELS)


def _clawling_model_id(model_name):
    return "builtin" if model_name == OFFICIAL_MODELS[0] else "clawling:" + model_name


def _clawling_model_name(model_id):
    if model_id == "builtin":
        return OFFICIAL_MODELS[0]
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
    if cname in _official_models():
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
        "default": m == OFFICIAL_MODELS[0],
        "key_set": bool(actor.MODEL_KEY),
        "kind": "official",
    } for m in _official_models()]
    custom_configs = [{"id": c["id"], "name": c["name"], "model": c["model"],
                       "base": c["base"], "key_masked": _mask_key(c.get("key")),
                       "added_at": c.get("added_at"), "kind": "custom"} for c in s["configs"]]
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
    if ref in ("内置模型", actor.MODEL_NAME, OFFICIAL_MODELS[0]):
        ref = "builtin"
        cname = OFFICIAL_MODELS[0]
    if cname in _official_models():
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
            return self._json(200, {"cards": _library_cards()})
        if path == "/api/worldbooks":
            return self._json(200, {"worldbooks": _list("worldbooks")})
        if path == "/api/library/cards":
            return self._json(200, {"cards": _library_cards()})
        if path == "/api/library/worldbooks":
            return self._json(200, {"worldbooks": _library_worldbooks()})
        if path == "/api/production/worldbooks":
            pid = parse_qs(urlparse(self.path).query).get("production_id", [""])[0]
            return self._json(200, {"worldbooks": _production_worldbooks(pid)})
        if path == "/api/production/state-sync":
            q = parse_qs(urlparse(self.path).query)
            pid = q.get("production_id", [""])[0]
            try:
                since_revision = int(q.get("since", ["0"])[0] or 0)
            except (TypeError, ValueError):
                since_revision = 0
            result = _story_state_sync_view(pid, since_revision)
            if result is None:
                return self._json(404, {"error": "production not found"})
            return self._json(200, result)
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
    _cleanup_tts_disk_cache(force=True)
    migrated = _migrate_worldbook_storage()
    if migrated:
        print(f"worldbook storage migrated: {migrated} production(s)", flush=True)
    print("酒馆演员运行时 → http://%s:%d  (model=%s, key=%s)" % (
        host, port, actor.MODEL_NAME, "set" if actor.MODEL_KEY else "MISSING"))
    _schedule_story_state_backlog()
    ThreadingHTTPServer((host, port), H).serve_forever()


if __name__ == "__main__":
    main()
