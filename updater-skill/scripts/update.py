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
SKILL_ASSET_MANIFEST = "skill-manifest.json"
SKILL_ASSET_ARCHIVE = "tavern-skill.tar.gz"
VERSION_RE = re.compile(r"^version:\s*['\"]?([^'\"\s]+)", re.MULTILINE)
IGNORED = ("__pycache__", "*.pyc", "*.log", "*.bak*", "*.before-*", ".DS_Store")
PROTECTED = (".env", ".env.*", "*.db", "*.sqlite", "*.sqlite3", "sessions", "credentials", "backups")
ALLOWED_MANAGED = {
    "runtime": {
        ".tavern-release-version",
        "actor.py",
        "actor_self.md",
        "card_import.py",
        "server.py",
        "web/actor.html",
        "web/actor.js",
        "web/app.js",
        "web/bridge.js",
        "web/console.css",
        "web/i18n.js",
        "web/index.html",
    },
    "updater": {
        "SKILL.md",
        "agents/openai.yaml",
        "references/release-format.md",
        "scripts/update.py",
    },
    "skill": {
        "SKILL.md",
        "references/actor-memory.md",
        "references/card-authoring.md",
        "references/card-localization.md",
        "references/card-workflow.md",
        "references/content-modeling.md",
        "references/diagnostics.md",
        "references/event-driven-update.md",
        "references/i18n.md",
        "references/liveware-ops.md",
        "references/lore-audit.md",
        "references/model-config.md",
        "references/recommendation-planning.md",
        "references/world-expansion.md",
        "references/world-rebuild.md",
        "references/worldbook-authoring.md",
        "scripts/bringup.sh",
        "scripts/install.sh",
        "scripts/make_test_card.py",
        "scripts/provision.sh",
        "scripts/smoke.py",
        "scripts/tavern_cli.py",
    },
}


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
    marker = TARGETS["runtime"] / ".tavern-release-version"
    try:
        value = marker.read_text(encoding="utf-8").strip()
        if value:
            return value
    except OSError:
        pass
    try:
        match = VERSION_RE.search((DATA / "skills/creative/tavern/SKILL.md").read_text(encoding="utf-8"))
        return match.group(1) if match else "0.0.0"
    except OSError:
        return "0.0.0"


def local_skill_version():
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
    required = (ASSET_MANIFEST, ASSET_ARCHIVE, SKILL_ASSET_MANIFEST, SKILL_ASSET_ARCHIVE)
    missing = [name for name in required if not assets.get(name)]
    if missing:
        raise RuntimeError("release is missing required assets: " + ", ".join(missing))
    return {"tag": release.get("tag_name"), "assets": assets, "url": release.get("html_url")}


