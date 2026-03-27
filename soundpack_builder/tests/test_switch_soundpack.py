import importlib.util
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch


def _load_switch_module():
    script_path = (
        Path(__file__).resolve().parents[2] / ".cursor" / "hooks" / "switch-soundpack.py"
    )
    spec = importlib.util.spec_from_file_location("switch_soundpack", script_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SwitchSoundpackTest(unittest.TestCase):
    def test_prefers_recommended_pack_config(self) -> None:
        mod = _load_switch_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_dir = root / "configs" / "sound-config"
            sounds_dir = root / "sounds" / "warcraft" / "orc-peon"
            active = root / ".cursor" / "hooks" / "sound-config.json"
            source_dir.mkdir(parents=True, exist_ok=True)
            sounds_dir.mkdir(parents=True, exist_ok=True)

            legacy_payload = {"soundPack": "warcraft", "soundSubdir": "orc-peon", "events": {"stop": "a.wav"}}
            recommended_payload = {
                "soundPack": "warcraft",
                "soundSubdir": "orc-peon",
                "events": {"stop": "recommended.wav"},
            }
            (source_dir / "warcraft-orc-peon.json").write_text(
                json.dumps(legacy_payload), encoding="utf-8"
            )
            (sounds_dir / "sound-config.json").write_text(
                json.dumps(recommended_payload), encoding="utf-8"
            )

            with patch.object(mod, "SOURCE_CONFIG_DIR", source_dir), patch.object(
                mod, "SOUNDS_DIR", root / "sounds"
            ), patch.object(mod, "ACTIVE_CONFIG_PATH", active):
                rc = mod._activate("warcraft-orc-peon")
                self.assertEqual(rc, 0)
                activated = json.loads(active.read_text(encoding="utf-8"))
                self.assertEqual(activated["events"]["stop"], "recommended.wav")

    def test_falls_back_to_legacy_when_recommended_missing(self) -> None:
        mod = _load_switch_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_dir = root / "configs" / "sound-config"
            active = root / ".cursor" / "hooks" / "sound-config.json"
            source_dir.mkdir(parents=True, exist_ok=True)
            legacy_payload = {"soundPack": "warcraft", "soundSubdir": "orc-peon", "events": {"stop": "legacy.wav"}}
            (source_dir / "warcraft-orc-peon.json").write_text(
                json.dumps(legacy_payload), encoding="utf-8"
            )

            stderr = StringIO()
            with patch.object(mod, "SOURCE_CONFIG_DIR", source_dir), patch.object(
                mod, "SOUNDS_DIR", root / "sounds"
            ), patch.object(mod, "ACTIVE_CONFIG_PATH", active), patch("sys.stderr", stderr):
                rc = mod._activate("warcraft-orc-peon")
                self.assertEqual(rc, 0)
                self.assertIn("falling back to legacy template", stderr.getvalue().lower())
                activated = json.loads(active.read_text(encoding="utf-8"))
                self.assertEqual(activated["events"]["stop"], "legacy.wav")


if __name__ == "__main__":
    unittest.main()
