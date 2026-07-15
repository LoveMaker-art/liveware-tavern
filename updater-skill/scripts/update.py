#!/usr/bin/env python3
"""Reviewable, merge-aware, state-preserving Tavern release updater."""

import argparse
from contextlib import contextmanager
import fcntl
import fnmatch
from functools import wraps
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
TAG_API = os.environ.get(
    "TAVERN_UPDATE_TAG_API",
    f"https://api.github.com/repos/{REPO}/releases/tags/v{{version}}",
)
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
LOCK = UPDATE_ROOT / "update.lock"
BASELINE_META = ".baseline.json"
ASSET_MANIFEST = "manifest.json"
ASSET_ARCHIVE = "tavern-release.tar.gz"
SKILL_ASSET_MANIFEST = "skill-manifest.json"
SKILL_ASSET_ARCHIVE = "tavern-skill.tar.gz"
VERSION_RE = re.compile(r"^version:\s*['\"]?([^'\"\s]+)", re.MULTILINE)
SKILL_VERSION_LINE_RE = re.compile(r"(?m)^version:[^\r\n]*$")
IGNORED = ("__pycache__", "*.pyc", "*.log", "*.bak*", "*.before-*", ".DS_Store")
PROTECTED = (".env", ".env.*", "*.db", "*.sqlite", "*.sqlite3", "sessions", "credentials", "backups")
OBSOLETE_UPDATER_FILES = ("references/conflict-inspection.md",)
HISTORICAL_SKILL_FILES = {
    "scripts/install.sh",
    "scripts/make_test_card.py",
    "scripts/smoke.py",
}
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
        "scripts/provision.sh",
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


def release_from_api(url):
    release = request_json(url)
    if release.get("draft") or release.get("prerelease"):
        raise RuntimeError("latest GitHub release is not stable")
    assets = {item.get("name"): item.get("browser_download_url") for item in release.get("assets") or []}
    required = (ASSET_MANIFEST, ASSET_ARCHIVE, SKILL_ASSET_MANIFEST, SKILL_ASSET_ARCHIVE)
    missing = [name for name in required if not assets.get(name)]
    if missing:
        raise RuntimeError("release is missing required assets: " + ", ".join(missing))
    return {"tag": release.get("tag_name"), "assets": assets, "url": release.get("html_url")}


def latest_release():
    return release_from_api(API)


def tagged_release(version):
    return release_from_api(TAG_API.format(version=version))


def release_material(work, release=None, historical=False):
    work.mkdir(parents=True, exist_ok=True)
    release = release or latest_release()
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
    allowed_skill = ALLOWED_MANAGED["skill"] | (HISTORICAL_SKILL_FILES if historical else set())
    for path in skill_managed:
        area, separator, name = str(path).partition("/")
        if area != "skill" or not separator or name not in allowed_skill:
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


def atomic_write_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.parent / ("." + path.name + ".next-" + uuid.uuid4().hex[:8])
    try:
        pending.write_text(content, encoding="utf-8")
        os.replace(pending, path)
    finally:
        try:
            pending.unlink()
        except OSError:
            pass


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


def merge_tavern_skill(base, current, incoming, output):
    """Merge SKILL.md after aligning only its release-owned version field."""
    try:
        texts = [path.read_text(encoding="utf-8") for path in (base, current, incoming)]
    except (OSError, UnicodeError):
        return None
    matches = [SKILL_VERSION_LINE_RE.search(text) for text in texts]
    if not all(matches):
        return None
    version_lines = [match.group(0) for match in matches]
    canonical = matches[2].group(0)
    normalized = [SKILL_VERSION_LINE_RE.sub(canonical, text, count=1) for text in texts]
    with tempfile.TemporaryDirectory(prefix="tavern-skill-merge-") as temp:
        root = Path(temp)
        paths = []
        for index, text in enumerate(normalized):
            path = root / str(index)
            path.write_text(text, encoding="utf-8")
            paths.append(path)
        return (
            merge_file(paths[0], paths[1], paths[2], output),
            len(set(version_lines)) > 1,
        )


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
        metadata_normalized = False
        if ch == nh:
            source = c
        elif ch == bh:
            source, status = n, "upstream"
        elif nh == bh:
            source, status = c, "local"
        elif not b and n and not c:
            source, status = n, "upstream-added"
        elif b and c and n and not any(binary(path) for path in (b, c, n)):
            merged = None
            if area == "skill" and name == "SKILL.md":
                skill_merge = merge_tavern_skill(b, c, n, output_root / name)
                if skill_merge is not None:
                    merged, version_drift = skill_merge
                    metadata_normalized = bool(merged and version_drift)
            if merged is None:
                merged = merge_file(b, c, n, output_root / name)
            if merged:
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
            "metadata_normalized": metadata_normalized,
        })
    return report, conflicts


