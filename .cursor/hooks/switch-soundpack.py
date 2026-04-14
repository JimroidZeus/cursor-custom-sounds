#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CONFIG_DIR = PROJECT_ROOT / "configs" / "sound-config"
ACTIVE_CONFIG_PATH = PROJECT_ROOT / ".cursor" / "hooks" / "sound-config.json"
SOUNDS_DIR = PROJECT_ROOT / "sounds"
HOOK_CANDIDATES_PATH = PROJECT_ROOT / "manifests" / "universe-character-hook-candidates.json"


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
            if isinstance(payload, dict):
                return payload
    except Exception:
        return {}
    return {}


def _slug_from_path_parts(parts: List[str]) -> str:
    return "-".join(p.strip() for p in parts if p and p.strip())


def _slug_from_active_payload(payload: Dict[str, Any]) -> str:
    sound_pack = str(payload.get("soundPack", "")).strip()
    if not sound_pack:
        return ""
    sound_subdir = str(payload.get("soundSubdir", "")).strip()
    if not sound_subdir:
        return sound_pack
    parts = [sound_pack] + [s for s in sound_subdir.split("/") if s.strip()]
    return _slug_from_path_parts(parts)


def _discover_installed_pack_paths() -> Dict[str, Path]:
    """Map canonical slug -> path to that pack's sound-config.json."""
    if not SOUNDS_DIR.is_dir():
        return {}
    out: Dict[str, Path] = {}
    for config_path in sorted(SOUNDS_DIR.glob("**/sound-config.json")):
        try:
            rel = config_path.parent.relative_to(SOUNDS_DIR)
        except ValueError:
            continue
        slug = _slug_from_path_parts(list(rel.parts))
        if not slug:
            continue
        out[slug] = config_path
    return out


@lru_cache(maxsize=1)
def _hook_characters_by_universe_character() -> Dict[Tuple[str, str], Dict[str, Any]]:
    payload = _read_json(HOOK_CANDIDATES_PATH)
    chars = payload.get("characters")
    if not isinstance(chars, list):
        return {}
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for item in chars:
        if not isinstance(item, dict):
            continue
        u = str(item.get("universe", "")).strip()
        c = str(item.get("character", "")).strip()
        if u and c:
            out[(u, c)] = item
    return out


def _words_slug(label: str) -> str:
    """Approximate slug from a human label (e.g. 'Batman (LEGO Dimensions)' -> batman-lego-dimensions)."""
    words = re.findall(r"[a-z0-9]+", label.lower())
    return "-".join(words) if words else ""


def _display_name_for_pack(
    sound_config_path: Path,
    payload: Dict[str, Any],
) -> str:
    parts = _pack_path_parts_from_payload(payload)
    if not parts:
        try:
            rel = sound_config_path.parent.relative_to(SOUNDS_DIR)
            parts = list(rel.parts)
        except ValueError:
            parts = []
    if not parts:
        return sound_config_path.parent.name
    universe = parts[0]
    if len(parts) == 1:
        return _title_slug_segment(universe)

    character = parts[1]
    pack_tail = parts[2:] if len(parts) > 2 else []
    meta = _hook_characters_by_universe_character().get((universe, character))
    base_name = (
        str(meta.get("displayName", "")).strip() if meta else ""
    ) or _title_slug_segment(character)

    if not pack_tail:
        return base_name

    pack_folder = pack_tail[-1]
    label_suffix = _match_candidate_label_for_pack_folder(meta, pack_folder)
    if label_suffix:
        return f"{base_name} - {label_suffix}"
    return f"{base_name} - {_title_slug_segment(pack_folder)}"


def _pack_path_parts_from_payload(payload: Dict[str, Any]) -> List[str]:
    sound_pack = str(payload.get("soundPack", "")).strip()
    if not sound_pack:
        return []
    sound_subdir = str(payload.get("soundSubdir", "")).strip()
    if not sound_subdir:
        return [sound_pack]
    return [sound_pack] + [s for s in sound_subdir.split("/") if s.strip()]


