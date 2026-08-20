#!/usr/bin/env python3
"""Inspect, probe, and atomically configure Hermes and Tavern model APIs."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import yaml
except ImportError as exc:  # Hermes itself depends on YAML support.
    raise SystemExit(f"PyYAML is required by this Hermes installation: {exc}")


HERMES_CONFIG = Path(os.environ.get("HERMES_CONFIG_PATH", "/opt/data/config.yaml"))
HERMES_ENV = Path(os.environ.get("HERMES_ENV_PATH", "/opt/data/.env"))
TAVERN_CONSOLE = os.environ.get("TAVERN_CONSOLE", "http://127.0.0.1:8799").rstrip("/")
TAVERN_MODELS = Path(os.environ.get("TAVERN_MODELS_PATH", "/opt/data/tavern-state/model_configs.json"))
TAVERN_CLI = Path(os.environ.get(
    "TAVERN_CLI",
    "/opt/data/skills/creative/tavern/scripts/tavern_cli.py",
))


class ManagerError(RuntimeError):
    pass


def emit(operation: str, **data) -> None:
    print(json.dumps({"ok": True, "operation": operation, **data}, ensure_ascii=False, indent=2))


def fail(message: str, *, details=None) -> None:
    payload = {"ok": False, "error": message}
    if details is not None:
        payload["details"] = details
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
    raise SystemExit(1)


def mask_key(value: str) -> str:
    if not value:
        return "not-set"
    return "***" + value[-4:] if len(value) >= 4 else "***"


def slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not result:
        raise ManagerError("provider name must contain letters or numbers")
    return result


def env_name(value: str) -> str:
    name = re.sub(r"[^A-Z0-9]+", "_", value.strip().upper()).strip("_")
    if not name or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", name):
        raise ManagerError("invalid environment variable name")
    return name


def load_env(path: Path | None = None) -> dict[str, str]:
    path = path or HERMES_ENV
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def store_env_secret(name: str, secret: str) -> None:
    name = env_name(name)
    if not secret.strip():
        raise ManagerError("API key cannot be empty")
    HERMES_ENV.parent.mkdir(parents=True, exist_ok=True)
    lines = HERMES_ENV.read_text(encoding="utf-8").splitlines() if HERMES_ENV.exists() else []
    replacement = f"{name}={secret.strip()}"
    found = False
    output = []
    for line in lines:
        if line.split("=", 1)[0].strip() == name and not line.lstrip().startswith("#"):
            output.append(replacement)
            found = True
        else:
            output.append(line)
    if not found:
        output.append(replacement)
    atomic_write(HERMES_ENV, ("\n".join(output).rstrip() + "\n").encode(), 0o600)


def key_from_env(name: str, *, allow_no_key: bool = False) -> str:
    name = env_name(name)
    value = os.environ.get(name) or load_env().get(name) or ""
    if not value and not allow_no_key:
        raise ManagerError(f"secret {name} is not configured")
    return value


def atomic_write(path: Path, content: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    current_mode = mode
    if current_mode is None and path.exists():
        current_mode = path.stat().st_mode & 0o777
    current_mode = current_mode or 0o600
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, current_mode)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def json_request(url: str, payload: dict | None, key: str, timeout: int) -> tuple[dict, int]:
    headers = {"Accept": "application/json", "User-Agent": "hermes-model-api-manager/1.0"}
    data = None
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:500]
        raise ManagerError(f"upstream HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ManagerError(f"upstream request failed: {exc}") from exc
    latency = round((time.monotonic() - started) * 1000)
    try:
        return json.loads(raw), latency
    except json.JSONDecodeError as exc:
        raise ManagerError("upstream response was not JSON") from exc


def chat_url(base: str) -> str:
    parsed = urllib.parse.urlparse(base.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ManagerError("base URL must include http(s) scheme and host")
    value = base.rstrip("/")
    return value if value.endswith("/chat/completions") else value + "/chat/completions"


def probe_tavern(base: str, model: str, key: str, timeout: int) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return exactly TAVERN_OK."},
            {"role": "user", "content": "Compatibility check"},
        ],
        "temperature": 0,
        "max_tokens": 24,
        "stream": False,
    }
    body, latency = json_request(chat_url(base), payload, key, timeout)
    choices = body.get("choices") or []
    content = ((choices[0].get("message") or {}).get("content") if choices else None)
    if not isinstance(content, str) or not content.strip():
        raise ManagerError("Tavern probe returned no assistant content")
    return {"compatible": True, "latency_ms": latency, "content": content.strip()[:80]}


def probe_agent(base: str, model: str, key: str, timeout: int) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Call the compatibility_probe tool exactly once."},
            {"role": "user", "content": "Run the tool now."},
        ],
        "tools": [{
            "type": "function",
            "function": {
                "name": "compatibility_probe",
                "description": "Verify tool calling support",
                "parameters": {
                    "type": "object",
                    "properties": {"status": {"type": "string"}},
                    "required": ["status"],
                },
            },
        }],
        "tool_choice": {"type": "function", "function": {"name": "compatibility_probe"}},
        "temperature": 0,
        "max_tokens": 64,
        "stream": False,
    }
    body, latency = json_request(chat_url(base), payload, key, timeout)
    choices = body.get("choices") or []
    message = choices[0].get("message") or {} if choices else {}
    calls = message.get("tool_calls") or []
    if not calls or ((calls[0].get("function") or {}).get("name") != "compatibility_probe"):
        raise ManagerError("agent probe did not return the required tool call")
    return {"compatible": True, "latency_ms": latency, "tool_call": "compatibility_probe"}


def run_probes(target: str, base: str, model: str, key: str, timeout: int) -> dict:
    result = {}
    if target in {"agent", "both"}:
        result["agent"] = probe_agent(base, model, key, timeout)
    if target in {"tavern", "both"}:
        result["tavern"] = probe_tavern(base, model, key, timeout)
    return result


def read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ManagerError(f"{path} must contain a YAML mapping")
    return value


def write_agent_config(name: str, base: str, model: str, key_env: str) -> None:
    provider = slug(name)
    config = read_yaml(HERMES_CONFIG)
    providers = config.setdefault("providers", {})
    if not isinstance(providers, dict):
        raise ManagerError("Hermes providers config is not a mapping")
    existing = providers.get(provider) if isinstance(providers.get(provider), dict) else {}
    models = existing.get("models") if isinstance(existing.get("models"), dict) else {}
    models.setdefault(model, {})
    existing.update({
        "name": name,
        "api": base.rstrip("/"),
        "key_env": env_name(key_env),
        "default_model": model,
        "transport": "chat_completions",
        "models": models,
    })
    existing.pop("api_key", None)
    providers[provider] = existing
    model_config = config.setdefault("model", {})
    if not isinstance(model_config, dict):
        raise ManagerError("Hermes model config is not a mapping")
    model_config.update({"provider": provider, "default": model, "base_url": base.rstrip("/")})
    rendered = yaml.safe_dump(config, allow_unicode=True, sort_keys=False).encode()
    atomic_write(HERMES_CONFIG, rendered)


def tavern_event(payload: dict, timeout: int = 180) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(
        TAVERN_CONSOLE + "/api/event",
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "hermes-model-api-manager/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:500]
        raise ManagerError(f"Tavern HTTP {exc.code}: {body}") from exc
    except Exception as exc:
        raise ManagerError(f"Tavern event failed: {exc}") from exc
    if not isinstance(result, dict) or result.get("ok") is False or result.get("error"):
        raise ManagerError(f"Tavern rejected model configuration: {result.get('error', result)}")
    return result


def inspect_agent() -> dict:
    config = read_yaml(HERMES_CONFIG)
    model = config.get("model") if isinstance(config.get("model"), dict) else {}
    provider_id = str(model.get("provider") or "")
    provider = (config.get("providers") or {}).get(provider_id, {}) if isinstance(config.get("providers"), dict) else {}
    key_env = provider.get("key_env") if isinstance(provider, dict) else None
    inline_key_set = bool(provider.get("api_key")) if isinstance(provider, dict) else False
    return {
        "provider": provider_id,
        "model": model.get("default"),
        "base": model.get("base_url") or (provider.get("api") if isinstance(provider, dict) else None),
        "key_env": key_env,
        "key_set": inline_key_set or bool(key_env and key_from_env(key_env, allow_no_key=True)),
    }


def inspect_tavern() -> dict:
    if not TAVERN_CLI.exists():
        raise ManagerError(f"Tavern CLI not found: {TAVERN_CLI}")
    proc = subprocess.run(
        [sys.executable, str(TAVERN_CLI), "model", "list", "--json"],
        text=True, capture_output=True, timeout=30,
    )
    if proc.returncode:
        raise ManagerError(proc.stderr.strip() or proc.stdout.strip() or "Tavern model list failed")
    return json.loads(proc.stdout)


def file_snapshot(path: Path) -> tuple[bool, bytes, int]:
    if not path.exists():
        return False, b"", 0o600
    return True, path.read_bytes(), path.stat().st_mode & 0o777


def restore_snapshot(path: Path, snapshot: tuple[bool, bytes, int]) -> None:
    existed, content, mode = snapshot
    if existed:
        atomic_write(path, content, mode)
    elif path.exists():
        path.unlink()


def validate_agent_config() -> None:
    proc = subprocess.run(["hermes", "config", "check"], text=True, capture_output=True, timeout=60)
    if proc.returncode:
        raise ManagerError(proc.stderr.strip() or proc.stdout.strip() or "Hermes config check failed")


def apply(args) -> None:
    key = key_from_env(args.key_env, allow_no_key=args.allow_no_key)
    probes = run_probes(args.target, args.base, args.model, key, args.timeout)
    snapshots = {
        HERMES_CONFIG: file_snapshot(HERMES_CONFIG),
        TAVERN_MODELS: file_snapshot(TAVERN_MODELS),
    }
    changed = []
    try:
        if args.target in {"agent", "both"}:
            write_agent_config(args.name, args.base, args.model, args.key_env)
            validate_agent_config()
            changed.append("agent")
        if args.target in {"tavern", "both"}:
            result = tavern_event({
                "type": "model_add",
                "name": args.name,
                "base": args.base.rstrip("/"),
                "model": args.model,
                "key": key,
            }, timeout=max(args.timeout, 150))
            tavern_event({"type": "model_test", "id": (result.get("config") or {}).get("id") or args.name})
            changed.append("tavern")
    except Exception:
        for path, snapshot in snapshots.items():
            restore_snapshot(path, snapshot)
        raise
    emit(
        "apply",
        target=args.target,
        provider=args.name,
        model=args.model,
        base=args.base.rstrip("/"),
        key=mask_key(key),
        probes=probes,
        changed=changed,
        gateway_restart_required=args.target in {"agent", "both"},
    )


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inspect", help="show sanitized current model configuration")
    p.add_argument("--target", choices=("agent", "tavern", "both"), required=True)

    p = sub.add_parser("store-key", help="read a secret from prompt/stdin and store it in Hermes .env")
    p.add_argument("--env", required=True, help="environment variable name")

    for command in ("probe", "apply"):
        p = sub.add_parser(command, help=f"{command} an OpenAI-compatible model API")
        p.add_argument("--target", choices=("agent", "tavern", "both"), required=True)
        p.add_argument("--base", required=True)
        p.add_argument("--model", required=True)
        p.add_argument("--key-env", required=True)
        p.add_argument("--allow-no-key", action="store_true", help="allow a local endpoint without auth")
        p.add_argument("--timeout", type=int, default=45)
        if command == "apply":
            p.add_argument("--name", required=True)
            p.add_argument("--confirm", action="store_true", required=True)
    return ap


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "inspect":
            data = {}
            if args.target in {"agent", "both"}:
                data["agent"] = inspect_agent()
            if args.target in {"tavern", "both"}:
                data["tavern"] = inspect_tavern()
            emit("inspect", target=args.target, **data)
        elif args.command == "store-key":
            secret = getpass.getpass("API key: ") if sys.stdin.isatty() else sys.stdin.readline().rstrip("\n")
            store_env_secret(args.env, secret)
            emit("store-key", env=env_name(args.env), key=mask_key(secret))
        elif args.command == "probe":
            key = key_from_env(args.key_env, allow_no_key=args.allow_no_key)
            emit(
                "probe", target=args.target, provider_model=args.model,
                key=mask_key(key), results=run_probes(args.target, args.base, args.model, key, args.timeout),
            )
        elif args.command == "apply":
            apply(args)
    except (ManagerError, OSError, ValueError, subprocess.SubprocessError) as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
