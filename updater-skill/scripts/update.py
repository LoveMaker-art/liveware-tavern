#!/usr/bin/env python3
"""Reviewable, merge-aware, state-preserving Tavern release updater."""

import argparse
import fnmatch
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
import uuid

REPO = os.environ.get("TAVERN_UPDATE_REPO", "LoveMaker-art/liveware-tavern")
API = os.environ.get("TAVERN_UPDATE_API", f"https://api.github.com/repos/{REPO}/releases/latest")
DATA = Path(os.environ.get("TAVERN_DATA_ROOT", "/opt/data"))
PYTHON = os.environ.get("TAVERN_PYTHON", "/opt/hermes/.venv/bin/python")
HEALTH_URL = os.environ.get("TAVERN_HEALTH_URL", "http://127.0.0.1:8799/api/health")
SKIP_SERVICE = os.environ.get("TAVERN_SKIP_SERVICE") == "1"
TARGETS = {
    "runtime": DATA / "apps/tavern-runtime",
    "skill": DATA / "skills/creative/tavern",
    "updater": DATA / "skills/system/tavern-updater",
}
UPDATE_ROOT = DATA / "tavern-updates"
BACKUPS = UPDATE_ROOT / "backups"
PLANS = UPDATE_ROOT / "plans"
BASELINE = UPDATE_ROOT / "baseline"
STATE = UPDATE_ROOT / "state.json"
ASSET_MANIFEST = "manifest.json"
ASSET_ARCHIVE = "tavern-release.tar.gz"
VERSION_RE = re.compile(r"^version:\s*['\"]?([^'\"\s]+)", re.MULTILINE)
IGNORED = ("__pycache__", "*.pyc", "*.log", "*.bak*", "*.before-*", ".DS_Store")
PROTECTED = (".env", ".env.*", "*.db", "*.sqlite", "*.sqlite3", "sessions", "credentials", "backups")


def version_key(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(value or ""))
    if not match:
        raise RuntimeError(f"unsupported semantic version: {value}")
    return tuple(int(part) for part in match.groups())


def request_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "tavern-updater/2"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def download(url, destination):
    req = urllib.request.Request(url, headers={"Accept": "application/octet-stream", "User-Agent": "tavern-updater/2"})
    with urllib.request.urlopen(req, timeout=120) as response, open(destination, "wb") as output:
        shutil.copyfileobj(response, output)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_version():
    try:
        match = VERSION_RE.search((TARGETS["skill"] / "SKILL.md").read_text(encoding="utf-8"))
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
    if manifest.get("schema") not in (1, 2) or manifest.get("archive") != ASSET_ARCHIVE:
        raise RuntimeError("unsupported release manifest")
    version = str(manifest.get("version") or "")
    if release.get("tag") != "v" + version:
        raise RuntimeError("release tag and manifest version do not match")
    digest = sha256_file(archive_path)
    if digest != manifest.get("sha256"):
        raise RuntimeError("release archive SHA256 mismatch")
    return release, manifest, archive_path


def safe_extract(archive, destination, manifest):
    destination = destination.resolve()
    allowed_areas = {"runtime", "skill", "updater"}
    with tarfile.open(archive, "r:gz") as package:
        for member in package.getmembers():
            parts = Path(member.name).parts
            if not parts or parts[0] not in allowed_areas:
                raise RuntimeError("release archive contains an unmanaged top-level path")
            target = (destination / member.name).resolve()
            if destination not in target.parents and target != destination:
                raise RuntimeError("release archive contains an unsafe path")
            if member.issym() or member.islnk() or member.isdev():
                raise RuntimeError("release archive contains an unsupported link or device")
        package.extractall(destination)
    required = (destination / "runtime/server.py", destination / "runtime/actor.py", destination / "skill/SKILL.md")
    for path in required:
        if not path.is_file():
            raise RuntimeError(f"release archive is missing {path.relative_to(destination)}")
    if manifest.get("schema") == 2:
        expected = manifest.get("files") or {}
        actual = tree_hashes(destination)
        if actual != expected:
            raise RuntimeError("release file manifest mismatch")


def ignored(path):
    return any(fnmatch.fnmatch(part, pattern) for part in path.parts for pattern in IGNORED)


def protected(path):
    return any(fnmatch.fnmatch(part, pattern) for part in path.parts for pattern in PROTECTED)


def tree_files(root):
    if not root.is_dir():
        return {}
    return {path.relative_to(root).as_posix(): path for path in root.rglob("*") if path.is_file() and not ignored(path.relative_to(root))}


