import importlib.util
import json
import sys
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
                self.assertIn("using legacy template", stderr.getvalue().lower())
                activated = json.loads(active.read_text(encoding="utf-8"))
                self.assertEqual(activated["events"]["stop"], "legacy.wav")

    def test_activate_nested_installed_slug(self) -> None:
        mod = _load_switch_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pack = root / "sounds" / "batman" / "batman-animated" / "batman-lego-dimensions"
            active = root / ".cursor" / "hooks" / "sound-config.json"
            pack.mkdir(parents=True, exist_ok=True)
            nested_payload = {
                "soundPack": "batman",
                "soundSubdir": "batman-animated/batman-lego-dimensions",
                "events": {"stop": "nested.wav"},
            }
            (pack / "sound-config.json").write_text(json.dumps(nested_payload), encoding="utf-8")

            with patch.object(mod, "SOUNDS_DIR", root / "sounds"), patch.object(
                mod, "ACTIVE_CONFIG_PATH", active
            ):
                rc = mod._activate("batman-batman-animated-batman-lego-dimensions")
                self.assertEqual(rc, 0)
                activated = json.loads(active.read_text(encoding="utf-8"))
                self.assertEqual(activated["events"]["stop"], "nested.wav")

    def test_list_only_installed_and_marks_active(self) -> None:
        mod = _load_switch_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sounds = root / "sounds"
            active = root / ".cursor" / "hooks" / "sound-config.json"
            (sounds / "u" / "c").mkdir(parents=True, exist_ok=True)
            (sounds / "u" / "c" / "sound-config.json").write_text(
                json.dumps(
                    {
                        "soundPack": "u",
                        "soundSubdir": "c",
                        "events": {"stop": "a.wav"},
                    }
                ),
                encoding="utf-8",
            )
            active.parent.mkdir(parents=True, exist_ok=True)
            active.write_text(
                json.dumps(
                    {
                        "soundPack": "u",
                        "soundSubdir": "c",
                        "events": {"stop": "a.wav"},
                    }
                ),
                encoding="utf-8",
            )
            manifest = {
                "characters": [
                    {
                        "universe": "u",
                        "character": "c",
                        "displayName": "Display From Manifest",
                        "candidateLinks": [],
                    }
                ]
            }
            man_path = root / "hook-candidates.json"
            man_path.write_text(json.dumps(manifest), encoding="utf-8")

            out = StringIO()
            mod._hook_characters_by_universe_character.cache_clear()
            with patch.object(mod, "SOUNDS_DIR", sounds), patch.object(
                mod, "ACTIVE_CONFIG_PATH", active
            ), patch.object(mod, "HOOK_CANDIDATES_PATH", man_path), patch.object(
                sys, "argv", ["switch-soundpack.py", "--list"]
            ):
                with patch("sys.stdout", out):
                    rc = mod.main()
            self.assertEqual(rc, 0)
            text = out.getvalue()
            self.assertIn("u-c", text)
            self.assertIn("Display From Manifest", text)
            self.assertIn("*", text)

    def test_list_empty_sounds_message(self) -> None:
        mod = _load_switch_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sounds = root / "sounds"
            sounds.mkdir(parents=True, exist_ok=True)
            active = root / ".cursor" / "hooks" / "sound-config.json"
            out = StringIO()
            with patch.object(mod, "SOUNDS_DIR", sounds), patch.object(
                mod, "ACTIVE_CONFIG_PATH", active
            ), patch.object(sys, "argv", ["switch-soundpack.py", "--list"]):
                with patch("sys.stdout", out):
                    rc = mod.main()
            self.assertEqual(rc, 0)
            self.assertIn("No installed soundpacks", out.getvalue())


if __name__ == "__main__":
    unittest.main()
