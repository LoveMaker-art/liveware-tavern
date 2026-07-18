import io
import json
import os
import socket
import tempfile
import threading
import unittest
from unittest import mock

from runtime_http import (
    BoundedThreadingHTTPServer,
    RequestBodyTooLarge,
    read_request_body,
    safe_static_path,
    validate_outbound_http_base,
)
from state_store import InvalidStateIdentifier, JsonStateStore


class DummyRequest:
    def __init__(self, body, headers):
        self.rfile = io.BytesIO(body)
        self.headers = headers


class StateStoreTests(unittest.TestCase):
    def test_round_trip_and_atomic_replacement(self):
        with tempfile.TemporaryDirectory() as root:
            store = JsonStateStore(root)
            store.write("worldbooks", "wb_valid-1", {"id": "wb_valid-1"})
            self.assertEqual(store.read("worldbooks", "wb_valid-1")["id"], "wb_valid-1")
            self.assertFalse(any(".tmp." in name for name in os.listdir(os.path.join(root, "worldbooks"))))

    def test_rejects_path_traversal_identifiers(self):
        with tempfile.TemporaryDirectory() as root:
            store = JsonStateStore(root)
            for identifier in ("../auth", "a/b", "..", "", "角色"):
                with self.subTest(identifier=identifier):
                    with self.assertRaises(InvalidStateIdentifier):
                        store.write("worldbooks", identifier, {})

    def test_list_skips_corrupt_files(self):
        with tempfile.TemporaryDirectory() as root:
            store = JsonStateStore(root)
            store.write("cards", "card_ok", {"id": "card_ok"})
            with open(os.path.join(root, "cards", "card_bad.json"), "w", encoding="utf-8") as file:
                file.write("{")
            self.assertEqual(store.list("cards"), [{"id": "card_ok"}])

    def test_concurrent_updates_do_not_lose_changes(self):
        with tempfile.TemporaryDirectory() as root:
            store = JsonStateStore(root)
            store.write("worldbooks", "wb_one", {"entries": []})
            barrier = threading.Barrier(3)

            def append(value):
                barrier.wait()
                store.update(
                    "worldbooks", "wb_one",
                    lambda document: {
                        **document,
                        "entries": [*(document.get("entries") or []), value],
                    },
                )

            threads = [threading.Thread(target=append, args=(value,)) for value in ("a", "b")]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join()
            self.assertEqual(set(store.read("worldbooks", "wb_one")["entries"]), {"a", "b"})


class HttpBoundaryTests(unittest.TestCase):
    @mock.patch("runtime_http.ThreadingHTTPServer.__init__", return_value=None)
    def test_http_worker_limit_is_bounded(self, _server_init):
        low = BoundedThreadingHTTPServer(("127.0.0.1", 0), object, max_workers=1)
        high = BoundedThreadingHTTPServer(("127.0.0.1", 0), object, max_workers=1000)
        self.assertEqual(low.max_workers, 2)
        self.assertEqual(high.max_workers, 64)

    def test_static_path_stays_under_reader(self):
        with tempfile.TemporaryDirectory() as root:
            expected = os.path.join(os.path.realpath(root), "app.js")
            self.assertEqual(safe_static_path(root, "/app.js"), expected)
            for path in ("/../server.py", "/%2e%2e/server.py", "/a/../../server.py"):
                with self.subTest(path=path):
                    with self.assertRaises(ValueError):
                        safe_static_path(root, path)

    def test_fixed_body_limit(self):
        request = DummyRequest(b"abcd", {"Content-Length": "4"})
        with self.assertRaises(RequestBodyTooLarge):
            read_request_body(request, 3)

    def test_chunked_body_limit_and_success(self):
        raw = b"3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n"
        request = DummyRequest(raw, {"Transfer-Encoding": "chunked"})
        self.assertEqual(read_request_body(request, 5), b"abcde")
        request = DummyRequest(raw, {"Transfer-Encoding": "chunked"})
        with self.assertRaises(RequestBodyTooLarge):
            read_request_body(request, 4)

    def test_rejects_ambiguous_or_unsupported_body_framing(self):
        ambiguous = DummyRequest(
            b"0\r\n\r\n", {"Content-Length": "5", "Transfer-Encoding": "chunked"})
        with self.assertRaises(ValueError):
            read_request_body(ambiguous, 10)
        unsupported = DummyRequest(b"", {"Transfer-Encoding": "gzip, chunked"})
        with self.assertRaises(ValueError):
            read_request_body(unsupported, 10)

    def test_chunked_trailers_are_consumed(self):
        raw = b"3\r\nabc\r\n0\r\nX-Trace: one\r\n\r\nnext"
        request = DummyRequest(raw, {"Transfer-Encoding": "chunked"})
        self.assertEqual(read_request_body(request, 3), b"abc")
        self.assertEqual(request.rfile.read(), b"next")

    @mock.patch("runtime_http.socket.getaddrinfo")
    def test_outbound_base_rejects_private_resolution(self, resolve):
        resolve.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
        with self.assertRaises(ValueError):
            validate_outbound_http_base("http://example.test/v1")

    @mock.patch("runtime_http.socket.getaddrinfo")
    def test_outbound_base_accepts_public_resolution(self, resolve):
        resolve.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
        self.assertEqual(
            validate_outbound_http_base("https://api.example.test/v1"),
            "https://api.example.test/v1",
        )


if __name__ == "__main__":
    unittest.main()