def tree_hashes(root):
    return {name: sha256_file(path) for name, path in sorted(tree_files(root).items())}


def installation_fingerprint():
    payload = {area: tree_hashes(path) for area, path in TARGETS.items()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def category(area, name):
    if area == "skill":
        return "skill"
    if area == "updater":
        return "updater"
    suffix = Path(name).suffix.lower()
    if name.startswith("web/") or suffix in (".html", ".css", ".js"):
        return "frontend"
    return "backend"


def binary(path):
    try:
        return b"\0" in path.read_bytes()[:8192]
    except OSError:
        return False


def copy_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def merge_file(base, current, incoming, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "merge-file", "-p", str(current), str(base), str(incoming)],
        text=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode == 0:
        output.write_bytes(result.stdout)
        return True
    return False


def merge_area(area, base_root, current_root, incoming_root, output_root):
    base = tree_files(base_root)
    current = tree_files(current_root)
    incoming = tree_files(incoming_root)
    report = []
    conflicts = []
    for name in sorted(set(base) | set(current) | set(incoming)):
        b, c, n = base.get(name), current.get(name), incoming.get(name)
        bh = sha256_file(b) if b else None
        ch = sha256_file(c) if c else None
        nh = sha256_file(n) if n else None
        status = "unchanged"
        source = None
        if ch == nh:
            source = c
        elif ch == bh:
            source, status = n, "upstream"
        elif nh == bh:
            source, status = c, "local"
        elif not b and c and not n:
            source, status = c, "local-added"
        elif not b and n and not c:
            source, status = n, "upstream-added"
        elif b and not c and nh == bh:
            status = "local-deleted"
        elif b and not n and ch == bh:
            status = "upstream-deleted"
        elif b and c and n and not any(binary(path) for path in (b, c, n)):
            if merge_file(b, c, n, output_root / name):
                status = "merged"
            else:
                status = "conflict"
        else:
            status = "conflict"
        if status == "conflict":
            conflicts.append(f"{area}/{name}")
        elif status != "merged" and source:
            copy_file(source, output_root / name)
        report.append({"path": f"{area}/{name}", "category": category(area, name), "status": status})
    # Preserve credentials and local state that are deliberately outside release control.
    for name, path in tree_files(current_root).items():
        rel = Path(name)
        if protected(rel):
            copy_file(path, output_root / rel)
    return report, conflicts


def run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, **kwargs)


def health():
    if SKIP_SERVICE:
        return True, {"ok": True, "skipped": True}
    try:
        data = request_json(HEALTH_URL)
        return bool(data.get("ok") and data.get("key_set")), data
    except Exception as exc:
        return False, {"error": str(exc)}


def copy_tree(source, destination):
    if source.is_dir():
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*IGNORED))
    else:
        destination.mkdir(parents=True, exist_ok=True)


def backup_current(version):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = BACKUPS / f"{version}-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    for area, target in TARGETS.items():
        copy_tree(target, backup / area)
    if BASELINE.is_dir():
        copy_tree(BASELINE, backup / "baseline")
    return backup


def replace_tree(source, target):
    pending = target.parent / ("." + target.name + ".next")
    old = target.parent / ("." + target.name + ".old")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(pending, ignore_errors=True)
    shutil.rmtree(old, ignore_errors=True)
    shutil.copytree(source, pending)
    if target.exists():
        target.rename(old)
    pending.rename(target)
    shutil.rmtree(old, ignore_errors=True)


def stop_server():
    if SKIP_SERVICE:
        return
    subprocess.run(["pkill", "-f", "server.py --port 8799"], check=False)
    time.sleep(1)


def start_server():
    if not SKIP_SERVICE:
        run(["sh", str(TARGETS["skill"] / "scripts/bringup.sh")])


def restore(backup):
    stop_server()
    for area, target in TARGETS.items():
        if (backup / area).is_dir():
            replace_tree(backup / area, target)
    if (backup / "baseline").is_dir():
        replace_tree(backup / "baseline", BASELINE)
    start_server()


def seed_baseline():
    seeded = False
    for area, target in TARGETS.items():
        baseline = BASELINE / area
        if not baseline.exists():
            baseline.parent.mkdir(parents=True, exist_ok=True)
            copy_tree(target, baseline)
            seeded = True
    return seeded


def write_baseline(staged):
    pending = UPDATE_ROOT / ".baseline.next"
    shutil.rmtree(pending, ignore_errors=True)
    pending.mkdir(parents=True)
    for area in TARGETS:
        copy_tree(staged / area, pending / area)
    old = UPDATE_ROOT / ".baseline.old"
    shutil.rmtree(old, ignore_errors=True)
    if BASELINE.exists():
        BASELINE.rename(old)
    pending.rename(BASELINE)
    shutil.rmtree(old, ignore_errors=True)


