"""Invalidate cached Hermes agents only when SOUL.md changes on disk."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from threading import Lock


_lock = Lock()
_known_revision = None


def _soul_revision() -> str:
    home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    try:
        return hashlib.sha256((home / "SOUL.md").read_bytes()).hexdigest()
    except OSError:
        return ""


def _release_cached_agents(gateway) -> None:
    cache = getattr(gateway, "_agent_cache", None)
    cache_lock = getattr(gateway, "_agent_cache_lock", None)
    if cache is None or cache_lock is None:
        return
    with cache_lock:
        entries = list(cache.values())
        cache.clear()
    release = getattr(gateway, "_release_evicted_agent_soft", None)
    if callable(release):
        for entry in entries:
            agent = entry[0] if isinstance(entry, tuple) else entry
            release(agent)


def register(ctx):
    global _known_revision
    _known_revision = _soul_revision()

    def refresh_personality(gateway=None, **kwargs):
        del kwargs
        global _known_revision
        revision = _soul_revision()
        with _lock:
            if revision == _known_revision:
                return {"action": "allow"}
            _known_revision = revision
        if gateway is not None:
            _release_cached_agents(gateway)
        return {"action": "allow"}

    ctx.register_hook("pre_gateway_dispatch", refresh_personality)
