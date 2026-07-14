#!/bin/sh
set -eu

BASE_URL=${TAVERN_BOOTSTRAP_BASE_URL:-https://github.com/LoveMaker-art/liveware-tavern/releases/latest/download}
WORK=$(mktemp -d "${TMPDIR:-/tmp}/tavern-bootstrap.XXXXXX")
trap 'rm -rf "$WORK"' EXIT HUP INT TERM

fetch() {
  url=$1
  output=$2
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$output"
  else
    python3 -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' "$url" "$output"
  fi
}

fetch "$BASE_URL/bootstrap-manifest.json" "$WORK/bootstrap-manifest.json"
fetch "$BASE_URL/tavern-updater-bootstrap.py" "$WORK/tavern-updater-bootstrap.py"

python3 - "$WORK" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
manifest = json.loads((root / "bootstrap-manifest.json").read_text(encoding="utf-8"))
script = root / "tavern-updater-bootstrap.py"
actual = hashlib.sha256(script.read_bytes()).hexdigest()
expected = str(manifest.get("sha256") or "")
if manifest.get("scope") != "tavern-updater-bootstrap" or actual != expected:
    raise SystemExit("Tavern bootstrap SHA256 verification failed")
PY

python3 "$WORK/tavern-updater-bootstrap.py" "$@"
