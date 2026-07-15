#!/usr/bin/env python3
"""Install Tavern's verified updater on legacy Hermes/ClawChat instances."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid


REPO = os.environ.get("TAVERN_UPDATE_REPO", "LoveMaker-art/liveware-tavern")
RELEASE_API = os.environ.get(
    "TAVERN_BOOTSTRAP_RELEASE_API",
    f"https://api.github.com/repos/{REPO}/releases/latest",
)
ASSET_MANIFEST = "manifest.json"
ASSET_ARCHIVE = "tavern-release.tar.gz"
SKILL_ASSET_MANIFEST = "skill-manifest.json"
SKILL_ASSET_ARCHIVE = "tavern-skill.tar.gz"
UPDATER_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/release-format.md",
    "scripts/update.py",
)
OBSOLETE_UPDATER_FILES = ("references/conflict-inspection.md",)
SKILL_FILES = (
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
)
AGENTS_START = "<!-- tavern-updater:start -->"
AGENTS_END = "<!-- tavern-updater:end -->"
AGENTS_BLOCK = f"""{AGENTS_START}
## Tavern System Updates

Use `/opt/data/skills/system/tavern-updater` for Tavern update checks, reviews,
installation, and rollback. Never improvise `git pull` or overwrite the runtime
directory.

Use this workflow:

```sh
python3 /opt/data/skills/system/tavern-updater/scripts/update.py check
python3 /opt/data/skills/system/tavern-updater/scripts/update.py review
python3 /opt/data/skills/system/tavern-updater/scripts/update.py report --plan <PLAN_ID>
```

After `report`, show one concise summary: installed and target versions, changed
categories, validation, protected data boundaries, metadata normalization, and
real conflicts. Do not print hashes or exhaustive file details unless the user
asks. Stop and wait for a new explicit user approval. Only after that approval run:

```sh
python3 /opt/data/skills/system/tavern-updater/scripts/update.py apply --plan <PLAN_ID> --confirm
```

The updater manages its allowlisted Tavern backend, official frontend,
operational Tavern skill, release marker, and updater files as one release.
Do not ask separately whether the Tavern skill should be synchronized. Never
update identity/persona files, runtime or skill assets, starter content,
`/opt/data/tavern-state`, `/opt/data/config.yaml`, credentials, sessions, or
logs. A failed application update must restore the previous managed files.
Never use current instance files as an official merge baseline. If the installed
version has no verified Release or cached baseline, differing files are conflicts
and must not be overwritten. Validate backend, frontend, and read-only API surfaces
before committing an update.

