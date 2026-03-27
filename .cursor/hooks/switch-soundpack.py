#!/usr/bin/env python3
import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CONFIG_DIR = PROJECT_ROOT / "configs" / "sound-config"
ACTIVE_CONFIG_PATH = PROJECT_ROOT / ".cursor" / "hooks" / "sound-config.json"
SOUNDS_DIR = PROJECT_ROOT / "sounds"


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
            if isinstance(payload, dict):
                return payload
    except Exception:
        return {}
    return {}


def _available_configs() -> List[Path]:
    if not SOURCE_CONFIG_DIR.exists():
        return []
    return sorted(SOURCE_CONFIG_DIR.glob("*.json"))


def _print_available(configs: List[Path], current_pack_slug: str) -> None:
    if not configs:
        print("No soundpack configs found in configs/sound-config/")
        return

    print("Available soundpacks:")
    for config_path in configs:
        slug = config_path.stem
        marker = "*" if slug == current_pack_slug else " "
        print(f" {marker} {slug}")


def _current_soundpack_slug() -> str:
    payload = _read_json(ACTIVE_CONFIG_PATH)
    sound_pack = str(payload.get("soundPack", "")).strip()
    sound_subdir = str(payload.get("soundSubdir", "")).strip()
    if not sound_pack:
        return ""
    if sound_subdir:
        return f"{sound_pack}-{sound_subdir}"

    # Template files follow "<soundPack>-<character>.json", where event paths
    # include "<character>/...". Infer slug so list mode can mark active config.
    events = payload.get("events", {})
    if not isinstance(events, dict):
        return sound_pack
    before_submit = events.get("beforeSubmitPrompt", [])
    first_entry = ""
    if isinstance(before_submit, list) and before_submit and isinstance(before_submit[0], str):
        first_entry = before_submit[0]
    elif isinstance(before_submit, str):
        first_entry = before_submit
    character = first_entry.split("/", 1)[0].strip() if "/" in first_entry else ""
    if character:
        return f"{sound_pack}-{character}"
    return sound_pack


def _activate(slug: str) -> int:
    legacy_path = SOURCE_CONFIG_DIR / f"{slug}.json"
    if not legacy_path.exists():
        print(f"Soundpack '{slug}' not found in configs/sound-config/", file=sys.stderr)
        return 1

    legacy_payload = _read_json(legacy_path)
    if not legacy_payload or "events" not in legacy_payload:
        print(f"Invalid soundpack config: {legacy_path}", file=sys.stderr)
        return 1

    sound_pack = str(legacy_payload.get("soundPack", "")).strip()
    sound_subdir = str(legacy_payload.get("soundSubdir", "")).strip()
    recommended_path = SOUNDS_DIR / sound_pack / sound_subdir / "sound-config.json"

    source_path = legacy_path
    source_label = "legacy template"
    if sound_pack and sound_subdir and recommended_path.exists():
        recommended_payload = _read_json(recommended_path)
        if recommended_payload and "events" in recommended_payload:
            source_path = recommended_path
            source_label = "recommended pack config"
        else:
            print(
                f"Recommended config invalid, falling back to legacy template: {recommended_path}",
                file=sys.stderr,
            )
    else:
        print(
            f"Recommended config not found, falling back to legacy template: {legacy_path}",
            file=sys.stderr,
        )

    ACTIVE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, ACTIVE_CONFIG_PATH)
    print(f"Activated soundpack: {slug}")
    print(f"Source: {source_label} ({source_path})")
    print(f"Wrote: {ACTIVE_CONFIG_PATH}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List soundpacks and activate recommended pack configs when available."
    )
    parser.add_argument(
        "soundpack",
        nargs="?",
        help="Soundpack slug (for example: warcraft-orc-peon)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available soundpacks and mark the active one.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.list:
        _print_available(_available_configs(), _current_soundpack_slug())
        return 0

    if not args.soundpack:
        parser.print_help()
        return 1

    return _activate(args.soundpack)


if __name__ == "__main__":
    raise SystemExit(main())
