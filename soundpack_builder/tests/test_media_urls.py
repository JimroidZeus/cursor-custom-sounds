import tempfile
import unittest
from pathlib import Path

from soundpack_builder.core.media_urls import looks_like_html_file, normalize_absolute_media_url


class NormalizeAbsoluteMediaUrlTest(unittest.TestCase):
    def test_fixes_double_https_concat(self) -> None:
        self.assertEqual(
            normalize_absolute_media_url(
                "https://freesound.orghttps://cdn.freesound.org/previews/388/388208_932959-lq.mp3"
            ),
            "https://cdn.freesound.org/previews/388/388208_932959-lq.mp3",
        )

    def test_fixes_urljoin_slash_https_artifact(self) -> None:
        self.assertEqual(
            normalize_absolute_media_url("https://freesound.org/https://cdn.freesound.org/x.mp3"),
            "https://cdn.freesound.org/x.mp3",
        )

    def test_preserves_single_url(self) -> None:
        u = "https://cdn.freesound.org/previews/1/1_2-hq.mp3"
        self.assertEqual(normalize_absolute_media_url(u), u)


class LooksLikeHtmlFileTest(unittest.TestCase):
    def test_detects_doctype(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.wav"
            p.write_bytes(b"<!DOCTYPE html><html>")
            self.assertTrue(looks_like_html_file(p))

    def test_detects_html5_lowercase_doctype(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fake.mp3"
            p.write_bytes(b"\n\n\n<!doctype html>\n<html lang=\"en\">")
            self.assertTrue(looks_like_html_file(p))

    def test_mp3_id3_not_html(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.mp3"
            p.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00")
            self.assertFalse(looks_like_html_file(p))


if __name__ == "__main__":
    unittest.main()
