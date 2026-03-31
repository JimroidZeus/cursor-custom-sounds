"""
Pipeline step 5: sanity-check hook-pack sound config templates.

Validates template JSON shape and references under
``sounds/<universe>/<character>/...`` (WAV duration limits optional).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, List, Optional

from soundpack_builder.audio.audio_duration import validate_wav_durations
from soundpack_builder.core.config import (
    BuilderConfig,
    add_output_path_args,
    add_wav_duration_args,
    build_config_from_args,
)
from soundpack_builder.core.console_progress import print_progress_line, print_status

EXPECTED_EVENTS = {
    "beforeSubmitPrompt",
    "afterAgentThought",
    "afterAgentResponse",
    "preToolUse",
    "postToolUse",
    "postToolUseFailure",
    "stop",
}


def as_list(v: Any) -> List[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [x for x in v if isinstance(x, str)]
    return []


def validate_templates(
    cfg: BuilderConfig,
    *,
    check_wav_duration: bool,
    max_wav_seconds: float,
    warn_wav_seconds: float,
    progress: bool = True,
) -> int:
    tmpl_dir = cfg.sound_config_dir
    templates = sorted(tmpl_dir.glob("*.json"))
    if not templates:
        raise SystemExit(f"No templates found under {tmpl_dir}/.")

    if progress:
        print_status(
            f"Validating {len(templates)} template JSON file(s)...",
            file=sys.stderr,
        )

    ok = True
    for i, p in enumerate(templates, start=1):
        if progress:
            print_progress_line(
                index=i,
                total=len(templates),
                label="template",
                detail=p.name,
                file=sys.stderr,
            )
        payload = json.loads(p.read_text(encoding="utf-8"))

        root = payload.get("soundRoot")
        subdir = payload.get("soundSubdir")
        events = payload.get("events", {})

        if root != "sounds":
            ok = False
            print(f"[FAIL] {p}: soundRoot != 'sounds' (got {root!r})")
        if not isinstance(subdir, str) or not subdir.strip():
            ok = False
            print(f"[FAIL] {p}: soundSubdir must be a non-empty string")

        if not isinstance(events, dict):
            ok = False
            print(f"[FAIL] {p}: events is not an object")
            continue

        for event_name in EXPECTED_EVENTS:
            got = as_list(events.get(event_name))
            if not got:
                ok = False
                print(f"[FAIL] {p}: missing or empty event mapping for {event_name}")

        # Ensure all referenced values are wav files.
        for event_name, v in events.items():
            for path_str in as_list(v):
                if not path_str.endswith(".wav"):
                    ok = False
                    print(f"[FAIL] {p}: {event_name} path not a .wav: {path_str}")

    duration_payload = {}
    if check_wav_duration:
        if progress:
            print(file=sys.stderr)
        durations_ok, duration_payload = validate_wav_durations(
            cfg.sound_dir,
            max_seconds=max_wav_seconds,
            warn_seconds=warn_wav_seconds,
            progress=progress,
            progress_file=sys.stderr,
        )
        for warning in duration_payload.get("warnings", []):
            print(
                f"[WARN] {warning['path']}: {warning['seconds']}s exceeds warning threshold "
                f"({warning['warnSeconds']}s)"
            )
        for failure in duration_payload.get("failures", []):
            if "seconds" in failure:
                print(
                    f"[FAIL] {failure['path']}: {failure['seconds']}s exceeds max "
                    f"({failure['maxSeconds']}s)"
                )
            else:
                print(f"[FAIL] {failure['path']}: {failure['error']}")
        ok = ok and durations_ok

    if ok:
        print(
            json.dumps(
                {
                    "ok": True,
                    "templatesChecked": len(templates),
                    "durationCheck": duration_payload,
                }
            )
        )
        return 0

    print(
        json.dumps(
            {
                "ok": False,
                "templatesChecked": len(templates),
                "durationCheck": duration_payload,
            }
        )
    )
    return 1


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate hook-pack sound config templates.")
    add_output_path_args(parser)
    add_wav_duration_args(parser)
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable stderr progress bars (JSON result still on stdout).",
    )
    args = parser.parse_args(argv)
    cfg = build_config_from_args(args)
    return validate_templates(
        cfg,
        check_wav_duration=not args.skip_wav_duration_check,
        max_wav_seconds=args.max_wav_seconds,
        warn_wav_seconds=args.warn_wav_seconds,
        progress=not args.no_progress,
    )


if __name__ == "__main__":
    raise SystemExit(main())
