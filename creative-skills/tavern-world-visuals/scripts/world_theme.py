#!/usr/bin/env python3
"""Inspect, validate, apply, and clear declarative Tavern world themes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


DEFAULT_BASE = os.environ.get("TAVERN_LOCAL_URL", "http://127.0.0.1:8799").rstrip("/")
STATE_DIR = Path(os.environ.get("TAVERN_STATE_DIR", "/opt/data/tavern-state"))
WORLD_ASSET_ROOT = STATE_DIR / "world-assets"
MAX_IMAGE_BYTES = max(1024, int(os.environ.get("TAVERN_WORLD_ASSET_MAX_BYTES", str(12 * 1024 * 1024))))
COLOR_FIELDS = {
    "accent", "background", "surface", "text", "secondary_text", "muted",
    "border", "user_message", "overlay",
}
THEME_FIELDS = COLOR_FIELDS | {
    "font", "narration_font", "content_width", "background_position", "background_fit",
    "background_position_mobile", "background_fit_mobile", "reading_surface",
}
FONT_PRESETS = {"default", "literary", "modern", "classic", "typewriter"}
POSITIONS = {
    "center", "top", "bottom", "left", "right",
    "left top", "left bottom", "right top", "right bottom",
}
BACKGROUND_FITS = {"cover", "contain"}
READING_SURFACES = {"plain", "glass", "solid"}
COLOR_RE = re.compile(r"^(?:#[0-9a-fA-F]{3}|#[0-9a-fA-F]{4}|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8})$")


class ThemeError(RuntimeError):
    pass


def request_json(base: str, path: str, payload: dict | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(base + path, data=data, headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
    except HTTPError as error:
        try:
            detail = json.loads(error.read().decode("utf-8")).get("error")
        except Exception:
            detail = str(error)
        raise ThemeError(detail or str(error)) from error
    except (URLError, OSError, json.JSONDecodeError) as error:
        raise ThemeError(f"Tavern API unavailable: {error}") from error
    if result.get("ok") is False:
        raise ThemeError(result.get("error") or "Tavern API rejected the request")
    return result


def world_aliases(world: dict) -> set[str]:
    aliases = {str(world.get("id") or ""), str(world.get("name") or "")}
    for pack in (world.get("i18n") or {}).values():
        if isinstance(pack, dict):
            aliases.add(str(pack.get("name") or ""))
    return {value.strip().casefold() for value in aliases if value.strip()}


def resolve_world(base: str, selector: str | None) -> dict:
    listing = request_json(base, "/api/productions?summary=1")
    worlds = listing.get("productions") or []
    if not worlds:
        raise ThemeError("No Tavern worlds exist")
    if selector:
        key = selector.strip().casefold()
        matches = [world for world in worlds if key in world_aliases(world)]
    else:
        active = str(listing.get("active") or "")
        matches = [world for world in worlds if str(world.get("id")) == active]
    if not matches:
        raise ThemeError(f"World not found: {selector or 'active world'}")
    if len(matches) > 1:
        ids = ", ".join(str(world.get("id")) for world in matches)
        raise ThemeError(f"World name is ambiguous; use an id: {ids}")
    pid = quote(str(matches[0]["id"]), safe="")
    return request_json(base, f"/api/production?production_id={pid}")["production"]


def load_theme(path: str) -> dict:
    try:
        if path == "-":
            value = json.load(sys.stdin)
        else:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ThemeError(f"Cannot read theme JSON: {error}") from error
    if not isinstance(value, dict):
        raise ThemeError("Theme JSON must be an object")
    return value


def normalize_asset(value: object) -> str:
    raw = str(value or "").strip()
    if not raw or len(raw) > 2048:
        raise ThemeError("assets.background must be a non-empty URL under 2048 characters")
    parsed = urlparse(raw)
    if parsed.scheme == "https" and parsed.netloc:
        return raw
    if (
        not parsed.scheme
        and not raw.startswith("//")
        and (raw.startswith("/world-assets/") or raw.startswith("/assets/"))
    ):
        return raw
    raise ThemeError("assets.background must be HTTPS, /world-assets/..., or a legacy /assets/... path")


def image_extension(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    raise ThemeError("Background must be a PNG, JPEG, or WebP image")


def read_image_source(source: str) -> bytes:
    parsed = urlparse(source)
    if parsed.scheme:
        if parsed.scheme != "https" or not parsed.netloc:
            raise ThemeError("Remote background source must use HTTPS")
        request = Request(source, headers={"Accept": "image/*", "User-Agent": "TavernWorldVisuals/1.1"})
        try:
            with urlopen(request, timeout=30) as response:
                length = int(response.headers.get("Content-Length") or 0)
                if length > MAX_IMAGE_BYTES:
                    raise ThemeError(f"Background exceeds {MAX_IMAGE_BYTES} bytes")
                data = response.read(MAX_IMAGE_BYTES + 1)
        except ThemeError:
            raise
        except (HTTPError, URLError, OSError, ValueError) as error:
            raise ThemeError(f"Cannot download background: {error}") from error
    else:
        path = Path(source).expanduser()
        try:
            if not path.is_file():
                raise ThemeError(f"Background file not found: {path}")
            if path.stat().st_size > MAX_IMAGE_BYTES:
                raise ThemeError(f"Background exceeds {MAX_IMAGE_BYTES} bytes")
            data = path.read_bytes()
        except ThemeError:
            raise
        except OSError as error:
            raise ThemeError(f"Cannot read background: {error}") from error
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ThemeError(f"Background must be between 1 and {MAX_IMAGE_BYTES} bytes")
    return data


def import_background(world: dict, source: str) -> dict:
    data = read_image_source(source)
    extension = image_extension(data)
    world_id = re.sub(r"[^A-Za-z0-9_-]+", "-", str(world.get("id") or "world")).strip("-") or "world"
    digest = hashlib.sha256(data).hexdigest()[:20]
    directory = WORLD_ASSET_ROOT / world_id
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{digest}{extension}"
    if not target.exists():
        temporary = directory / f".{target.name}.{os.getpid()}.tmp"
        temporary.write_bytes(data)
        os.replace(temporary, target)
    return {
        "path": str(target),
        "url": f"/world-assets/{quote(world_id, safe='')}/{quote(target.name, safe='')}",
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def probe_asset(base: str, asset: str) -> dict:
    url = base.rstrip("/") + asset if asset.startswith("/") else asset
    headers = {"Accept": "image/*", "User-Agent": "TavernWorldVisuals/1.1"}
    try:
        request = Request(url, headers=headers, method="HEAD")
        with urlopen(request, timeout=15) as response:
            status = response.status
            content_type = response.headers.get_content_type()
    except HTTPError as error:
        if error.code not in {405, 501}:
            raise ThemeError(f"Background is not HTTP-accessible: {error}") from error
        try:
            request = Request(url, headers={**headers, "Range": "bytes=0-0"})
            with urlopen(request, timeout=15) as response:
                status = response.status
                content_type = response.headers.get_content_type()
        except (HTTPError, URLError, OSError) as fallback_error:
            raise ThemeError(f"Background is not HTTP-accessible: {fallback_error}") from fallback_error
    except (URLError, OSError) as error:
        raise ThemeError(f"Background is not HTTP-accessible: {error}") from error
    if status not in {200, 206} or not content_type.startswith("image/"):
        raise ThemeError(f"Background probe returned {status} {content_type}, expected an image")
    return {"url": asset, "status": status, "content_type": content_type}


def normalize_theme(value: dict) -> tuple[dict, list[str]]:
    unknown_root = set(value) - {"version", "theme", "assets"}
    if unknown_root:
        raise ThemeError("Unknown root fields: " + ", ".join(sorted(unknown_root)))
    if value.get("version", 1) != 1:
        raise ThemeError("Only world theme version 1 is supported")

    source_theme = value.get("theme") or {}
    source_assets = value.get("assets") or {}
    if not isinstance(source_theme, dict) or not isinstance(source_assets, dict):
        raise ThemeError("theme and assets must be objects")
    unknown_theme = set(source_theme) - THEME_FIELDS
    unknown_assets = set(source_assets) - {"background", "background_desktop", "background_mobile"}
    if unknown_theme:
        raise ThemeError("Unknown theme fields: " + ", ".join(sorted(unknown_theme)))
    if unknown_assets:
        raise ThemeError("Unknown asset fields: " + ", ".join(sorted(unknown_assets)))

    theme = {}
    for field in COLOR_FIELDS:
        if field not in source_theme:
            continue
        color = str(source_theme[field]).strip()
        if not COLOR_RE.fullmatch(color):
            raise ThemeError(f"{field} must be a 3, 4, 6, or 8 digit hex color")
        theme[field] = color.lower()
    for field in ("font", "narration_font"):
        if field not in source_theme:
            continue
        preset = str(source_theme[field]).strip().lower()
        if preset not in FONT_PRESETS:
            raise ThemeError(f"{field} must be one of: {', '.join(sorted(FONT_PRESETS))}")
        theme[field] = preset
    if "content_width" in source_theme:
        width = source_theme["content_width"]
        if isinstance(width, bool) or not isinstance(width, int) or not 360 <= width <= 760:
            raise ThemeError("content_width must be an integer from 360 to 760")
        theme["content_width"] = width
    if "background_position" in source_theme:
        position = str(source_theme["background_position"]).strip().lower()
        if position not in POSITIONS:
            raise ThemeError("background_position is not supported")
        theme["background_position"] = position
    if "background_fit" in source_theme:
        fit = str(source_theme["background_fit"]).strip().lower()
        if fit not in BACKGROUND_FITS:
            raise ThemeError("background_fit must be cover or contain")
        theme["background_fit"] = fit
    if "background_position_mobile" in source_theme:
        position = str(source_theme["background_position_mobile"]).strip().lower()
        if position not in POSITIONS:
            raise ThemeError("background_position_mobile is not supported")
        theme["background_position_mobile"] = position
    if "background_fit_mobile" in source_theme:
        fit = str(source_theme["background_fit_mobile"]).strip().lower()
        if fit not in BACKGROUND_FITS:
            raise ThemeError("background_fit_mobile must be cover or contain")
        theme["background_fit_mobile"] = fit
    if "reading_surface" in source_theme:
        surface = str(source_theme["reading_surface"]).strip().lower()
        if surface not in READING_SURFACES:
            raise ThemeError("reading_surface must be plain, glass, or solid")
        theme["reading_surface"] = surface

    assets = {}
    for field in ("background", "background_desktop", "background_mobile"):
        if field in source_assets:
            assets[field] = normalize_asset(source_assets[field])
    if not theme and not assets:
        raise ThemeError("Theme contains no supported visual fields; use the clear command to reset")

    normalized = {"version": 1}
    if theme:
        normalized["theme"] = theme
    if assets:
        normalized["assets"] = assets
    warnings = contrast_warnings(normalized)
    return normalized, warnings


def rgb(color: str) -> tuple[float, float, float]:
    value = color[1:]
    if len(value) in {3, 4}:
        value = "".join(ch * 2 for ch in value)
    value = value[:6]
    return tuple(int(value[index:index + 2], 16) / 255 for index in (0, 2, 4))


def luminance(color: str) -> float:
    values = []
    for channel in rgb(color):
        values.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def contrast_warnings(value: dict) -> list[str]:
    theme = value.get("theme") or {}
    warnings = []
    for foreground, background, label in (
        ("text", "background", "story text/background"),
        ("secondary_text", "user_message", "user message text/surface"),
    ):
        if foreground in theme and background in theme:
            ratio = contrast(theme[foreground], theme[background])
            if ratio < 4.5:
                warnings.append(f"Low contrast for {label}: {ratio:.2f}:1 (target 4.5:1)")
    if (value.get("assets") or {}) and "overlay" not in theme:
        warnings.append("A background image is set without an overlay; readability may vary")
    return warnings


def clip(value: object, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


def inspect_view(world: dict) -> dict:
    cast = []
    for card in world.get("cards") or []:
        cue = " | ".join(filter(None, [
            clip(card.get("scenario"), 120),
            clip(card.get("description") or (card.get("profile") or {}).get("summary"), 160),
        ]))
        cast.append({
            "name": card.get("name"),
            "visual_cue": clip(cue, 220),
        })
    lore = []
    remaining_entries = 8
    for book in world.get("worldbooks") or []:
        entries = []
        for entry in (book.get("entries") or [])[:remaining_entries]:
            entries.append({
                "name": entry.get("name") or entry.get("comment"),
                "visual_cue": clip(entry.get("content"), 150),
            })
        remaining_entries -= len(entries)
        lore.append({"name": book.get("name"), "entries": entries})
        if remaining_entries <= 0:
            break
    opening = []
    for message in (world.get("story") or [])[:2]:
        opening.append({"role": message.get("role"), "text": clip(message.get("text"), 300)})
    return {
        "id": world.get("id"),
        "name": world.get("name"),
        "language": world.get("response_language") or world.get("language_mode"),
        "current_ui": world.get("ui") or {},
        "cast": cast,
        "lore": lore,
        "opening": opening,
    }


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Tavern per-world visual theme helper")
    parser.add_argument("--base", default=DEFAULT_BASE, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_parser = sub.add_parser("inspect", help="Show compact world visual context")
    inspect_parser.add_argument("--world")

    validate_parser = sub.add_parser("validate", help="Validate and normalize theme JSON")
    validate_parser.add_argument("--json", required=True)

    import_parser = sub.add_parser("import-background", help="Persist a local file or HTTPS image for one world")
    import_parser.add_argument("--world")
    import_parser.add_argument("--source", required=True)
    import_parser.add_argument("--target", choices=("desktop", "mobile", "both"), default="both")
    import_parser.add_argument("--apply", action="store_true", help="Set the imported image as the current background")
    import_parser.add_argument("--confirm", action="store_true")

    apply_parser = sub.add_parser("apply", help="Apply a validated theme")
    apply_parser.add_argument("--world")
    apply_parser.add_argument("--json", required=True)
    apply_parser.add_argument("--confirm", action="store_true")

    clear_parser = sub.add_parser("clear", help="Restore the standard theme")
    clear_parser.add_argument("--world")
    clear_parser.add_argument("--confirm", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "validate":
            normalized, warnings = normalize_theme(load_theme(args.json))
            probes = {
                field: probe_asset(args.base.rstrip("/"), asset)
                for field, asset in (normalized.get("assets") or {}).items()
            }
            print_json({"valid": True, "normalized": normalized, "asset_probes": probes, "warnings": warnings})
            return 0

        world = resolve_world(args.base.rstrip("/"), args.world)
        if args.command == "inspect":
            print_json(inspect_view(world))
            return 0
        if not args.confirm:
            raise ThemeError("State change requires --confirm")

        if args.command == "import-background":
            imported = import_background(world, args.source)
            imported["probe"] = probe_asset(args.base.rstrip("/"), imported["url"])
            output = {
                "ok": True,
                "world": {"id": world.get("id"), "name": world.get("name")},
                "background": imported,
            }
            if args.apply:
                current_ui = json.loads(json.dumps(world.get("ui") or {"version": 1}))
                current_assets = current_ui.setdefault("assets", {})
                if args.target == "both":
                    current_assets.pop("background", None)
                    current_assets["background_desktop"] = imported["url"]
                    current_assets["background_mobile"] = imported["url"]
                else:
                    current_assets[f"background_{args.target}"] = imported["url"]
                normalized, warnings = normalize_theme(current_ui)
                result = request_json(args.base.rstrip("/"), "/api/event", {
                    "type": "update_world_ui",
                    "production_id": world["id"],
                    "ui": normalized,
                })
                saved = (result.get("production") or {}).get("ui") or {}
                if saved != normalized:
                    raise ThemeError("Runtime verification failed after importing background")
                output["ui"] = saved
                output["warnings"] = warnings
            print_json(output)
            return 0

        if args.command == "clear":
            theme = {}
            warnings = []
        else:
            theme, warnings = normalize_theme(load_theme(args.json))
            for background in (theme.get("assets") or {}).values():
                probe_asset(args.base.rstrip("/"), background)
        result = request_json(args.base.rstrip("/"), "/api/event", {
            "type": "update_world_ui",
            "production_id": world["id"],
            "ui": theme,
        })
        saved = (result.get("production") or {}).get("ui") or {}
        if saved != theme:
            raise ThemeError("Runtime verification failed: saved theme differs from validated theme")
        print_json({
            "ok": True,
            "world": {"id": world.get("id"), "name": world.get("name")},
            "ui": saved,
            "warnings": warnings,
        })
        return 0
    except ThemeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
