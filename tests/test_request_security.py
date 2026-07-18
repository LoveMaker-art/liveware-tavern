import unittest

from request_security import RequestAuthorizer


class RequestAuthorizerTests(unittest.TestCase):
    def test_same_forwarded_origin_is_allowed(self):
        authorizer = RequestAuthorizer(allowed_origins="", trusted_user_header="")
        headers = {
            "Origin": "https://tavern.example",
            "Host": "127.0.0.1:8799",
            "X-Forwarded-Host": "tavern.example",
            "X-Forwarded-Proto": "https",
        }
        self.assertEqual(authorizer.rejection_reason(headers, state_changing=True), "")

    def test_cross_site_and_opaque_origins_are_rejected(self):
        authorizer = RequestAuthorizer(allowed_origins="", trusted_user_header="")
        for origin in ("https://evil.example", "null", "javascript:alert(1)"):
            with self.subTest(origin=origin):
                reason = authorizer.rejection_reason(
                    {"Origin": origin, "Host": "tavern.example"}, state_changing=True)
                self.assertIn("not allowed", reason)

    def test_explicit_origin_and_relay_identity(self):
        authorizer = RequestAuthorizer(
            allowed_origins="https://console.example", trusted_user_header="X-Relay-User")
        headers = {"Origin": "https://console.example", "X-Relay-User": "user-1"}
        self.assertEqual(authorizer.rejection_reason(headers, state_changing=True), "")
        self.assertIn(
            "identity",
            authorizer.rejection_reason({"Origin": "https://console.example"}),
        )

    def test_get_without_origin_remains_compatible(self):
        authorizer = RequestAuthorizer(allowed_origins="", trusted_user_header="")
        self.assertEqual(authorizer.rejection_reason({}, state_changing=False), "")


if __name__ == "__main__":
    unittest.main()