def run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, **kwargs)


@contextmanager
def update_lock():
    UPDATE_ROOT.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another Tavern update operation is already running") from exc
        stream.seek(0)
        stream.truncate()
        stream.write(json.dumps({"pid": os.getpid(), "started_at": int(time.time())}) + "\n")
        stream.flush()
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def exclusive(command):
    @wraps(command)
    def wrapped(*args, **kwargs):
        with update_lock():
            return command(*args, **kwargs)
    return wrapped


def request_bytes(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "tavern-updater/2"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(), response.getcode(), response.headers.get_content_type()


def validate_release_code(unpacked, managed_files):
    grouped = split_managed(managed_files)
    python_files, shell_files, javascript_files = [], [], []
    for area, names in grouped.items():
        for name in sorted(names):
            path = unpacked / area / name
            if path.suffix == ".py":
                python_files.append(path)
            elif path.suffix == ".sh":
                shell_files.append(path)
            elif path.suffix == ".js":
                javascript_files.append(path)
    if python_files:
        run([PYTHON, "-m", "py_compile", *map(str, python_files)])
    for path in shell_files:
        run(["sh", "-n", str(path)])
    node = shutil.which("node")
    if javascript_files and not node:
        raise RuntimeError("Node.js is required to validate managed frontend JavaScript")
    for path in javascript_files:
        run([node, "--check", str(path)], stdout=subprocess.DEVNULL)
    return {
        "python": len(python_files),
        "shell": len(shell_files),
        "javascript": len(javascript_files),
    }


def health():
    if SKIP_SERVICE:
        return True, {"ok": True, "skipped": True}
    try:
        base = HEALTH_URL.rsplit("/api/health", 1)[0]
        data = request_json(HEALTH_URL)
        checks = {"health": bool(data.get("ok") and data.get("key_set"))}
        for name, path in (
            ("identity", "/api/identity"),
            ("actor_card", "/api/actor_card?lang=zh"),
            ("productions", "/api/productions"),
            ("models", "/api/models"),
        ):
            payload = request_json(base + path)
            checks[name] = payload is not None
        for name, path in (("console", "/"), ("actor", "/actor")):
            body, status, content_type = request_bytes(base + path)
            checks[name] = status == 200 and bool(body) and content_type in ("text/html", "application/xhtml+xml")
        return all(checks.values()), {**data, "checks": checks}
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


def remove_obsolete_updater_files():
    for name in OBSOLETE_UPDATER_FILES:
        try:
            (TARGETS["updater"] / name).unlink()
        except FileNotFoundError:
            pass


def backup_current(version, managed_files):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = BACKUPS / f"{version}-{stamp}-{uuid.uuid4().hex[:8]}"
    backup.mkdir(parents=True, exist_ok=False)
    missing = []
    for area, names in split_managed(managed_files).items():
        for name in sorted(names):
            current = TARGETS[area] / name
            if current.is_file():
                copy_file(current, backup / "installed" / area / name)
            else:
                missing.append(f"{area}/{name}")
    if BASELINE.is_dir():
        shutil.copytree(BASELINE, backup / "baseline")
    obsolete_present = []
    for name in OBSOLETE_UPDATER_FILES:
        current = TARGETS["updater"] / name
        if current.is_file():
            copy_file(current, backup / "obsolete/updater" / name)
            obsolete_present.append("updater/" + name)
    metadata = {
        "managed_files": sorted(managed_files),
        "missing": missing,
        "baseline_present": BASELINE.is_dir(),
        "obsolete_present": obsolete_present,
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
    obsolete_present = set(metadata.get("obsolete_present") or [])
    for name in OBSOLETE_UPDATER_FILES:
        key = "updater/" + name
        target = TARGETS["updater"] / name
        if key in obsolete_present:
            copy_file(backup / "obsolete/updater" / name, target)
        else:
            try:
                target.unlink()
            except FileNotFoundError:
                pass
    shutil.rmtree(BASELINE, ignore_errors=True)
    if metadata.get("baseline_present") and (backup / "baseline").is_dir():
        shutil.copytree(backup / "baseline", BASELINE)
    start_server()


def write_baseline(upstream, managed_files, version):
    pending = UPDATE_ROOT / ".baseline.next"
    shutil.rmtree(pending, ignore_errors=True)
    pending.mkdir(parents=True)
    copy_managed(upstream, pending, managed_files)
    metadata = {
        "schema": 1,
        "version": version,
        "managed_files": sorted(managed_files),
        "hashes": {
            area: tree_hashes(pending / area)
            for area in TARGETS
        },
    }
    (pending / BASELINE_META).write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    old = UPDATE_ROOT / ".baseline.old"
    shutil.rmtree(old, ignore_errors=True)
    if BASELINE.exists():
        BASELINE.rename(old)
    pending.rename(BASELINE)
    shutil.rmtree(old, ignore_errors=True)


def cached_baseline(version, managed_files):
    metadata_path = BASELINE / BASELINE_META
    if not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if metadata.get("schema") != 1 or metadata.get("version") != version:
        return None
    if sorted(metadata.get("managed_files") or []) != sorted(managed_files):
        return None
    actual = {area: tree_hashes(BASELINE / area) for area in TARGETS}
    if actual != metadata.get("hashes"):
        return None
    return BASELINE


def command_check(_args):
    with tempfile.TemporaryDirectory(prefix="tavern-update-check-") as temp:
        release, manifest, _archive, skill_manifest, _skill_archive = release_material(Path(temp))
    installed = local_version()
    skill_installed = local_skill_version()
    print(json.dumps({
        "installed": installed,
        "latest": manifest["version"],
        "skill_installed": skill_installed,
        "skill_latest": skill_manifest["version"],
        "skill_version_drift": bool(skill_installed and skill_installed != installed),
        "release": release["url"],
    }, ensure_ascii=False))


@exclusive
def command_review(_args):
    UPDATE_ROOT.mkdir(parents=True, exist_ok=True)
    PLANS.mkdir(parents=True, exist_ok=True)
    installed = local_version()
    with tempfile.TemporaryDirectory(prefix="tavern-update-review-") as temp:
        work = Path(temp)
        target_work = work / "target"
        release, manifest, archive, skill_manifest, skill_archive = release_material(target_work)
        managed_files = sorted(set(manifest["managed_files"] + skill_manifest["managed_files"]))
        if version_key(manifest["version"]) < version_key(installed):
            raise RuntimeError("latest release is older than the installed version")
        unpacked = target_work / "unpacked"
        unpacked.mkdir()
        safe_extract(archive, unpacked, manifest)
        safe_extract_skill(skill_archive, unpacked, skill_manifest)
        validation = validate_release_code(unpacked, managed_files)

        baseline_trusted = True
        baseline_source = "target-release" if manifest["version"] == installed else "installed-release"
        baseline_warning = ""
        base_root = unpacked
        if manifest["version"] != installed:
            cached = cached_baseline(installed, managed_files)
            if cached:
                base_root = cached
                baseline_source = "verified-cache"
            else:
                try:
                    base_work = work / "base"
                    base_release = tagged_release(installed)
                    (_old_release, old_manifest, old_archive,
                     old_skill_manifest, old_skill_archive) = release_material(
                        base_work, base_release, historical=True)
                    if old_manifest["version"] != installed:
                        raise RuntimeError("installed release version does not match its manifest")
                    base_root = base_work / "unpacked"
                    base_root.mkdir()
                    safe_extract(old_archive, base_root, old_manifest)
                    safe_extract_skill(old_skill_archive, base_root, old_skill_manifest)
                except Exception as exc:
                    baseline_trusted = False
                    baseline_source = "unavailable"
                    baseline_warning = (
                        "No verified official baseline is available for installed version "
                        f"{installed}: {exc}. Existing files that differ from the target "
                        "are treated as conflicts and will not be overwritten."
                    )
                    base_root = work / "untrusted-empty-base"
                    for area in TARGETS:
                        (base_root / area).mkdir(parents=True, exist_ok=True)

        plan_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        plan_dir = PLANS / plan_id
        staged = plan_dir / "staged"
        upstream = plan_dir / "upstream"
        staged.mkdir(parents=True)
        upstream.mkdir(parents=True)
        copy_managed(unpacked, upstream, managed_files)
        files, conflicts = [], []
        managed_by_area = split_managed(managed_files)
        for area, target in TARGETS.items():
            incoming = unpacked / area
            area_files, area_conflicts = merge_area(
                area, base_root / area, target, incoming, staged / area, managed_by_area[area])
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
            "upstream_hashes": {area: tree_hashes(upstream / area) for area in TARGETS},
            "baseline_trusted": baseline_trusted,
            "baseline_source": baseline_source,
            "baseline_warning": baseline_warning,
            "validation": validation,
            "reported_at": None,
            "ready": not conflicts,
            "counts": counts,
            "categories": categories,
            "conflicts": conflicts,
            "metadata_normalized": [
                item["path"] for item in files if item.get("metadata_normalized")
            ],
            "files": files,
        }
        atomic_write_text(
            plan_dir / "plan.json",
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        )
    print(json.dumps({
        "plan_id": plan["plan_id"],
        "installed": plan["installed"],
        "target": plan["target"],
        "ready": plan["ready"],
        "baseline_trusted": plan["baseline_trusted"],
        "baseline_source": plan["baseline_source"],
        "baseline_warning": plan["baseline_warning"],
        "validation": plan["validation"],
        "counts": plan["counts"],
        "categories": plan["categories"],
        "conflicts": plan["conflicts"],
        "metadata_normalized": plan["metadata_normalized"],
    }, ensure_ascii=False))


@exclusive
def command_report(args):
    plan_path = PLANS / args.plan / "plan.json"
    if not plan_path.is_file():
        raise RuntimeError("review plan does not exist")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if managed_fingerprint(plan.get("managed_files") or []) != plan.get("current_fingerprint"):
        raise RuntimeError("installed files changed after review; run review again")
    changes = [item for item in plan.get("files") or [] if item.get("status") != "unchanged"]
    plan["reported_at"] = int(time.time())
    atomic_write_text(plan_path, json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    report = {
        "plan_id": plan["plan_id"],
        "installed": plan["installed"],
        "target": plan["target"],
        "scope": "tavern-system",
        "ready": plan["ready"],
        "baseline_trusted": plan["baseline_trusted"],
        "baseline_source": plan["baseline_source"],
        "baseline_warning": plan["baseline_warning"],
        "validation": plan["validation"],
        "counts": plan["counts"],
        "categories": plan["categories"],
        "conflicts": plan["conflicts"],
        "metadata_normalized": plan.get("metadata_normalized") or [],
        "changes": (
            changes if args.details else [
                {key: item[key] for key in ("path", "category", "status")}
                for item in changes
            ]
        ),
        "details": bool(args.details),
        "excluded": [
            "runtime/web files outside the seven official managed code files",
            "runtime/assets",
            "runtime identity/persona files other than the neutral actor_self.md seed template",
            "starter and fixture content",
            "creative Tavern skill identity files, assets, fixtures, and every file outside the explicit allowlist",
            "/opt/data/tavern-state",
            "credentials and model keys",
        ],
        "next_step": "Report this summary once and wait for approval. Use --details only when the user explicitly requests file hashes or conflict diagnosis.",
    }
    print(json.dumps(report, ensure_ascii=False))


def load_plan(plan_id):
    plan_path = PLANS / plan_id / "plan.json"
    if not plan_path.is_file():
        raise RuntimeError("review plan does not exist")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    staged = plan_path.parent / "staged"
    upstream = plan_path.parent / "upstream"
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
    actual_upstream = {area: tree_hashes(upstream / area) for area in TARGETS}
    if actual_upstream != plan.get("upstream_hashes"):
        raise RuntimeError("verified upstream files changed after review")
    return plan, staged, upstream


@exclusive
def command_apply(args):
    if not args.confirm:
        raise RuntimeError("apply requires --confirm")
    if not args.plan:
        raise RuntimeError("apply requires --plan from a successful review")
    BACKUPS.mkdir(parents=True, exist_ok=True)
    plan, staged, upstream = load_plan(args.plan)
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
        remove_obsolete_updater_files()
        write_baseline(upstream, managed_files, plan["target"])
        state = {
            "installed": plan["target"],
            "previous": installed,
            "backup": str(backup),
            "release": plan["release"],
            "plan_id": args.plan,
            "updated_at": int(time.time()),
        }
        atomic_write_text(STATE, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    except Exception as error:
        restore(backup)
        rollback_ok, rollback_report = health()
        if not rollback_ok:
            raise RuntimeError(
                "update failed and the restored service did not pass validation: "
                + json.dumps(rollback_report, ensure_ascii=False)
            ) from error
        raise
    print(json.dumps({"updated": True, "from": installed, "to": plan["target"], "plan_id": args.plan, "health": report}, ensure_ascii=False))


@exclusive
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
    STATE.unlink()
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
    report.add_argument("--details", action="store_true")
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
