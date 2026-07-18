import struct
import unittest
import zlib

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


if __name__ == "__main__":
    unittest.main()