def _strip_trailing_content_hash(segment: str) -> str:
    """Remove trailing -<hex> suffix used in some pack folder names."""
    return re.sub(r"-[a-f0-9]{6,}$", "", segment, flags=re.IGNORECASE)


def _match_candidate_label_for_pack_folder(
    meta: Optional[Dict[str, Any]],
    pack_folder: str,
) -> str:
    if not meta:
        return ""
    links = meta.get("candidateLinks")
    if not isinstance(links, list):
        return ""
    pf = _strip_trailing_content_hash(pack_folder.lower().strip())
    for link in links:
        if not isinstance(link, dict):
            continue
        label = str(link.get("label", "")).strip()
        if not label:
            continue
        slug = _words_slug(label)
        if not slug:
            continue
        if slug == pf:
            return label
        if pf.startswith(slug + "-") or pf.startswith(slug):
            return label
        if slug.startswith(pf + "-") or slug.startswith(pf):
            return label
    return ""


def _title_slug_segment(segment: str) -> str:
    s = segment.replace("-", " ").replace("_", " ")
    return s.title() if s else segment


def _list_entries() -> List[Tuple[str, Path, str]]:
    """Sorted list of (slug, sound_config_path, display_name)."""
    discovered = _discover_installed_pack_paths()
    rows: List[Tuple[str, Path, str]] = []
    for slug, path in discovered.items():
        payload = _read_json(path)
        label = _display_name_for_pack(path, payload)
        rows.append((slug, path, label))
    rows.sort(key=lambda t: (t[2].lower(), t[0]))
    return rows


def _print_available(current_pack_slug: str) -> None:
    entries = _list_entries()
    if not entries:
        print("No installed soundpacks found under sounds/ (look for sounds/**/sound-config.json).")
        print("Download or build a pack first; configs/sound-config/*.json are templates only.")
        return

    print("Installed soundpacks (under sounds/):")
    for slug, _path, display in entries:
        marker = "*" if slug == current_pack_slug else " "
        print(f" {marker} {display}")
        print(f"     {slug}")


def _current_soundpack_slug() -> str:
    payload = _read_json(ACTIVE_CONFIG_PATH)
    return _slug_from_active_payload(payload)


def _activate_from_installed(slug: str, installed: Dict[str, Path]) -> Optional[int]:
    path = installed.get(slug)
    if not path:
        return None
    ACTIVE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, ACTIVE_CONFIG_PATH)
    print(f"Activated soundpack: {slug}")
    print(f"Source: installed pack ({path})")
    print(f"Wrote: {ACTIVE_CONFIG_PATH}")
    return 0


def _activate_legacy(slug: str) -> int:
    legacy_path = SOURCE_CONFIG_DIR / f"{slug}.json"
    if not legacy_path.exists():
        print(
            f"Soundpack '{slug}' not found (no sounds/**/sound-config.json slug match "
            f"and no configs/sound-config/{slug}.json).",
            file=sys.stderr,
        )
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
            f"Recommended config not found under sounds/, using legacy template: {legacy_path}",
            file=sys.stderr,
        )

    ACTIVE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, ACTIVE_CONFIG_PATH)
    print(f"Activated soundpack: {slug}")
    print(f"Source: {source_label} ({source_path})")
    print(f"Wrote: {ACTIVE_CONFIG_PATH}")
    return 0


def _activate(slug: str) -> int:
    installed = _discover_installed_pack_paths()
    direct = _activate_from_installed(slug, installed)
    if direct is not None:
        return direct
    return _activate_legacy(slug)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List installed soundpacks and activate pack configs from sounds/ when available."
    )
    parser.add_argument(
        "soundpack",
        nargs="?",
        help="Soundpack slug (see --list; e.g. warcraft-orc-peon or nested segments joined with '-')",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List installed soundpacks and mark the active one.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.list:
        _print_available(_current_soundpack_slug())
        return 0

    if not args.soundpack:
        parser.print_help()
        return 1

    return _activate(args.soundpack)


if __name__ == "__main__":
    raise SystemExit(main())