Treat a Tavern Skill version mismatch as informational. The updater normalizes
the release-owned `version:` field during review. Never edit `SKILL.md` only to
align versions, never search temporary directories for reviewed files, and never
generate repeated plans unless managed files actually changed.
{AGENTS_END}"""


def request_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "tavern-updater-bootstrap/1",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def download(url, destination):
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/octet-stream", "User-Agent": "tavern-updater-bootstrap/1"},
    )
    with urllib.request.urlopen(request, timeout=120) as response, open(destination, "wb") as output:
        shutil.copyfileobj(response, output)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_release(work, release_dir=None):
    if release_dir:
        release_dir = Path(release_dir)
        manifest_path = release_dir / ASSET_MANIFEST
        archive_path = release_dir / ASSET_ARCHIVE
        skill_manifest_path = release_dir / SKILL_ASSET_MANIFEST
        skill_archive_path = release_dir / SKILL_ASSET_ARCHIVE
        if not all(path.is_file() for path in (
                manifest_path, archive_path, skill_manifest_path, skill_archive_path)):
            raise RuntimeError("local release directory is missing required assets")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        skill_manifest = json.loads(skill_manifest_path.read_text(encoding="utf-8"))
        return ({"tag": "v" + str(manifest.get("version") or ""), "url": str(release_dir)},
                manifest, archive_path, skill_manifest, skill_archive_path)

    release = request_json(RELEASE_API)
    if release.get("draft") or release.get("prerelease"):
        raise RuntimeError("latest GitHub release is not stable")
    assets = {item.get("name"): item.get("browser_download_url") for item in release.get("assets") or []}
    required_assets = (ASSET_MANIFEST, ASSET_ARCHIVE, SKILL_ASSET_MANIFEST, SKILL_ASSET_ARCHIVE)
    missing = [name for name in required_assets if not assets.get(name)]
    if missing:
        raise RuntimeError("release is missing required assets: " + ", ".join(missing))
    manifest_path = work / ASSET_MANIFEST
    archive_path = work / ASSET_ARCHIVE
    skill_manifest_path = work / SKILL_ASSET_MANIFEST
    skill_archive_path = work / SKILL_ASSET_ARCHIVE
    download(assets[ASSET_MANIFEST], manifest_path)
    download(assets[ASSET_ARCHIVE], archive_path)
    download(assets[SKILL_ASSET_MANIFEST], skill_manifest_path)
    download(assets[SKILL_ASSET_ARCHIVE], skill_archive_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    skill_manifest = json.loads(skill_manifest_path.read_text(encoding="utf-8"))
    return {
        "tag": release.get("tag_name"),
        "url": release.get("html_url"),
    }, manifest, archive_path, skill_manifest, skill_archive_path


def validate_release(release, manifest, archive_path, skill_manifest, skill_archive_path):
    if (manifest.get("schema") != 4 or manifest.get("scope") != "tavern-system"
            or manifest.get("archive") != ASSET_ARCHIVE):
        raise RuntimeError("unsupported release manifest")
    version = str(manifest.get("version") or "")
    if release.get("tag") != "v" + version:
        raise RuntimeError("release tag and manifest version do not match")
    if sha256_file(archive_path) != manifest.get("sha256"):
        raise RuntimeError("release archive SHA256 mismatch")
    managed = set(manifest.get("managed_files") or [])
    hashes = manifest.get("files") or {}
    required = {"updater/" + name for name in UPDATER_FILES}
    if not required.issubset(managed) or not required.issubset(hashes):
        raise RuntimeError("release does not contain the complete updater skill")
    if (skill_manifest.get("schema") != 1
            or skill_manifest.get("scope") != "tavern-creative-skill"
            or skill_manifest.get("archive") != SKILL_ASSET_ARCHIVE):
        raise RuntimeError("unsupported Tavern skill manifest")
    if str(skill_manifest.get("version") or "") != version:
        raise RuntimeError("runtime and Tavern skill release versions do not match")
    if sha256_file(skill_archive_path) != skill_manifest.get("sha256"):
        raise RuntimeError("Tavern skill archive SHA256 mismatch")
    skill_managed = set(skill_manifest.get("managed_files") or [])
    skill_hashes = skill_manifest.get("files") or {}
    allowed = {"skill/" + name for name in SKILL_FILES}
    if skill_managed != allowed or set(skill_hashes) != allowed:
        raise RuntimeError("Tavern skill release does not match the safe allowlist")


def extract_updater(archive_path, manifest, destination):
    expected = manifest.get("files") or {}
    required = {"updater/" + name: name for name in UPDATER_FILES}
    found = set()
    with tarfile.open(archive_path, "r:gz") as package:
        for member in package.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise RuntimeError("release archive contains an unsafe path")
            if path.parts[0] not in ("runtime", "updater"):
                raise RuntimeError("release archive contains an unmanaged top-level path")
            if member.issym() or member.islnk() or member.isdev():
                raise RuntimeError("release archive contains an unsupported link or device")
            key = path.as_posix()
            if key not in required:
                continue
            source = package.extractfile(member)
            if source is None:
                raise RuntimeError(f"release updater file is unreadable: {key}")
            data = source.read()
            if sha256_bytes(data) != expected.get(key):
                raise RuntimeError(f"release updater file SHA256 mismatch: {key}")
            target = destination / required[key]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            found.add(key)
    if found != set(required):
        missing = sorted(set(required) - found)
        raise RuntimeError("release archive is missing updater files: " + ", ".join(missing))
    (destination / "scripts/update.py").chmod(0o755)


def atomic_write(path, content):
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


def backup_existing(data_root, updater_target, agents_path):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = data_root / "tavern-updates/bootstrap-backups" / stamp
    copied = False
    if updater_target.is_dir():
        shutil.copytree(updater_target, backup / "tavern-updater")
        copied = True
    if agents_path.is_file():
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(agents_path, backup / "AGENTS.md")
        copied = True
    return str(backup) if copied else ""


def install_updater(staged, target):
    for name in UPDATER_FILES:
        source = staged / name
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        pending = destination.parent / ("." + destination.name + ".next-" + uuid.uuid4().hex[:8])
        try:
            shutil.copy2(source, pending)
            os.replace(pending, destination)
        finally:
            try:
                pending.unlink()
            except OSError:
                pass
    for name in OBSOLETE_UPDATER_FILES:
        try:
            (target / name).unlink()
        except FileNotFoundError:
            pass


def sync_agents(path):
    current = path.read_text(encoding="utf-8") if path.is_file() else "# AGENTS.md\n"
    marked = re.compile(re.escape(AGENTS_START) + r".*?" + re.escape(AGENTS_END), re.DOTALL)
    legacy = re.compile(r"(?ms)^## Tavern (?:Backend|System) Updates\s*\n.*?(?=^## |\Z)")
    if marked.search(current):
        updated = marked.sub(AGENTS_BLOCK, current, count=1)
    elif legacy.search(current):
        updated = legacy.sub(AGENTS_BLOCK + "\n\n", current, count=1)
    else:
        updated = current.rstrip() + "\n\n" + AGENTS_BLOCK + "\n"
    updated = re.sub(r"(?m)^Current deployed skill version:.*\n?", "", updated)
    if updated != current:
        atomic_write(path, updated)
        return True
    return False


def run_json(command, env):
    result = subprocess.run(command, check=False, text=True, capture_output=True, env=env)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"command failed ({' '.join(command)}): {detail}")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("updater command returned no report")
    return json.loads(lines[-1])


def generate_report(update_script, data_root):
    env = os.environ.copy()
    env["TAVERN_DATA_ROOT"] = str(data_root)
    check = run_json([sys.executable, str(update_script), "check"], env)
    review = run_json([sys.executable, str(update_script), "review"], env)
    report = run_json(
        [sys.executable, str(update_script), "report", "--plan", review["plan_id"]],
        env,
    )
    return {"check": check, "report": report}


def apply_reported_plan(update_script, data_root, report):
    if not report.get("ready"):
        raise RuntimeError("review contains conflicts; automatic update was stopped")
    env = os.environ.copy()
    env["TAVERN_DATA_ROOT"] = str(data_root)
    return run_json(
        [sys.executable, str(update_script), "apply", "--plan", report["plan_id"], "--confirm"],
        env,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Install Tavern's verified updater on a legacy Hermes instance and generate an update report."
    )
    parser.add_argument("--data-root", default=os.environ.get("TAVERN_DATA_ROOT", "/opt/data"))
    parser.add_argument("--apply", action="store_true", help="apply the reviewed update after installation")
    parser.add_argument("--confirm", action="store_true", help="confirm that this command authorizes update installation")
    parser.add_argument("--release-dir", help=argparse.SUPPRESS)
    parser.add_argument("--skip-report", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.apply and not args.confirm:
        raise RuntimeError("--apply requires --confirm")

    data_root = Path(args.data_root).resolve()
    updater_target = data_root / "skills/system/tavern-updater"
    agents_path = data_root / "AGENTS.md"
    with tempfile.TemporaryDirectory(prefix="tavern-updater-bootstrap-") as temp:
        work = Path(temp)
        release, manifest, archive_path, skill_manifest, skill_archive_path = fetch_release(work, args.release_dir)
        validate_release(release, manifest, archive_path, skill_manifest, skill_archive_path)
        staged_updater = work / "updater"
        extract_updater(archive_path, manifest, staged_updater)
        backup = backup_existing(data_root, updater_target, agents_path)
        install_updater(staged_updater, updater_target)
        agents_changed = sync_agents(agents_path)

    result = {
        "ok": True,
        "bootstrap_schema": 1,
        "updater_installed": True,
        "tavern_skill_included": True,
        "release": release["url"],
        "release_version": manifest["version"],
        "agents_updated": agents_changed,
        "backup": backup,
        "next_step": "Show one update report and wait for approval. The operational Tavern skill is included in that plan and must not be offered as a separate follow-up.",
    }
    if not args.skip_report:
        result.update(generate_report(updater_target / "scripts/update.py", data_root))
        report = result["report"]
        if args.apply:
            if result["check"].get("installed") == result["check"].get("latest") and not report.get("changes"):
                result["apply"] = {"updated": False, "already_current": True}
            else:
                result["apply"] = apply_reported_plan(
                    updater_target / "scripts/update.py", data_root, report)
            result["next_step"] = "Report the installed version and health result."
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