def release_material(work):
    release = latest_release()
    manifest_path = work / ASSET_MANIFEST
    archive_path = work / ASSET_ARCHIVE
    skill_manifest_path = work / SKILL_ASSET_MANIFEST
    skill_archive_path = work / SKILL_ASSET_ARCHIVE
    download(release["assets"][ASSET_MANIFEST], manifest_path)
    download(release["assets"][ASSET_ARCHIVE], archive_path)
    download(release["assets"][SKILL_ASSET_MANIFEST], skill_manifest_path)
    download(release["assets"][SKILL_ASSET_ARCHIVE], skill_archive_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    skill_manifest = json.loads(skill_manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("schema") != 4 or manifest.get("scope") != "tavern-system"
            or manifest.get("archive") != ASSET_ARCHIVE):
        raise RuntimeError("unsupported release manifest")
    version = str(manifest.get("version") or "")
    if release.get("tag") != "v" + version:
        raise RuntimeError("release tag and manifest version do not match")
    digest = sha256_file(archive_path)
    if digest != manifest.get("sha256"):
        raise RuntimeError("release archive SHA256 mismatch")
    managed = manifest.get("managed_files") or []
    for path in managed:
        area, separator, name = str(path).partition("/")
        if not separator or name not in ALLOWED_MANAGED.get(area, set()):
            raise RuntimeError(f"release attempts to manage a forbidden path: {path}")
    required_runtime = {
        "runtime/.tavern-release-version",
        "runtime/actor.py",
        "runtime/actor_self.md",
        "runtime/server.py",
        "runtime/web/actor.html",
        "runtime/web/actor.js",
        "runtime/web/app.js",
        "runtime/web/bridge.js",
        "runtime/web/console.css",
        "runtime/web/i18n.js",
        "runtime/web/index.html",
    }
    if not required_runtime.issubset(set(managed)):
        raise RuntimeError("release is missing required Tavern system files")
    if (skill_manifest.get("schema") != 1 or skill_manifest.get("scope") != "tavern-creative-skill"
            or skill_manifest.get("archive") != SKILL_ASSET_ARCHIVE):
        raise RuntimeError("unsupported Tavern skill manifest")
    if str(skill_manifest.get("version") or "") != version:
        raise RuntimeError("runtime and Tavern skill release versions do not match")
    if sha256_file(skill_archive_path) != skill_manifest.get("sha256"):
        raise RuntimeError("Tavern skill archive SHA256 mismatch")
    skill_managed = skill_manifest.get("managed_files") or []
    for path in skill_managed:
        area, separator, name = str(path).partition("/")
        if area != "skill" or not separator or name not in ALLOWED_MANAGED["skill"]:
            raise RuntimeError(f"Tavern skill release attempts to manage a forbidden path: {path}")
    if "skill/SKILL.md" not in skill_managed:
        raise RuntimeError("Tavern skill release is missing SKILL.md")
    return release, manifest, archive_path, skill_manifest, skill_archive_path


def safe_extract(archive, destination, manifest):
    destination = destination.resolve()
    allowed_areas = {"runtime", "updater"}
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
    required = (destination / "runtime/server.py", destination / "runtime/actor.py",
                destination / "runtime/actor_self.md",
                destination / "runtime/.tavern-release-version", destination / "updater/SKILL.md")
    for path in required:
        if not path.is_file():
            raise RuntimeError(f"release archive is missing {path.relative_to(destination)}")
    expected = manifest.get("files") or {}
    managed = manifest.get("managed_files") or []
    actual = tree_hashes(destination)
    if actual != expected or sorted(expected) != sorted(managed):
        raise RuntimeError("release file manifest mismatch")


def safe_extract_skill(archive, destination, manifest):
    destination = destination.resolve()
    with tarfile.open(archive, "r:gz") as package:
        for member in package.getmembers():
            parts = Path(member.name).parts
            if not parts or parts[0] != "skill":
                raise RuntimeError("Tavern skill archive contains an unmanaged top-level path")
            target = (destination / member.name).resolve()
            if destination not in target.parents and target != destination:
                raise RuntimeError("Tavern skill archive contains an unsafe path")
            if member.issym() or member.islnk() or member.isdev():
                raise RuntimeError("Tavern skill archive contains an unsupported link or device")
        package.extractall(destination)
    expected = manifest.get("files") or {}
    managed = manifest.get("managed_files") or []
    actual = {f"skill/{name}": digest for name, digest in tree_hashes(destination / "skill").items()}
    if actual != expected or sorted(expected) != sorted(managed):
        raise RuntimeError("Tavern skill file manifest mismatch")


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


def split_managed(managed_files):
    grouped = {area: set() for area in TARGETS}
    for path in managed_files:
        area, separator, name = str(path).partition("/")
        if not separator or name not in ALLOWED_MANAGED.get(area, set()):
            raise RuntimeError(f"release manages an unsupported path: {path}")
        grouped[area].add(name)
    return grouped


def managed_fingerprint(managed_files):
    payload = {}
    for area, names in split_managed(managed_files).items():
        for name in sorted(names):
            path = TARGETS[area] / name
            payload[f"{area}/{name}"] = sha256_file(path) if path.is_file() else None
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


def merge_area(area, base_root, current_root, incoming_root, output_root, managed_names):
    base = tree_files(base_root)
    current = tree_files(current_root)
    incoming = tree_files(incoming_root)
    report = []
    conflicts = []
    for name in sorted(managed_names):
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
        elif not b and n and not c:
            source, status = n, "upstream-added"
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
        report.append({
            "path": f"{area}/{name}",
            "category": category(area, name),
            "status": status,
            "base_sha256": bh,
            "installed_sha256": ch,
            "release_sha256": nh,
        })
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


def copy_managed(source_root, destination_root, managed_files, areas=None):
    grouped = split_managed(managed_files)
    for area, names in grouped.items():
        if areas is not None and area not in areas:
            continue
        for name in sorted(names):
            source = source_root / area / name
            if source.is_file():
                copy_file(source, destination_root / area / name)


def install_managed(source_root, managed_files, areas=None):
    grouped = split_managed(managed_files)
    for area, names in grouped.items():
        if areas is not None and area not in areas:
            continue
        for name in sorted(names):
            source = source_root / area / name
            if not source.is_file():
                raise RuntimeError(f"staged managed file is missing: {area}/{name}")
            target = TARGETS[area] / name
            target.parent.mkdir(parents=True, exist_ok=True)
            pending = target.parent / ("." + target.name + ".next-" + uuid.uuid4().hex[:8])
            try:
                shutil.copy2(source, pending)
                os.replace(pending, target)
            finally:
                try:
                    pending.unlink()
                except OSError:
                    pass


def backup_current(version, managed_files):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = BACKUPS / f"{version}-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    missing = []
    baseline_missing = []
    for area, names in split_managed(managed_files).items():
        for name in sorted(names):
            current = TARGETS[area] / name
            if current.is_file():
                copy_file(current, backup / "installed" / area / name)
            else:
                missing.append(f"{area}/{name}")
            baseline = BASELINE / area / name
            if baseline.is_file():
                copy_file(baseline, backup / "baseline" / area / name)
            else:
                baseline_missing.append(f"{area}/{name}")
    metadata = {
        "managed_files": sorted(managed_files),
        "missing": missing,
        "baseline_missing": baseline_missing,
    }
    (backup / "backup.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return backup


def stop_server():
    if SKIP_SERVICE:
        return
    subprocess.run(["pkill", "-f", "server.py --port 8799"], check=False)
    time.sleep(1)


def start_server():
    if not SKIP_SERVICE:
        run(["sh", str(DATA / "skills/creative/tavern/scripts/bringup.sh")])


def restore(backup):
    metadata_path = backup / "backup.json"
    if not metadata_path.is_file():
        raise RuntimeError("rollback backup metadata is missing")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    managed_files = metadata.get("managed_files") or []
    missing = set(metadata.get("missing") or [])
    stop_server()
    for area, names in split_managed(managed_files).items():
        for name in sorted(names):
            key = f"{area}/{name}"
            target = TARGETS[area] / name
            if key in missing:
                try:
                    target.unlink()
                except OSError:
                    pass
            else:
                copy_file(backup / "installed" / area / name, target)
    shutil.rmtree(BASELINE, ignore_errors=True)
    copy_managed(backup / "baseline", BASELINE, managed_files)
    start_server()


def seed_baseline(managed_files):
    seeded = False
    for area, names in split_managed(managed_files).items():
        for name in sorted(names):
            baseline = BASELINE / area / name
            current = TARGETS[area] / name
            if not baseline.exists() and current.is_file():
                copy_file(current, baseline)
                seeded = True
    return seeded


def write_baseline(staged, managed_files):
    pending = UPDATE_ROOT / ".baseline.next"
    shutil.rmtree(pending, ignore_errors=True)
    pending.mkdir(parents=True)
    copy_managed(staged, pending, managed_files)
    old = UPDATE_ROOT / ".baseline.old"
    shutil.rmtree(old, ignore_errors=True)
    if BASELINE.exists():
        BASELINE.rename(old)
    pending.rename(BASELINE)
    shutil.rmtree(old, ignore_errors=True)


def command_check(_args):
    with tempfile.TemporaryDirectory(prefix="tavern-update-check-") as temp:
        release, manifest, _archive, skill_manifest, _skill_archive = release_material(Path(temp))
    print(json.dumps({
        "installed": local_version(),
        "latest": manifest["version"],
        "skill_installed": local_skill_version(),
        "skill_latest": skill_manifest["version"],
        "release": release["url"],
    }, ensure_ascii=False))


def command_review(_args):
    UPDATE_ROOT.mkdir(parents=True, exist_ok=True)
    PLANS.mkdir(parents=True, exist_ok=True)
    installed = local_version()
    with tempfile.TemporaryDirectory(prefix="tavern-update-review-") as temp:
        work = Path(temp)
        release, manifest, archive, skill_manifest, skill_archive = release_material(work)
        managed_files = sorted(set(manifest["managed_files"] + skill_manifest["managed_files"]))
        baseline_seeded = seed_baseline(managed_files)
        if version_key(manifest["version"]) < version_key(installed):
            raise RuntimeError("latest release is older than the installed version")
        unpacked = work / "unpacked"
        unpacked.mkdir()
        safe_extract(archive, unpacked, manifest)
        safe_extract_skill(skill_archive, unpacked, skill_manifest)
        run([PYTHON, "-m", "py_compile", str(unpacked / "runtime/server.py"), str(unpacked / "runtime/actor.py")])
        plan_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        plan_dir = PLANS / plan_id
        staged = plan_dir / "staged"
        staged.mkdir(parents=True)
        files, conflicts = [], []
        managed_by_area = split_managed(managed_files)
        for area, target in TARGETS.items():
            incoming = unpacked / area
            area_files, area_conflicts = merge_area(
                area, BASELINE / area, target, incoming, staged / area, managed_by_area[area])
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
            "skill_archive_sha256": skill_manifest["sha256"],
            "created_at": int(time.time()),
            "managed_files": managed_files,
            "current_fingerprint": managed_fingerprint(managed_files),
            "staged_hashes": {area: tree_hashes(staged / area) for area in TARGETS},
            "baseline_seeded": baseline_seeded,
            "reported_at": None,
            "ready": not conflicts,
            "counts": counts,
            "categories": categories,
            "conflicts": conflicts,
            "files": files,
        }
        (plan_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan, ensure_ascii=False))


