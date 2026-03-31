from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from soundpack_builder.tools.repair_wavs import needs_repair, scan_and_repair


class NeedsRepairTest(unittest.TestCase):
    def test_true_for_mp3_bytes_with_wav_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "clip.wav"
            p.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00")
            self.assertTrue(needs_repair(p))

    def test_true_for_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "empty.wav"
            p.write_bytes(b"")
            self.assertTrue(needs_repair(p))


class ScanAndRepairTest(unittest.TestCase):
    def test_html_placeholder_skips_ffmpeg_and_is_not_other_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bad = root / "saved-page.wav"
            bad.write_text("<!doctype html><html><body>login</body></html>", encoding="ascii")

            with patch("soundpack_builder.tools.repair_wavs.convert_to_wav") as mock_convert:
                repaired, skipped_ok, html_ph, errors = scan_and_repair(
                    root,
                    dry_run=False,
                    progress=False,
                )
            mock_convert.assert_not_called()
            self.assertEqual(repaired, 0)
            self.assertEqual(skipped_ok, 0)
            self.assertEqual(len(html_ph), 1)
            self.assertIn("HTML", html_ph[0])
            self.assertEqual(errors, [])

    def test_dry_run_non_html_increments_repaired_not_html(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / "id3.wav"
            p.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00")

            repaired, skipped_ok, html_ph, errors = scan_and_repair(
                root,
                dry_run=True,
                progress=False,
            )
            self.assertEqual(repaired, 1)
            self.assertEqual(skipped_ok, 0)
            self.assertEqual(html_ph, [])
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
