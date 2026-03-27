#!/usr/bin/env python3
import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_CONFIG_PATH = PROJECT_ROOT / ".cursor" / "hooks" / "sound-config.json"
USER_CONFIG_PATH = Path.home() / ".cursor" / "sound-hooks.json"


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
            if isinstance(payload, dict):
                return payload
    except Exception:
        pass
    return {}


def _merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _as_list(value: Any) -> List[str]:
    if isinstance(value, str):
        trimmed = value.strip()
        return [trimmed] if trimmed else []
    if isinstance(value, list):
        result: List[str] = []
        for item in value:
            if isinstance(item, str):
                trimmed = item.strip()
                if trimmed:
                    result.append(trimmed)
        return result
    return []


def _resolve_sound_path(candidate: str, sound_root: str, sound_pack: str) -> Path:
    path_obj = Path(candidate).expanduser()
    if path_obj.is_absolute():
        return path_obj

    if sound_root:
        root_obj = Path(sound_root).expanduser()
        if not root_obj.is_absolute():
            root_obj = (PROJECT_ROOT / root_obj).resolve()
        if sound_pack:
            return (root_obj / sound_pack / path_obj).resolve()
        return (root_obj / path_obj).resolve()

    if sound_pack:
        return (PROJECT_ROOT / "sounds" / sound_pack / path_obj).resolve()

    return (PROJECT_ROOT / path_obj).resolve()


def _play_background(sound_path: Path) -> None:
    if sys.platform == "win32":
        escaped_path = str(sound_path).replace("'", "''")
        powershell = [
            "powershell",
            "-NoProfile",
            "-WindowStyle",
            "Hidden",
            "-Command",
            (
                "Add-Type -AssemblyName presentationCore; "
                "$p = New-Object System.Windows.Media.MediaPlayer; "
                f"$p.Open([uri]'{escaped_path}'); "
                "$p.Volume = 1.0; "
                "$p.Play(); "
                "Start-Sleep -Milliseconds 1200;"
            ),
        ]
        subprocess.Popen(
            powershell,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS,
        )
        return

    if sys.platform == "darwin":
        subprocess.Popen(
            ["afplay", str(sound_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return

    for command in (["paplay", str(sound_path)], ["aplay", str(sound_path)]):
        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return
        except FileNotFoundError:
            continue

    raise RuntimeError("No supported Linux sound player found (paplay/aplay).")


def _load_config() -> Dict[str, Any]:
    project = _read_json(PROJECT_CONFIG_PATH)
    user = _read_json(USER_CONFIG_PATH)
    return _merge_dict(project, user)


def _pick_sound(event_name: str, config: Dict[str, Any]) -> Path:
    events = config.get("events", {})
    if not isinstance(events, dict):
        raise RuntimeError("Invalid config: 'events' must be an object.")

    sound_choices = _as_list(events.get(event_name))
    if not sound_choices:
        raise RuntimeError(f"No sound configured for event '{event_name}'.")

    choice = random.choice(sound_choices)
    return _resolve_sound_path(
        choice,
        str(config.get("soundRoot", "")).strip(),
        str(config.get("soundPack", "")).strip(),
    )


def _read_stdin_payload() -> Dict[str, Any]:
    # Cursor hook payloads are available on stdin during hook execution.
    # Avoid blocking for manual CLI tests where stdin may not close.
    if sys.stdin.isatty():
        return {}
    try:
        text = sys.stdin.read()
        payload = json.loads(text) if text.strip() else {}
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}


def main() -> int:
    event_name = sys.argv[1] if len(sys.argv) > 1 else ""
    is_test_mode = False
    if not event_name:
        print(json.dumps({"ok": True, "message": "No event arg; skipping sound"}))
        return 0

    if event_name == "--test" and len(sys.argv) > 2:
        is_test_mode = True
        event_name = sys.argv[2]

    if not is_test_mode:
        _ = _read_stdin_payload()
    config = _load_config()
    if not bool(config.get("enabled", True)):
        print(json.dumps({"ok": True, "message": "Sound hooks disabled"}))
        return 0

    try:
        sound_path = _pick_sound(event_name, config)
        if not sound_path.exists():
            raise RuntimeError(f"Sound file does not exist: {sound_path}")
        _play_background(sound_path)
        print(json.dumps({"ok": True, "event": event_name, "path": str(sound_path)}))
    except Exception as error:
        # Hooks should not block agent flow for sound issues.
        print(json.dumps({"ok": True, "event": event_name, "warning": str(error)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
