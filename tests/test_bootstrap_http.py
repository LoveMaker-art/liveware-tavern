import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "skill"


def _unused_loopback_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class BootstrapHttpTests(unittest.TestCase):
    def test_frontend_bootstrap_endpoints_on_real_server(self):
        with tempfile.TemporaryDirectory() as state_dir, tempfile.TemporaryDirectory() as runtime_dir:
            runtime_root = Path(runtime_dir)
            shutil.copytree(SOURCE_ROOT, runtime_root, dirs_exist_ok=True)
            (runtime_root / "reader").rename(runtime_root / "web")
            port = _unused_loopback_port()
            environment = dict(os.environ)
            environment.update({
                "TAVERN_STATE_DIR": state_dir,
                "TAVERN_HOST": "127.0.0.1",
                "TAVERN_MODEL_KEY": "",
            })
            process = subprocess.Popen(
                [sys.executable, "server.py", "--port", str(port)],
                cwd=runtime_root,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                base = f"http://127.0.0.1:{port}"
                for _ in range(80):
                    if process.poll() is not None:
                        self.fail("server exited during startup: " + (process.stderr.read() or ""))
                    try:
                        with urllib.request.urlopen(base + "/api/health", timeout=0.25) as response:
                            if response.status == 200:
                                self.assertEqual(response.headers.get("Cache-Control"), "no-store")
                                policy = response.headers.get("Content-Security-Policy") or ""
                                self.assertIn("script-src 'self' 'nonce-", policy)
                                self.assertNotIn("script-src 'self' 'unsafe-inline'", policy)
                                break
                    except (OSError, urllib.error.URLError):
                        time.sleep(0.025)
                else:
                    self.fail("server did not become healthy")

                endpoints = (
                    "/api/identity",
                    "/api/productions?summary=1",
                    "/api/cards",
                    "/api/worldbooks",
                    "/api/library/worldbooks",
                    "/api/models",
                    "/api/tts/config",
                )
                for endpoint in endpoints:
                    with self.subTest(endpoint=endpoint):
                        with urllib.request.urlopen(base + endpoint, timeout=2) as response:
                            self.assertEqual(response.status, 200)
                            self.assertIsNotNone(json.load(response))

                def event(payload):
                    request = urllib.request.Request(
                        base + "/api/event",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(request, timeout=2) as response:
                        self.assertEqual(response.status, 200)
                        return json.load(response)

                created = event({"type": "create_blank_production", "name": "Test world"})
                production_id = created["production"]["id"]
                with urllib.request.urlopen(
                    base + "/api/productions?summary=1", timeout=2
                ) as response:
                    summaries = json.load(response)["productions"]
                self.assertEqual(summaries[0]["id"], production_id)
                self.assertNotIn("story", summaries[0])
                self.assertNotIn("runtime", summaries[0])
                with urllib.request.urlopen(
                    base + "/api/production?production_id=" + production_id,
                    timeout=2,
                ) as response:
                    detail = json.load(response)["production"]
                self.assertEqual(detail["id"], production_id)
                self.assertIn("story", detail)
                asset_dir = Path(state_dir) / "world-assets" / production_id
                asset_dir.mkdir(parents=True)
                asset_path = asset_dir / "background.png"
                asset_path.write_bytes(b"\x89PNG\r\n\x1a\nworld-theme-test")
                themed = event({
                    "type": "update_world_ui",
                    "production_id": production_id,
                    "ui": {
                        "version": 1,
                        "theme": {
                            "accent": "#AABBCC",
                            "background_fit": "contain",
                            "reading_surface": "glass",
                        },
                        "assets": {
                            "background_desktop": (
                                f"/world-assets/{production_id}/background.png"
                            ),
                        },
                    },
                })
                self.assertEqual(themed["production"]["ui"]["theme"]["accent"], "#aabbcc")
                with urllib.request.urlopen(
                    base + f"/world-assets/{production_id}/background.png",
                    timeout=2,
                ) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers.get_content_type(), "image/png")
                    self.assertEqual(
                        response.headers.get("Cache-Control"),
                        "private, max-age=86400, immutable",
                    )
                with self.assertRaises(urllib.error.HTTPError) as invalid_query:
                    urllib.request.urlopen(
                        base + "/api/production/worldbooks?production_id=../escape",
                        timeout=2,
                    )
                self.assertEqual(invalid_query.exception.code, 400)
                bad_event = urllib.request.Request(
                    base + "/api/event",
                    data=json.dumps({
                        "type": "set_note",
                        "production_id": "../escape",
                        "note": "x",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with self.assertRaises(urllib.error.HTTPError) as invalid_event:
                    urllib.request.urlopen(bad_event, timeout=2)
                self.assertEqual(invalid_event.exception.code, 400)
                added_lore = event({
                    "type": "add_lore",
                    "production_id": production_id,
                    "content": "The gate opens at midnight.",
                    "constant": False,
                    "keys": ["gate"],
                })
                entry_id = added_lore["entry"]["id"]
                worldbook_id = added_lore["worldbook"]["id"]
                updated_lore = event({
                    "type": "update_lore",
                    "production_id": production_id,
                    "worldbook_id": worldbook_id,
                    "entry_id": entry_id,
                    "content": "The gate opens before dawn.",
                    "constant": False,
                    "keys": ["gate"],
                })
                self.assertEqual(
                    updated_lore["entry"]["content"],
                    "The gate opens before dawn.",
                )
                deleted_lore = event({
                    "type": "delete_lore",
                    "production_id": production_id,
                    "worldbook_id": worldbook_id,
                    "entry_id": entry_id,
                })
                self.assertEqual(deleted_lore["deleted"], entry_id)
                prepared = event({
                    "type": "prepare_delete_production",
                    "production_id": production_id,
                })
                deleted = event({
                    "type": "delete_production",
                    "production_id": production_id,
                    "confirmation_token": prepared["confirmation_token"],
                })
                self.assertEqual(deleted["deleted"], production_id)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()
