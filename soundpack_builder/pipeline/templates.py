"""Pipeline step 4: generate per-character Cursor hook sound config templates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from soundpack_builder.core.config import BuilderConfig, add_output_path_args, build_config_from_args
from soundpack_builder.core.console_progress import print_progress_line, print_status
from soundpack_builder.core.hook_events import EVENT_FILES, TARGET_TO_EVENT

# Packs that get template generation + search_hints. Slugs align with
# manifests/universe-character-hook-candidates.json where a character exists there.
HOOK_PACK_CHARACTERS = [
    {"universe": "ace-attorney", "character": "phoenix-wright"},
    {"universe": "batman", "character": "batman-animated"},
    {"universe": "dark-souls", "character": "solaire"},
    {"universe": "disney", "character": "genie"},
    {"universe": "doctor-who", "character": "the-doctor"},
    {"universe": "dragon-ball-z", "character": "goku"},
    {"universe": "dragon-ball-z", "character": "krillin"},
    {"universe": "futurama", "character": "bender"},
    {"universe": "ghostbusters", "character": "venkman-team"},
    {"universe": "halo", "character": "cortana"},
    {"universe": "harry-potter", "character": "spell-incantations"},
    {"universe": "hitchhikers-guide", "character": "marvin"},
    {"universe": "james-bond", "character": "bond"},
    {"universe": "lord-of-the-rings", "character": "gandalf"},
    {"universe": "lord-of-the-rings", "character": "sam-frodo"},
    {"universe": "looney-tunes", "character": "porky-pig"},
    {"universe": "marvel", "character": "captain-america"},
    {"universe": "marvel", "character": "loki"},
    {"universe": "marvel", "character": "tony-stark"},
    {"universe": "mass-effect", "character": "commander-shepard"},
    {"universe": "metal-gear", "character": "snake"},
    {"universe": "mario", "character": "mario"},
    {"universe": "monty-python", "character": "holy-grail-narrator-knight"},
    {"universe": "one-piece", "character": "luffy"},
    {"universe": "portal", "character": "glados"},
    {"universe": "portal", "character": "wheatley"},
    {"universe": "sherlock-holmes", "character": "sherlock"},
    {"universe": "simpsons", "character": "homer"},
    {"universe": "spongebob", "character": "mr-krabs"},
    {"universe": "star-trek", "character": "jean-luc-picard"},
    {"universe": "star-trek", "character": "scotty"},
    {"universe": "star-trek", "character": "spock"},
    {"universe": "star-wars", "character": "c-3po"},
    {"universe": "star-wars", "character": "han-solo"},
    {"universe": "star-wars", "character": "obi-wan"},
    {"universe": "team-fortress-2", "character": "demoman"},
    {"universe": "team-fortress-2", "character": "engineer"},
    {"universe": "team-fortress-2", "character": "scout"},
    {"universe": "terminator", "character": "t800"},
    {"universe": "the-a-team", "character": "hannibal"},
    {"universe": "the-princess-bride", "character": "inigo-vizzini"},
    {"universe": "toy-story", "character": "buzz-lightyear"},
    {"universe": "warcraft", "character": "orc-peon"},
    {"universe": "watchmen", "character": "rorschach"},
]


def _manifest_event_map(cfg: BuilderConfig) -> Dict[tuple[str, str, str], dict]:
    manifest_path = cfg.manifests_dir / "download-manifest.json"
    if not manifest_path.exists():
        return {}
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return {}
    out: Dict[tuple[str, str, str], Dict[str, list[str]]] = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        universe = str(item.get("universe", "")).strip()
        character = str(item.get("character", "")).strip()
        if not universe or not character:
            continue
        pack_slug = str(item.get("packLabelSlug") or "").strip()
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
        event_map = out.setdefault((universe, character, pack_slug), {})
        event_map.setdefault(event_name, []).append(wav_name)
    return out


def make_template(
    universe: str,
    character: str,
    event_map: Optional[dict] = None,
    *,
    pack_label_slug: str = "",
) -> dict:
    events = {}
    for event_name, fallback_files in EVENT_FILES.items():
        files = (event_map or {}).get(event_name, fallback_files)
        events[event_name] = files[0] if len(files) == 1 else files

    subdir = f"{character}/{pack_label_slug}" if pack_label_slug else character
    return {
        "enabled": True,
        "soundRoot": "sounds",
        "soundPack": universe,
        "soundSubdir": subdir,
        "events": events,
    }


def generate_templates(cfg: BuilderConfig, *, progress: bool = True) -> int:
    out_dir = cfg.sound_config_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_map = _manifest_event_map(cfg)

    file_plan: List[tuple[str, str, str]] = []
    for item in HOOK_PACK_CHARACTERS:
        universe = item["universe"]
        character = item["character"]
        slugs = sorted(
            {
                k[2]
                for k in manifest_map.keys()
                if k[0] == universe and k[1] == character
            }
        )
        variants: List[str] = slugs if slugs else [""]
        for slug in variants:
            file_plan.append((universe, character, slug))

    total = len(file_plan)
    if progress:
        print_status(
            f"Generating {total} sound-config template(s)...",
            file=sys.stderr,
        )

    for i, (universe, character, slug) in enumerate(file_plan, start=1):
        if progress:
            detail = f"{universe}/{character}"
            if slug:
                detail = f"{universe}/{character}/{slug}"
            print_progress_line(
                index=i,
                total=total,
                label="template",
                detail=detail,
                file=sys.stderr,
            )
        payload = make_template(
            universe,
            character,
            manifest_map.get((universe, character, slug)),
            pack_label_slug=slug,
        )
        if slug:
            out_path = out_dir / f"{universe}-{character}__{slug}.json"
        else:
            out_path = out_dir / f"{universe}-{character}.json"
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if progress:
        print_status("Done.", file=sys.stderr)

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate per-character sound config templates.")
    add_output_path_args(parser)
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable stderr progress lines.",
    )
    args = parser.parse_args(argv)
    cfg = build_config_from_args(args)
    return generate_templates(cfg, progress=not args.no_progress)


if __name__ == "__main__":
    raise SystemExit(main())
