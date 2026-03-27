#!/usr/bin/env python3
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

if sys.platform == "win32":
    import winsound


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_CONFIG_PATH = PROJECT_ROOT / ".cursor" / "hooks" / "sound-config.json"
USER_CONFIG_PATH = Path.home() / ".cursor" / "sound-hooks.json"
DEBOUNCE_STATE_DIR = PROJECT_ROOT / ".cursor" / "hooks" / ".debounce-state"


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


def _resolve_sound_path(
    candidate: str, sound_root: str, sound_pack: str, sound_subdir: str
) -> Path:
    path_obj = Path(candidate).expanduser()
    if path_obj.is_absolute():
        return path_obj

    if sound_root:
        root_obj = Path(sound_root).expanduser()
        if not root_obj.is_absolute():
            root_obj = (PROJECT_ROOT / root_obj).resolve()
        if sound_pack:
            if sound_subdir and len(path_obj.parts) == 1:
                return (root_obj / sound_pack / sound_subdir / path_obj).resolve()
            return (root_obj / sound_pack / path_obj).resolve()
        return (root_obj / path_obj).resolve()

    if sound_pack:
        if sound_subdir and len(path_obj.parts) == 1:
            return (PROJECT_ROOT / "sounds" / sound_pack / sound_subdir / path_obj).resolve()
        return (PROJECT_ROOT / "sounds" / sound_pack / path_obj).resolve()

    return (PROJECT_ROOT / path_obj).resolve()


def _event_cache_key(event_name: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", event_name).strip("-")
    return safe_name or "unknown-event"


def _as_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
        if parsed >= 0:
            return parsed
    except (TypeError, ValueError):
        pass
    return default


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _should_play_event(event_name: str, debounce_ms: int) -> Tuple[bool, str]:
    if debounce_ms <= 0:
        return True, "disabled"

    DEBOUNCE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    key = _event_cache_key(event_name)
    state_path = DEBOUNCE_STATE_DIR / f"{key}.json"
    lock_path = DEBOUNCE_STATE_DIR / f"{key}.lock"
    now_ms = int(time.time() * 1000)

    lock_fd = None
    lock_deadline = time.time() + 0.2
    while True:
        try:
            lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                age_ms = now_ms - int(lock_path.stat().st_mtime * 1000)
                if age_ms > 10_000:
                    _safe_unlink(lock_path)
                    continue
            except Exception:
                pass
            if time.time() >= lock_deadline:
                return False, "busy"
            time.sleep(0.005)

    try:
        if lock_fd is not None:
            os.write(lock_fd, str(os.getpid()).encode("ascii", errors="ignore"))
            os.close(lock_fd)
            lock_fd = None

        last_played_ms = 0
        if state_path.exists():
            state_data = _read_json(state_path)
            last_played_ms = _as_positive_int(state_data.get("lastPlayedMs"), 0)

        if now_ms - last_played_ms < debounce_ms:
            return False, "debounced"

        temp_path = DEBOUNCE_STATE_DIR / f"{key}.tmp-{os.getpid()}"
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump({"lastPlayedMs": now_ms, "event": event_name}, handle)
        temp_path.replace(state_path)
        return True, "accepted"
    finally:
        try:
            if lock_fd is not None:
                os.close(lock_fd)
        except Exception:
            pass
        _safe_unlink(lock_path)


def _play_background(sound_path: Path) -> None:
    if sys.platform == "win32":
        # Most reliable on Windows for local WAV playback in short-lived hooks.
        winsound.PlaySound(str(sound_path), winsound.SND_FILENAME)
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
        str(config.get("soundSubdir", "")).strip(),
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

    debounce_ms = _as_positive_int(config.get("debounceMs"), 500)
    should_play, dedupe_reason = _should_play_event(event_name, debounce_ms)
    if not should_play:
        print(
            json.dumps(
                {
                    "ok": True,
                    "event": event_name,
                    "message": f"Skipped duplicate hook event ({dedupe_reason})",
                    "debounceMs": debounce_ms,
                }
            )
        )
        return 0

    try:
        sound_path = _pick_sound(event_name, config)
        if not sound_path.exists():
            raise RuntimeError(f"Sound file does not exist: {sound_path}")
        _play_background(sound_path)
        print(
            json.dumps(
                {
                    "ok": True,
                    "event": event_name,
                    "path": str(sound_path),
                    "debounceMs": debounce_ms,
                }
            )
        )
    except Exception as error:
        # Hooks should not block agent flow for sound issues.
        print(json.dumps({"ok": True, "event": event_name, "warning": str(error)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
