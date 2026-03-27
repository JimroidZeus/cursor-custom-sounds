"""Generate per-character Cursor hook sound config templates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Optional

from .config import BuilderConfig, add_output_path_args, build_config_from_args

TIER1_CHARACTERS = [
    {"universe": "warcraft", "character": "orc-peon"},
    {"universe": "team-fortress-2", "character": "demoman"},
    {"universe": "team-fortress-2", "character": "scout"},
    {"universe": "dragon-ball-z", "character": "goku"},
    {"universe": "dragon-ball-z", "character": "krillin"},
    {"universe": "one-piece", "character": "luffy"},
    {"universe": "futurama", "character": "bender"},
    {"universe": "spongebob", "character": "mr-krabs"},
    {"universe": "star-wars", "character": "c-3po"},
    {"universe": "disney", "character": "genie"},
]


EVENT_FILES = {
    "beforeSubmitPrompt": ["beforeSubmitPrompt_1.wav", "beforeSubmitPrompt_2.wav"],
    "afterAgentThought": ["afterAgentThought_1.wav", "afterAgentThought_2.wav"],
    "afterAgentResponse": ["afterAgentResponse_1.wav", "afterAgentResponse_2.wav"],
    "preToolUse": ["preToolUse.wav"],
    "postToolUse": ["postToolUse.wav"],
    "postToolUseFailure": ["postToolUseFailure.wav"],
    "stop": ["stop.wav"],
}

TARGET_TO_EVENT = {
    "beforeSubmitPrompt_1.wav": "beforeSubmitPrompt",
    "beforeSubmitPrompt_2.wav": "beforeSubmitPrompt",
    "afterAgentThought_1.wav": "afterAgentThought",
    "afterAgentThought_2.wav": "afterAgentThought",
    "afterAgentResponse_1.wav": "afterAgentResponse",
    "afterAgentResponse_2.wav": "afterAgentResponse",
    "preToolUse.wav": "preToolUse",
    "postToolUse.wav": "postToolUse",
    "postToolUseFailure.wav": "postToolUseFailure",
    "stop.wav": "stop",
}


def _manifest_event_map(cfg: BuilderConfig) -> Dict[tuple[str, str], dict]:
    manifest_path = cfg.manifests_dir / "tier1-approved.json"
    if not manifest_path.exists():
        return {}
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return {}
    out: Dict[tuple[str, str], Dict[str, list[str]]] = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        universe = str(item.get("universe", "")).strip()
        character = str(item.get("character", "")).strip()
        if not universe or not character:
            continue
        event_name = str(item.get("event", "")).strip()
        if not event_name:
            event_name = TARGET_TO_EVENT.get(str(item.get("targetFile", "")).strip(), "")
        if not event_name:
            continue
        path_in_archive = str(item.get("pathInArchive") or item.get("path_in_archive") or "").strip()
        if path_in_archive:
            filename = Path(path_in_archive).name
        else:
            url = str(item.get("url", "")).strip()
            filename = Path(url.split("?", 1)[0]).name
        if not filename:
            continue
        stem = Path(filename).stem
        wav_name = f"{stem}.wav"
        event_map = out.setdefault((universe, character), {})
        event_map.setdefault(event_name, []).append(wav_name)
    return out


def make_template(universe: str, character: str, event_map: Optional[dict] = None) -> dict:
    events = {}
    for event_name, fallback_files in EVENT_FILES.items():
        files = (event_map or {}).get(event_name, fallback_files)
        events[event_name] = files[0] if len(files) == 1 else files

    return {
        "enabled": True,
        "soundRoot": "sounds",
        "soundPack": universe,
        "soundSubdir": character,
        "events": events,
    }


def generate_templates(cfg: BuilderConfig) -> int:
    out_dir = cfg.sound_config_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_map = _manifest_event_map(cfg)

    for item in TIER1_CHARACTERS:
        universe = item["universe"]
        character = item["character"]
        payload = make_template(universe, character, manifest_map.get((universe, character)))
        out_path = out_dir / f"{universe}-{character}.json"
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate per-character sound config templates.")
    add_output_path_args(parser)
    args = parser.parse_args(argv)
    cfg = build_config_from_args(args)
    return generate_templates(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
