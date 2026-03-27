#!/usr/bin/env python3
"""
Install sound packs and hook scripts into ~/.cursor/cursor-custom-sounds (default)
and register user-level Cursor hooks in ~/.cursor/hooks.json.

Layout after install matches this repo so Path(__file__).resolve().parents[2] in
play-sound.py / switch-soundpack.py resolves to the install root.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from subprocess import list2cmdline
from typing import Iterable, Set

REPO_ROOT = Path(__file__).resolve().parent

DEFAULT_INSTALL_ROOT = Path.home() / ".cursor" / "cursor-custom-sounds"

HOOK_EVENTS = (
    "beforeSubmitPrompt",
    "afterAgentThought",
    "afterAgentResponse",
    "preToolUse",
    "postToolUse",
    "postToolUseFailure",
    "stop",
)

IGNORE_DIR_NAMES: Set[str] = {"__pycache__", ".debounce-state"}


def _ignore_copy(path: str, names: Iterable[str]) -> Set[str]:
    ignored: Set[str] = set()
    base = Path(path)
    for name in names:
        if name in IGNORE_DIR_NAMES:
            ignored.add(name)
            continue
        if name.endswith(".pyc"):
            ignored.add(name)
            continue
        if base.name == "hooks" and name == ".debounce-state":
            ignored.add(name)
    return ignored


def _copy_tree(src: Path, dst: Path, dry_run: bool) -> None:
    if dry_run:
        print(f"Would copy: {src} -> {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_ignore_copy)


def _copy_file(src: Path, dst: Path, dry_run: bool) -> None:
    if dry_run:
        print(f"Would copy file: {src} -> {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _merge_user_hooks(
    existing: dict, install_root: Path, python_exe: Path
) -> dict:
    play_script = install_root / ".cursor" / "hooks" / "play-sound.py"
    new_hooks: dict = {}
    for event in HOOK_EVENTS:
        cmd = list2cmdline([str(python_exe), str(play_script), event])
        new_hooks[event] = [{"command": cmd}]

    merged = dict(existing) if isinstance(existing, dict) else {}
    merged.setdefault("version", 1)
    hooks = dict(merged.get("hooks", {})) if isinstance(merged.get("hooks"), dict) else {}
    hooks.update(new_hooks)
    merged["hooks"] = hooks
    return merged


def _backup(path: Path, dry_run: bool) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak.{stamp}")
    if dry_run:
        print(f"Would backup: {path} -> {backup_path}")
        return backup_path
    shutil.copy2(path, backup_path)
    print(f"Backed up existing file to: {backup_path}")
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install cursor-custom-sounds into ~/.cursor and register user hooks."
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_INSTALL_ROOT,
        help=f"Install root (default: {DEFAULT_INSTALL_ROOT})",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable to invoke from hooks.json (default: sys.executable)",
    )
    parser.add_argument(
        "--skip-sounds",
        action="store_true",
        help="Do not copy the sounds/ tree (configs and scripts only).",
    )
    parser.add_argument(
        "--no-hooks-json",
        action="store_true",
        help="Do not write or merge ~/.cursor/hooks.json.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without copying files or writing hooks.json.",
    )
    args = parser.parse_args()

    install_root: Path = args.dest.expanduser().resolve()
    python_exe: Path = args.python.expanduser().resolve()

    if not REPO_ROOT.is_dir():
        print("Could not locate repository root.", file=sys.stderr)
        return 1

    required = [
        REPO_ROOT / ".cursor" / "hooks" / "play-sound.py",
        REPO_ROOT / ".cursor" / "hooks" / "switch-soundpack.py",
        REPO_ROOT / ".cursor" / "hooks" / "sound-config.json",
        REPO_ROOT / "configs" / "sound-config",
    ]
    for path in required:
        if not path.exists():
            print(f"Missing required path in repo: {path}", file=sys.stderr)
            return 1

    print(f"Install root: {install_root}")
    print(f"Python for hooks: {python_exe}")

    # Mirror repo layout under install_root
    _copy_tree(REPO_ROOT / "configs", install_root / "configs", args.dry_run)
    if not args.skip_sounds:
        sounds_src = REPO_ROOT / "sounds"
        if sounds_src.is_dir():
            _copy_tree(sounds_src, install_root / "sounds", args.dry_run)
        else:
            print("No sounds/ directory in repo; skipping.", file=sys.stderr)
    else:
        print("Skipping sounds/ (--skip-sounds).")

    hooks_src = REPO_ROOT / ".cursor" / "hooks"
    hooks_dst = install_root / ".cursor" / "hooks"
    for name in ("play-sound.py", "switch-soundpack.py", "sound-config.json"):
        _copy_file(hooks_src / name, hooks_dst / name, args.dry_run)

    user_hooks_path = Path.home() / ".cursor" / "hooks.json"
    if not args.no_hooks_json:
        existing: dict = {}
        if user_hooks_path.exists():
            try:
                text = user_hooks_path.read_text(encoding="utf-8")
                loaded = json.loads(text) if text.strip() else {}
                if isinstance(loaded, dict):
                    existing = loaded
            except (OSError, json.JSONDecodeError) as error:
                print(f"Warning: could not read {user_hooks_path}: {error}", file=sys.stderr)
        if user_hooks_path.exists() and not args.dry_run:
            _backup(user_hooks_path, dry_run=False)
        merged = _merge_user_hooks(existing, install_root, python_exe)
        if args.dry_run:
            print(f"Would write {user_hooks_path}:")
            print(json.dumps(merged, indent=2))
        else:
            user_hooks_path.parent.mkdir(parents=True, exist_ok=True)
            user_hooks_path.write_text(
                json.dumps(merged, indent=2) + "\n", encoding="utf-8"
            )
            print(f"Wrote: {user_hooks_path}")
    else:
        print("Skipped ~/.cursor/hooks.json (--no-hooks-json).")
        print(
            "Add commands manually, e.g.:",
            list2cmdline(
                [
                    str(python_exe),
                    str(install_root / ".cursor" / "hooks" / "play-sound.py"),
                    "afterAgentResponse",
                ]
            ),
        )

    if not args.dry_run:
        print("\nNext steps:")
        print(
            f"  List packs:  {list2cmdline([str(python_exe), str(install_root / '.cursor' / 'hooks' / 'switch-soundpack.py'), '--list'])}"
        )
        print(
            f"  Activate:    {list2cmdline([str(python_exe), str(install_root / '.cursor' / 'hooks' / 'switch-soundpack.py'), '<slug>'])}"
        )
        print(
            f"  Test sound:  {list2cmdline([str(python_exe), str(install_root / '.cursor' / 'hooks' / 'play-sound.py'), '--test', 'afterAgentResponse'])}"
        )
        print("  Restart Cursor so user hooks are picked up.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