def command_check(_args):
    with tempfile.TemporaryDirectory(prefix="tavern-update-check-") as temp:
        release, manifest, _archive = release_material(Path(temp))
    print(json.dumps({"installed": local_version(), "latest": manifest["version"], "release": release["url"]}, ensure_ascii=False))


def command_review(_args):
    UPDATE_ROOT.mkdir(parents=True, exist_ok=True)
    PLANS.mkdir(parents=True, exist_ok=True)
    baseline_seeded = seed_baseline()
    installed = local_version()
    with tempfile.TemporaryDirectory(prefix="tavern-update-review-") as temp:
        work = Path(temp)
        release, manifest, archive = release_material(work)
        if version_key(manifest["version"]) < version_key(installed):
            raise RuntimeError("latest release is older than the installed version")
        unpacked = work / "unpacked"
        unpacked.mkdir()
        safe_extract(archive, unpacked, manifest)
        run([PYTHON, "-m", "py_compile", str(unpacked / "runtime/server.py"), str(unpacked / "runtime/actor.py")])
        plan_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        plan_dir = PLANS / plan_id
        staged = plan_dir / "staged"
        staged.mkdir(parents=True)
        files, conflicts = [], []
        for area, target in TARGETS.items():
            incoming = unpacked / area
            if not incoming.is_dir():
                copy_tree(target, incoming)
            area_files, area_conflicts = merge_area(area, BASELINE / area, target, incoming, staged / area)
            files.extend(area_files)
            conflicts.extend(area_conflicts)
        counts = {}
        categories = {}
        for item in files:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
            if item["status"] != "unchanged":
                categories[item["category"]] = categories.get(item["category"], 0) + 1
        plan = {
            "schema": 1,
            "plan_id": plan_id,
            "installed": installed,
            "target": manifest["version"],
            "release": release["url"],
            "archive_sha256": manifest["sha256"],
            "created_at": int(time.time()),
            "current_fingerprint": installation_fingerprint(),
            "staged_hashes": {area: tree_hashes(staged / area) for area in TARGETS},
            "baseline_seeded": baseline_seeded,
            "ready": not conflicts,
            "counts": counts,
            "categories": categories,
            "conflicts": conflicts,
            "files": files,
        }
        (plan_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan, ensure_ascii=False))


def load_plan(plan_id):
    plan_path = PLANS / plan_id / "plan.json"
    if not plan_path.is_file():
        raise RuntimeError("review plan does not exist")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    staged = plan_path.parent / "staged"
    if not plan.get("ready"):
        raise RuntimeError("review plan contains merge conflicts")
    if installation_fingerprint() != plan.get("current_fingerprint"):
        raise RuntimeError("installed files changed after review; run review again")
    actual = {area: tree_hashes(staged / area) for area in TARGETS}
    if actual != plan.get("staged_hashes"):
        raise RuntimeError("reviewed staging files changed after review")
    return plan, staged


def command_apply(args):
    if not args.confirm:
        raise RuntimeError("apply requires --confirm")
    if not args.plan:
        raise RuntimeError("apply requires --plan from a successful review")
    BACKUPS.mkdir(parents=True, exist_ok=True)
    plan, staged = load_plan(args.plan)
    installed = local_version()
    backup = backup_current(installed)
    try:
        stop_server()
        replace_tree(staged / "runtime", TARGETS["runtime"])
        replace_tree(staged / "skill", TARGETS["skill"])
        start_server()
        ok, report = health()
        if not ok:
            raise RuntimeError("health check failed: " + json.dumps(report, ensure_ascii=False))
        # Self-update last so a failed application update keeps the known-good updater.
        replace_tree(staged / "updater", TARGETS["updater"])
        write_baseline(staged)
    except Exception:
        restore(backup)
        raise
    state = {"installed": plan["target"], "previous": installed, "backup": str(backup), "release": plan["release"], "plan_id": args.plan, "updated_at": int(time.time())}
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"updated": True, "from": installed, "to": plan["target"], "plan_id": args.plan, "health": report}, ensure_ascii=False))


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
    review = sub.add_parser("review")
    review.set_defaults(func=command_review)
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--plan")
    apply_parser.add_argument("--confirm", action="store_true")
    apply_parser.set_defaults(func=command_apply)
    rollback = sub.add_parser("rollback")
    rollback.add_argument("--confirm", action="store_true")
    rollback.set_defaults(func=command_rollback)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
