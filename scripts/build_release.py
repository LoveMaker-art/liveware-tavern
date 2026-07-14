#!/usr/bin/env python3
"""Build the state-free Tavern release assets consumed by tavern-updater."""

import hashlib
import json
from pathlib import Path
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skill"
UPDATER = ROOT / "updater-skill"
DIST = ROOT / "dist"
STAGE = DIST / "release"
ARCHIVE = DIST / "tavern-release.tar.gz"
SKILL_STAGE = DIST / "skill-release"
SKILL_ARCHIVE = DIST / "tavern-skill.tar.gz"
SKILL_MANIFEST = DIST / "skill-manifest.json"
BOOTSTRAP_SOURCE = ROOT / "bootstrap/tavern_updater_bootstrap.py"
BOOTSTRAP_ASSET = DIST / "tavern-updater-bootstrap.py"
BOOTSTRAP_LAUNCHER_SOURCE = ROOT / "bootstrap/install_tavern_updater.sh"
BOOTSTRAP_LAUNCHER_ASSET = DIST / "install-tavern-updater.sh"
BOOTSTRAP_MANIFEST = DIST / "bootstrap-manifest.json"
BACKEND_FILES = ("actor.py", "actor_self.md", "server.py", "card_import.py")
FRONTEND_FILES = (
    "actor.html",
    "actor.js",
    "app.js",
    "bridge.js",
    "console.css",
    "i18n.js",
    "index.html",
)
SKILL_SCRIPT_FILES = (
    "bringup.sh",
    "install.sh",
    "make_test_card.py",
    "provision.sh",
    "smoke.py",
    "tavern_cli.py",
)


def copy(source, destination):
    if source.is_dir():
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.bak*", "*.before-*", "*.log"))
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def main():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    shutil.rmtree(DIST, ignore_errors=True)
    (STAGE / "runtime").mkdir(parents=True)
    (STAGE / "updater").mkdir(parents=True)
    for name in BACKEND_FILES:
        copy(SOURCE / name, STAGE / "runtime" / name)
    for name in FRONTEND_FILES:
        copy(SOURCE / "reader" / name, STAGE / "runtime/web" / name)
    (STAGE / "runtime/.tavern-release-version").write_text(version + "\n", encoding="utf-8")
    copy(UPDATER / "SKILL.md", STAGE / "updater/SKILL.md")
    copy(UPDATER / "scripts", STAGE / "updater/scripts")
    copy(UPDATER / "references", STAGE / "updater/references")
    if (UPDATER / "agents").is_dir():
        copy(UPDATER / "agents", STAGE / "updater/agents")
    files = {
        path.relative_to(STAGE).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(STAGE.rglob("*"))
        if path.is_file()
    }
    with tarfile.open(ARCHIVE, "w:gz", format=tarfile.PAX_FORMAT) as package:
        package.add(STAGE / "runtime", arcname="runtime")
        package.add(STAGE / "updater", arcname="updater")
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    manifest = {
        "schema": 4,
        "scope": "tavern-system",
        "version": version,
        "archive": ARCHIVE.name,
        "sha256": digest,
        "managed_files": sorted(files),
        "files": files,
    }
    (DIST / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    (SKILL_STAGE / "skill").mkdir(parents=True)
    copy(SOURCE / "SKILL.md", SKILL_STAGE / "skill/SKILL.md")
    copy(SOURCE / "references", SKILL_STAGE / "skill/references")
    for name in SKILL_SCRIPT_FILES:
        copy(SOURCE / "tools" / name, SKILL_STAGE / "skill/scripts" / name)
    skill_files = {
        path.relative_to(SKILL_STAGE).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(SKILL_STAGE.rglob("*"))
        if path.is_file()
    }
    with tarfile.open(SKILL_ARCHIVE, "w:gz", format=tarfile.PAX_FORMAT) as package:
        package.add(SKILL_STAGE / "skill", arcname="skill")
    skill_manifest = {
        "schema": 1,
        "scope": "tavern-creative-skill",
        "version": version,
        "archive": SKILL_ARCHIVE.name,
        "sha256": hashlib.sha256(SKILL_ARCHIVE.read_bytes()).hexdigest(),
        "managed_files": sorted(skill_files),
        "files": skill_files,
    }
    SKILL_MANIFEST.write_text(
        json.dumps(skill_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    copy(BOOTSTRAP_SOURCE, BOOTSTRAP_ASSET)
    copy(BOOTSTRAP_LAUNCHER_SOURCE, BOOTSTRAP_LAUNCHER_ASSET)
    bootstrap_files = {
        BOOTSTRAP_ASSET.name: hashlib.sha256(BOOTSTRAP_ASSET.read_bytes()).hexdigest(),
        BOOTSTRAP_LAUNCHER_ASSET.name: hashlib.sha256(BOOTSTRAP_LAUNCHER_ASSET.read_bytes()).hexdigest(),
    }
    bootstrap_manifest = {
        "schema": 1,
        "scope": "tavern-updater-bootstrap",
        "version": version,
        "file": BOOTSTRAP_ASSET.name,
        "sha256": bootstrap_files[BOOTSTRAP_ASSET.name],
        "files": bootstrap_files,
    }
    BOOTSTRAP_MANIFEST.write_text(
        json.dumps(bootstrap_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.rmtree(STAGE)
    shutil.rmtree(SKILL_STAGE)
    print(json.dumps({"release": manifest, "skill": skill_manifest, "bootstrap": bootstrap_manifest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