def command_report(args):
    plan_path = PLANS / args.plan / "plan.json"
    if not plan_path.is_file():
        raise RuntimeError("review plan does not exist")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if managed_fingerprint(plan.get("managed_files") or []) != plan.get("current_fingerprint"):
        raise RuntimeError("installed files changed after review; run review again")
    changes = [item for item in plan.get("files") or [] if item.get("status") != "unchanged"]
    plan["reported_at"] = int(time.time())
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "plan_id": plan["plan_id"],
        "installed": plan["installed"],
        "target": plan["target"],
        "scope": "tavern-system",
        "ready": plan["ready"],
        "baseline_seeded": plan["baseline_seeded"],
        "counts": plan["counts"],
        "categories": plan["categories"],
        "conflicts": plan["conflicts"],
        "changes": changes,
        "excluded": [
            "runtime/web files outside the seven official managed code files",
            "runtime/assets",
            "runtime identity/persona files other than the neutral actor_self.md seed template",
            "starter and fixture content",
            "creative Tavern skill identity files, assets, fixtures, and every file outside the explicit allowlist",
            "/opt/data/tavern-state",
            "credentials and model keys",
        ],
        "next_step": "Report once and wait for approval to apply the complete runtime plus Tavern skill update. Never ask separately whether the Tavern skill should be synchronized.",
    }
    print(json.dumps(report, ensure_ascii=False))


def load_plan(plan_id):
    plan_path = PLANS / plan_id / "plan.json"
    if not plan_path.is_file():
        raise RuntimeError("review plan does not exist")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    staged = plan_path.parent / "staged"
    if not plan.get("ready"):
        raise RuntimeError("review plan contains merge conflicts")
    if not plan.get("reported_at"):
        raise RuntimeError("review plan has not been reported; run report and show it to the user first")
    managed_files = plan.get("managed_files") or []
    if managed_fingerprint(managed_files) != plan.get("current_fingerprint"):
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
    managed_files = plan.get("managed_files") or []
    installed = local_version()
    backup = backup_current(installed, managed_files)
    try:
        stop_server()
        install_managed(staged, managed_files, areas={"runtime", "skill"})
        start_server()
        ok, report = health()
        if not ok:
            raise RuntimeError("health check failed: " + json.dumps(report, ensure_ascii=False))
        # Self-update last so a failed application update keeps the known-good updater.
        install_managed(staged, managed_files, areas={"updater"})
        write_baseline(staged, managed_files)
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
    if not (backup / "backup.json").is_file():
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
    report = sub.add_parser("report")
    report.add_argument("--plan", required=True)
    report.set_defaults(func=command_report)
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
