#!/usr/bin/env python3
"""Compatibility entry point for the canonical Hermes Tavern CLI."""

import importlib.util
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "skills/tavern/scripts/tavern_cli.py"
SPEC = importlib.util.spec_from_file_location("tavern_cli_canonical", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

for _name in dir(MODULE):
    if not _name.startswith("__"):
        globals()[_name] = getattr(MODULE, _name)


if __name__ == "__main__":
    MODULE.main()
