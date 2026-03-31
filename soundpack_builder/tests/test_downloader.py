import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from soundpack_builder.core.config import BuilderConfig
from soundpack_builder.pipeline.downloader import (
    ClipEntry,
    _is_riff_wave,
    _output_filename,
    _write_recommended_configs,
    download_clips,
    extract_from_zip,
)


class ZipUrlDownloadCacheTest(unittest.TestCase):
    """Same ``.zip`` URL reused across manifest rows should trigger one HTTP download."""

    def test_shared_zip_url_downloads_archive_once(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture_zip = root / "fixture.zip"
            wav_bytes = b"RIFF" + (36).to_bytes(4, "little") + b"WAVE"
            with zipfile.ZipFile(fixture_zip, "w") as zf:
                zf.writestr("a.wav", wav_bytes)
                zf.writestr("b.wav", wav_bytes)

            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "universe": "u",
                                "character": "c",
                                "url": "https://example.com/pack.zip?updated=1",
                                "pathInArchive": "a.wav",
                            },
                            {
                                "universe": "u",
                                "character": "c",
                                "url": "https://example.com/pack.zip?updated=2",
                                "pathInArchive": "b.wav",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            cfg = BuilderConfig(
                repo_root=root,
                manifests_dir=root / "manifests",
                configs_dir=root / "configs",
                sound_dir=root / "sounds",
            )

            download_calls: list[str] = []

            def fake_download(url: str, dest: Path) -> None:
                download_calls.append(url)
                shutil.copyfile(fixture_zip, dest)

            with patch("soundpack_builder.pipeline.downloader.download_url", side_effect=fake_download):
                code = download_clips(
                    cfg,
                    manifest_path=manifest,
                    dry_run=False,
                    limit=0,
                    overwrite=True,
                    progress=False,
                    recommend_config=False,
                    skip_transcript=True,
                    whisper_model="tiny",
                    whisper_language=None,
                    whisper_device="auto",
                    whisper_compute_type="auto",
                    overwrite_recommended_config=False,
                    use_llm_classifier=False,
                    classifier_backend="zero-shot",
                    classifier_model="x",
                    classifier_weight=5.0,
                    speech_verification_enabled=False,
                )

            self.assertEqual(code, 0)
            self.assertEqual(len(download_calls), 1)
            self.assertTrue((root / "sounds" / "u" / "c" / "a.wav").is_file())
            self.assertTrue((root / "sounds" / "u" / "c" / "b.wav").is_file())


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

    def test_extract_from_zip_picks_member_by_preferred_stem(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            zip_path = temp_root / "pack.zip"
            downloads_dir = temp_root / "downloads"
            a = b"aaa"
            b = b"bbb"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("other/clip1.wav", a)
                zf.writestr("voices/403989.wav", b)

            extracted = extract_from_zip(
                zip_path,
                path_in_archive=None,
                temp_dir=downloads_dir,
                preferred_stem="403989",
            )
            self.assertEqual(extracted.read_bytes(), b)


class RiffWaveDetectionTest(unittest.TestCase):
    def test_is_riff_wave_true_for_minimal_header(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.wav"
            p.write_bytes(b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE")
            self.assertTrue(_is_riff_wave(p))

    def test_is_riff_wave_false_for_mp3_disguised_as_wav(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fake.wav"
            p.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00")  # typical MP3 tag start
            self.assertFalse(_is_riff_wave(p))


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
                {("warcraft", "orc-peon", "")},
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
            rep = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(rep["speechVerification"]["mode"], "skipped")
            self.assertTrue(rep["speechVerification"]["notAssessed"])

    @patch("soundpack_builder.pipeline.downloader.transcribe_with_whisper")
    @patch("soundpack_builder.pipeline.downloader.classify_hook_events")
    def test_recommended_config_excludes_non_lexical_transcripts(
        self, mock_classify: object, mock_whisper: object
    ) -> None:
        mock_classify.return_value = {}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = BuilderConfig(
                repo_root=root,
                manifests_dir=root / "manifests",
                configs_dir=root / "configs",
                sound_dir=root / "sounds",
            )
            pack_dir = cfg.sound_dir / "u" / "c"
            pack_dir.mkdir(parents=True, exist_ok=True)
            bad = pack_dir / "sfx.wav"
            good = pack_dir / "line.wav"
            bad.write_bytes(b"wav-data")
            good.write_bytes(b"wav-data")
            mock_whisper.return_value = {
                bad: "[music]",
                good: "I am a character line.",
            }

            result = _write_recommended_configs(
                cfg,
                {("u", "c", "")},
                skip_transcript=False,
                whisper_model="tiny",
                whisper_language="en",
                whisper_device="auto",
                whisper_compute_type="auto",
                overwrite=True,
                use_llm_classifier=False,
            )
            self.assertEqual(len(result), 1)
            self.assertTrue(result[0]["ok"])
            self.assertEqual(result[0]["speechVerification"]["filter"], "applied")
            self.assertEqual(len(result[0]["speechVerification"]["excludedClips"]), 1)
            self.assertEqual(result[0]["speechVerification"]["excludedClips"][0]["file"], "sfx.wav")

            cfg_json = json.loads((pack_dir / "sound-config.json").read_text(encoding="utf-8"))
            events_flat = []
            for _ev, v in cfg_json["events"].items():
                if isinstance(v, list):
                    events_flat.extend(v)
                else:
                    events_flat.append(v)
            self.assertNotIn("sfx.wav", events_flat)
            self.assertIn("line.wav", events_flat)

            rep = json.loads((pack_dir / "mapping-report.json").read_text(encoding="utf-8"))
            self.assertEqual(rep["speechVerification"]["eligibleCount"], 1)
            sfx_row = next(c for c in rep["clips"] if c["file"] == "sfx.wav")
            self.assertFalse(sfx_row["speechEligible"])

    @patch("soundpack_builder.pipeline.downloader.transcribe_with_whisper")
    def test_recommend_config_language_filter_skips_non_matching_wav_suffixes(
        self, mock_whisper: object
    ) -> None:
        mock_whisper.side_effect = lambda paths, **kwargs: {p: "line" for p in paths}

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = BuilderConfig(
                repo_root=root,
                manifests_dir=root / "manifests",
                configs_dir=root / "configs",
                sound_dir=root / "sounds",
            )
            pack_dir = cfg.sound_dir / "lotr" / "gandalf" / "pack"
            pack_dir.mkdir(parents=True)
            (pack_dir / "clip_ENG.wav").write_bytes(b"w")
            (pack_dir / "clip_DAN.wav").write_bytes(b"w")
            (pack_dir / "clip_FRE.wav").write_bytes(b"w")

            _write_recommended_configs(
                cfg,
                {("lotr", "gandalf", "pack")},
                skip_transcript=False,
                whisper_model="tiny",
                whisper_language="en",
                whisper_device="auto",
                whisper_compute_type="auto",
                overwrite=True,
                use_llm_classifier=False,
                language_filter_codes={"ENG"},
            )
            self.assertTrue(mock_whisper.called)
            passed = mock_whisper.call_args[0][0]
            names = sorted(p.name for p in passed)
            self.assertEqual(names, ["clip_ENG.wav"])

    @patch("soundpack_builder.pipeline.downloader.transcribe_with_whisper")
    def test_no_speech_eligible_writes_report_not_config(self, mock_whisper: object) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = BuilderConfig(
                repo_root=root,
                manifests_dir=root / "manifests",
                configs_dir=root / "configs",
                sound_dir=root / "sounds",
            )
            pack_dir = cfg.sound_dir / "x" / "y"
            pack_dir.mkdir(parents=True)
            only = pack_dir / "only.wav"
            only.write_bytes(b"w")
            mock_whisper.return_value = {only: "[music]"}

            result = _write_recommended_configs(
                cfg,
                {("x", "y", "")},
                skip_transcript=False,
                whisper_model="tiny",
                whisper_language="en",
                whisper_device="auto",
                whisper_compute_type="auto",
                overwrite=True,
                use_llm_classifier=False,
            )
            self.assertFalse(result[0]["ok"])
            self.assertIn("No speech-eligible", result[0]["error"])
            self.assertFalse((pack_dir / "sound-config.json").exists())
            self.assertTrue((pack_dir / "mapping-report.json").is_file())


class LanguageCodeInferenceTest(unittest.TestCase):
    def test_filename_suffix_takes_priority_over_embedded_lang_tokens(self) -> None:
        from soundpack_builder.core.language_codes import resolve_language_code

        self.assertEqual(resolve_language_code(None, "CLIP_ENG_DAN.wav"), "DAN")
        self.assertEqual(resolve_language_code(None, "DX_GANDALF_300LIVES_DAN.wav"), "DAN")
        self.assertEqual(resolve_language_code(None, "LINE_MEX.wav"), "MEX")


if __name__ == "__main__":
    unittest.main()
