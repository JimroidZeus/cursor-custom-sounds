import tempfile
import unittest
import zipfile
from pathlib import Path

from soundpack_builder.config import BuilderConfig
from soundpack_builder.downloader import (
    ClipEntry,
    _output_filename,
    _write_recommended_configs,
    extract_from_zip,
)


class ExtractFromZipRegressionTest(unittest.TestCase):
    def test_extract_from_zip_returns_persistent_file_for_path_in_archive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            zip_path = temp_root / "sample.zip"
            downloads_dir = temp_root / "downloads"

            payload = b"fake-audio-bytes"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("Base form/Main Voice Files/Goku_3(49174).wav", payload)

            # Intentionally pass backslashes and different casing to ensure
            # path normalization works for Windows-style manifest entries.
            extracted = extract_from_zip(
                zip_path,
                path_in_archive=r"base form\main voice files\goku_3(49174).wav",
                temp_dir=downloads_dir,
            )

            self.assertTrue(extracted.exists(), "Extracted file should persist after return.")
            self.assertEqual(extracted.read_bytes(), payload)
            self.assertEqual(extracted.parent.resolve(), downloads_dir.resolve())


class OutputFilenameTest(unittest.TestCase):
    def test_uses_path_in_archive_basename(self) -> None:
        entry = ClipEntry(
            universe="dragon-ball-z",
            character="goku",
            url="https://example.com/archive.zip",
            pathInArchive="Base form/Main Voice Files/Goku_3(49174).wav",
        )
        self.assertEqual(_output_filename(entry), "Goku_3(49174).wav")

    def test_uses_url_basename_when_no_archive_path(self) -> None:
        entry = ClipEntry(
            universe="team-fortress-2",
            character="demoman",
            url="https://example.com/demoman/yes01.mp3?download=true",
        )
        self.assertEqual(_output_filename(entry), "yes01.wav")


class RecommendedConfigGenerationTest(unittest.TestCase):
    def test_writes_recommended_config_without_transcription(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = BuilderConfig(
                repo_root=root,
                manifests_dir=root / "manifests",
                configs_dir=root / "configs",
                sound_dir=root / "sounds",
            )
            pack_dir = cfg.sound_dir / "warcraft" / "orc-peon"
            pack_dir.mkdir(parents=True, exist_ok=True)
            (pack_dir / "PeonReady1.wav").write_bytes(b"wav-data")
            (pack_dir / "PeonWhat2.wav").write_bytes(b"wav-data")

            result = _write_recommended_configs(
                cfg,
                {("warcraft", "orc-peon")},
                skip_transcript=True,
                whisper_model="tiny",
                whisper_language="en",
                whisper_device="auto",
                whisper_compute_type="auto",
                overwrite=True,
            )
            self.assertEqual(len(result), 1)
            self.assertTrue(result[0]["ok"])
            self.assertEqual(result[0]["transcription"], "filename-only")

            config_path = pack_dir / "sound-config.json"
            self.assertTrue(config_path.exists())
            payload = config_path.read_text(encoding="utf-8")
            self.assertIn('"soundPack": "warcraft"', payload)
            self.assertIn('"soundSubdir": "orc-peon"', payload)
            report_path = pack_dir / "mapping-report.json"
            self.assertTrue(report_path.exists())
            report = report_path.read_text(encoding="utf-8")
            self.assertIn('"events"', report)
            self.assertIn('"transcription": "filename-only"', report)


if __name__ == "__main__":
    unittest.main()
