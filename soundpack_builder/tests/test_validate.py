import tempfile
import unittest
import wave
from pathlib import Path

from soundpack_builder.audio.audio_duration import validate_wav_durations


def _write_silent_wav(path: Path, *, seconds: float, sample_rate: int = 8000) -> None:
    frames = int(seconds * sample_rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frames)


class WavDurationValidationTest(unittest.TestCase):
    def test_reports_warning_and_failure_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            sound_dir = Path(td) / "sounds"
            _write_silent_wav(sound_dir / "pack" / "short.wav", seconds=3.0)
            _write_silent_wav(sound_dir / "pack" / "warn.wav", seconds=11.0)
            _write_silent_wav(sound_dir / "pack" / "too-long.wav", seconds=16.0)

            ok, payload = validate_wav_durations(
                sound_dir,
                max_seconds=15.0,
                warn_seconds=10.0,
            )

            self.assertFalse(ok)
            self.assertEqual(payload["wavFilesChecked"], 3)
            self.assertEqual(len(payload["warnings"]), 1)
            self.assertEqual(len(payload["failures"]), 1)
            self.assertIn("warn.wav", payload["warnings"][0]["path"])
            self.assertIn("too-long.wav", payload["failures"][0]["path"])


if __name__ == "__main__":
    unittest.main()
