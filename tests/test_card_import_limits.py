import base64
import io
import json
import struct
import unittest
import zlib
import zipfile

import card_import


def png_with_chunk(chunk_type, payload):
    chunk = struct.pack(">I", len(payload)) + chunk_type + payload + b"\0\0\0\0"
    end = struct.pack(">I", 0) + b"IEND" + b"\0\0\0\0"
    return card_import.PNG_SIG + chunk + end


class CardImportLimitTests(unittest.TestCase):
    def test_rejects_oversized_png_before_parsing(self):
        with self.assertRaises(ValueError):
            card_import.import_card_bytes(b"x" * (card_import.MAX_PNG_BYTES + 1))

    def test_compressed_metadata_cannot_expand_past_limit(self):
        expanded = b"x" * (card_import.MAX_METADATA_BYTES + 1)
        # iTXt: keyword, compression flag/method, language, translated keyword, text.
        payload = b"ccv3\0\x01\x00\0\0" + zlib.compress(expanded)
        raw = png_with_chunk(b"iTXt", payload)
        chunks = card_import._read_text_chunks(raw)
        self.assertNotIn("ccv3", chunks)

    def test_reads_v3_from_compressed_ztxt(self):
        card = {
            "spec": "chara_card_v3",
            "spec_version": "3.0",
            "data": {"name": "Mara", "description": "An archivist."},
        }
        encoded = base64.b64encode(json.dumps(card).encode("utf-8"))
        payload = b"ccv3\0\x00" + zlib.compress(encoded)
        raw = png_with_chunk(b"zTXt", payload)

        imported = card_import.import_card_bytes(raw)

        self.assertEqual(imported["source_format"], "v3")
        self.assertEqual(imported["name"], "Mara")

    def test_reads_v3_charx_and_preserves_asset_manifest(self):
        card = {
            "spec": "chara_card_v3",
            "spec_version": "3.0",
            "data": {
                "name": "Mara",
                "description": "An archivist.",
                "assets": [{
                    "type": "icon",
                    "uri": "embeded://assets/portrait.png",
                    "ext": "png",
                }],
            },
        }
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            archive.writestr("card.json", json.dumps(card))
            archive.writestr("assets/portrait.png", b"not-a-real-image")

        imported = card_import.import_card_archive_bytes(raw.getvalue())

        self.assertEqual(imported["source_format"], "v3")
        self.assertEqual(imported["source_container"], "charx")
        self.assertEqual(imported["embedded_assets"][0]["path"], "assets/portrait.png")

    def test_rejects_charx_path_traversal(self):
        card = {
            "spec": "chara_card_v3",
            "spec_version": "3.0",
            "data": {"name": "Mara"},
        }
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            archive.writestr("card.json", json.dumps(card))
            archive.writestr("../escape.png", b"x")

        with self.assertRaisesRegex(ValueError, "不安全路径"):
            card_import.import_card_archive_bytes(raw.getvalue())


if __name__ == "__main__":
    unittest.main()
