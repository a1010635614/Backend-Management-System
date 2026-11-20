"""Provider protocol and URL boundaries; no cloud credentials or network calls."""
from hashlib import md5
import unittest
from unittest.mock import patch
from app.cdn import signed_cdn_url, validate_cdn_settings


class CdnSigningTests(unittest.TestCase):
    def test_type_d_protocol(self):
        # Tencent's published vector independently fixes concatenation order.
        key = "dimtm5evg50ijsx2hvuwyfoiu65"
        self.assertEqual(md5((key + "/test.jpg1582791032").encode()).hexdigest(),
                         "900a5049aa8ac1ab144527d9c2be4cea")
        with patch("app.cdn.time.time", return_value=1582791032):
            result = signed_cdn_url("https://cdn.example.com/", "uploads/test.jpg", key)
        expected = md5((key + "/uploads/test.jpg1582791032").encode()).hexdigest()
        self.assertEqual(result,
                         f"https://cdn.example.com/uploads/test.jpg?sign={expected}&t=1582791032")

    def test_encoded_object_path_is_signed_as_transmitted(self):
        result = signed_cdn_url("https://cdn.example.com", "uploads/图片 one.png",
                                "ExampleKey123", timestamp=1700000000)
        path = "/uploads/%E5%9B%BE%E7%89%87%20one.png"
        expected = md5(("ExampleKey123" + path + "1700000000").encode()).hexdigest()
        self.assertEqual(result, f"https://cdn.example.com{path}?sign={expected}&t=1700000000")

    def test_invalid_configuration_fails_without_echoing_secrets(self):
        origins = ["", "http://cdn.example.com", "//cdn.example.com",
                   "https://user:pass@cdn.example.com", "https://cdn.example.com:443",
                   "https://cdn.example.com/folder", "https://cdn.example.com?x=1",
                   "https://cdn.example.com#x", "https://cdn.example.com\n",
                   "https://cdn.example.com\\evil", "https://-invalid.example.com"]
        for origin in origins:
            with self.subTest(origin=origin), self.assertRaises(ValueError) as error:
                validate_cdn_settings(origin, "ExampleKey123")
            self.assertNotIn("ExampleKey123", str(error.exception))
        for key in ("", "short", "has-dashes", "a" * 41):
            with self.subTest(length=len(key)), self.assertRaises(ValueError):
                validate_cdn_settings("https://cdn.example.com", key)

    def test_paths_cannot_escape_the_upload_namespace(self):
        for path in ("/uploads/x.jpg", "https://evil.example/x", "uploads/../x",
                     "uploads/./x", "uploads//x", "uploads/%2e%2e/x",
                     "uploads/x?other=1", "uploads/x#fragment", "uploads/x\\y",
                     "uploads/x\n"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                signed_cdn_url("https://cdn.example.com", path, "ExampleKey123")


if __name__ == "__main__":
    unittest.main()
