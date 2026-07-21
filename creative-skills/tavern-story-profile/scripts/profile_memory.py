#!/usr/bin/env python3
"""Inspect and maintain Tavern's structured story profile projections."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path


RUNTIME = Path("/opt/data/apps/tavern-runtime")
STATE = Path("/opt/data/tavern-state")
SEED_ACTOR = RUNTIME / "actor_self.md"
sys.path.insert(0, str(RUNTIME))

import story_profile  # noqa: E402


def _print(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("audit")
    sub.add_parser("memory-preview")
    sub.add_parser("memory-sync")
    sub.add_parser("refresh")

    context = sub.add_parser("context")
    context.add_argument("message", nargs="?", default="")

    for command in ("confirm", "reject"):
        item = sub.add_parser(command)
        item.add_argument("preference_id")

    edit = sub.add_parser("edit")
    edit.add_argument("preference_id")
    edit.add_argument("text")
    edit.add_argument("--scope", choices=("tavern", "ruotang_chat", "both"))

    lock = sub.add_parser("lock")
    lock.add_argument("preference_id")
    lock.add_argument("--off", action="store_true")

    args = parser.parse_args()
    profile = story_profile.ensure_profile(STATE, SEED_ACTOR)

    if args.command == "audit":
        return _print(story_profile.audit(STATE, SEED_ACTOR))
    if args.command == "memory-preview":
        return _print(story_profile.memory_preview(profile))
    if args.command == "memory-sync":
        return _print(story_profile.sync_hermes_memories(profile))
    if args.command == "refresh":
        port = os.environ.get("TAVERN_PORT", "8799")
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/event",
            data=json.dumps({"type": "refresh_story_profile"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            return _print(json.loads(response.read().decode("utf-8")))
    if args.command == "context":
        return print(story_profile.context_for_message(profile, args.message))
    if args.command in {"confirm", "reject"}:
        status = "confirmed" if args.command == "confirm" else "rejected"
        return _print(story_profile.update_preference(
            STATE, SEED_ACTOR, args.preference_id, status=status))
    if args.command == "edit":
        return _print(story_profile.update_preference(
            STATE, SEED_ACTOR, args.preference_id, text=args.text, scope=args.scope))
    if args.command == "lock":
        return _print(story_profile.update_preference(
            STATE, SEED_ACTOR, args.preference_id, locked=not args.off))


if __name__ == "__main__":
    main()
