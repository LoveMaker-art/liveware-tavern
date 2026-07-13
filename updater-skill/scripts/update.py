#!/usr/bin/env python3
"""Verified, state-preserving Tavern release updater."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request

REPO = os.environ.get("TAVERN_UPDATE_REPO", "LoveMaker-art/liveware-tavern")
API = os.environ.get("TAVERN_UPDATE_API", f"https://api.github.com/repos/{REPO}/releases/latest")
DATA = Path("/opt/data")
RUNTIME = DATA / "apps/tavern-runtime"
SKILL = DATA / "skills/creative/tavern"
UPDATE_ROOT = DATA / "tavern-updates"
BACKUPS = UPDATE_ROOT / "backups"
STATE = UPDATE_ROOT / "state.json"
ASSET_MANIFEST = "manifest.json"
ASSET_ARCHIVE = "tavern-release.tar.gz"
VERSION_RE = re.compile(r"^version:\s*['\"]?([^'\"\s]+)", re.MULTILINE)


def version_key(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(value or ""))
    if not match:
        raise RuntimeError(f"unsupported semantic version: {value}")
    return tuple(int(part) for part in match.groups())


def request_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "tavern-updater/1"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def download(url, destination):
    req = urllib.request.Request(url, headers={"Accept": "application/octet-stream", "User-Agent": "tavern-updater/1"})
    with urllib.request.urlopen(req, timeout=120) as response, open(destination, "wb") as output:
        shutil.copyfileobj(response, output)


def local_version():
    try:
        match = VERSION_RE.search((SKILL / "SKILL.md").read_text(encoding="utf-8"))
        return match.group(1) if match else "0.0.0"
    except OSError:
        return "0.0.0"


def latest_release():
    release = request_json(API)
    if release.get("draft") or release.get("prerelease"):
        raise RuntimeError("latest GitHub release is not stable")
    assets = {item.get("name"): item.get("browser_download_url") for item in release.get("assets") or []}
    missing = [name for name in (ASSET_MANIFEST, ASSET_ARCHIVE) if not assets.get(name)]
    if missing:
        raise RuntimeError("release is missing required assets: " + ", ".join(missing))
    return {"tag": release.get("tag_name"), "assets": assets, "url": release.get("html_url")}


def release_material(work):
    release = latest_release()
    manifest_path = work / ASSET_MANIFEST
    archive_path = work / ASSET_ARCHIVE
    download(release["assets"][ASSET_MANIFEST], manifest_path)
    download(release["assets"][ASSET_ARCHIVE], archive_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or manifest.get("archive") != ASSET_ARCHIVE:
        raise RuntimeError("unsupported release manifest")
    version = str(manifest.get("version") or "")
    if release.get("tag") != "v" + version:
        raise RuntimeError("release tag and manifest version do not match")
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    if digest != manifest.get("sha256"):
        raise RuntimeError("release archive SHA256 mismatch")
    return release, manifest, archive_path


def safe_extract(archive, destination):
    destination = destination.resolve()
    with tarfile.open(archive, "r:gz") as package:
        for member in package.getmembers():
            target = (destination / member.name).resolve()
            if destination not in target.parents and target != destination:
                raise RuntimeError("release archive contains an unsafe path")
            if member.issym() or member.islnk() or member.isdev():
                raise RuntimeError("release archive contains an unsupported link or device")
        package.extractall(destination)
    for required in (destination / "runtime/server.py", destination / "runtime/actor.py", destination / "skill/SKILL.md"):
        if not required.is_file():
            raise RuntimeError(f"release archive is missing {required.relative_to(destination)}")


def run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, **kwargs)


def health():
    try:
        data = request_json("http://127.0.0.1:8799/api/health")
        return bool(data.get("ok") and data.get("key_set")), data
    except Exception as exc:
        return False, {"error": str(exc)}


def backup_current(version):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = BACKUPS / f"{version}-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copytree(RUNTIME, backup / "runtime", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.log", "backups"))
    shutil.copytree(SKILL, backup / "skill", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.bak*"))
    return backup


def replace_tree(source, target):
    pending = target.parent / ("." + target.name + ".next")
    old = target.parent / ("." + target.name + ".old")
    shutil.rmtree(pending, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)
    shutil.copytree(source, pending)
    if target.exists():
        target.rename(old)
    pending.rename(target)
    shutil.rmtree(old, ignore_errors=True)


def stop_server():
    subprocess.run(["pkill", "-f", "server.py --port 8799"], check=False)
    time.sleep(1)


def start_server():
    run(["sh", str(SKILL / "scripts/bringup.sh")])


def restore(backup):
    stop_server()
    replace_tree(backup / "runtime", RUNTIME)
    replace_tree(backup / "skill", SKILL)
    start_server()


def command_check(_args):
    with tempfile.TemporaryDirectory(prefix="tavern-update-check-") as temp:
        release, manifest, _archive = release_material(Path(temp))
    print(json.dumps({"installed": local_version(), "latest": manifest["version"], "release": release["url"]}, ensure_ascii=False))


def command_apply(args):
    if not args.confirm:
        raise RuntimeError("apply requires --confirm")
    UPDATE_ROOT.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)
    installed = local_version()
    with tempfile.TemporaryDirectory(prefix="tavern-update-") as temp:
        work = Path(temp)
        release, manifest, archive = release_material(work)
        if version_key(manifest["version"]) < version_key(installed):
            raise RuntimeError("latest release is older than the installed version")
        if manifest["version"] == installed:
            print(json.dumps({"updated": False, "installed": installed, "reason": "already current"}, ensure_ascii=False))
            return
        unpacked = work / "unpacked"
        unpacked.mkdir()
        safe_extract(archive, unpacked)
        run(["/opt/hermes/.venv/bin/python", "-m", "py_compile", str(unpacked / "runtime/server.py"), str(unpacked / "runtime/actor.py")])
        backup = backup_current(installed)
        try:
            stop_server()
            replace_tree(unpacked / "runtime", RUNTIME)
            replace_tree(unpacked / "skill", SKILL)
            start_server()
            ok, report = health()
            if not ok:
                raise RuntimeError("health check failed: " + json.dumps(report, ensure_ascii=False))
        except Exception:
            restore(backup)
            raise
    STATE.write_text(json.dumps({"installed": manifest["version"], "previous": installed, "backup": str(backup), "release": release["url"], "updated_at": int(time.time())}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"updated": True, "from": installed, "to": manifest["version"], "health": report}, ensure_ascii=False))


def command_rollback(args):
    if not args.confirm:
        raise RuntimeError("rollback requires --confirm")
    if not STATE.exists():
        raise RuntimeError("no updater state is available for rollback")
    state = json.loads(STATE.read_text(encoding="utf-8"))
    backup = Path(state.get("backup") or "")
    if not (backup / "runtime").is_dir() or not (backup / "skill").is_dir():
        raise RuntimeError("rollback backup is missing")
    current = local_version()
    restore(backup)
    ok, report = health()
    if not ok:
        raise RuntimeError("rollback completed but health check failed: " + json.dumps(report, ensure_ascii=False))
    print(json.dumps({"rolled_back": True, "from": current, "to": local_version(), "health": report}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    check.set_defaults(func=command_check)
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--confirm", action="store_true")
    apply_parser.set_defaults(func=command_apply)
    rollback = sub.add_parser("rollback")
    rollback.add_argument("--confirm", action="store_true")
    rollback.set_defaults(func=command_rollback)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
