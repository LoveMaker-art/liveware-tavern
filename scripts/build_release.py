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
BACKEND_FILES = ("actor.py", "server.py", "card_import.py", "actor_self.md")


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
        "schema": 3,
        "scope": "backend-system",
        "version": version,
        "archive": ARCHIVE.name,
        "sha256": digest,
        "managed_files": sorted(files),
        "files": files,
    }
    (DIST / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.rmtree(STAGE)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
