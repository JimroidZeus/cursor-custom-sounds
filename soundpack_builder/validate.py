"""
Sanity-check Tier 1 sound config templates.

Because we are not generating placeholder WAVs, this only validates that
template JSON is structurally correct and references the standardized event
filenames under `sounds/<universe>/<character>/...`.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, List, Optional

from .audio_duration import validate_wav_durations
from .config import (
    BuilderConfig,
    add_output_path_args,
    add_wav_duration_args,
    build_config_from_args,
)

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
) -> int:
    tmpl_dir = cfg.sound_config_dir
    templates = sorted(tmpl_dir.glob("*.json"))
    if not templates:
        raise SystemExit(f"No templates found under {tmpl_dir}/.")

    ok = True
    for p in templates:
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
        durations_ok, duration_payload = validate_wav_durations(
            cfg.sound_dir,
            max_seconds=max_wav_seconds,
            warn_seconds=warn_wav_seconds,
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
    parser = argparse.ArgumentParser(description="Validate Tier 1 sound config templates.")
    add_output_path_args(parser)
    add_wav_duration_args(parser)
    args = parser.parse_args(argv)
    cfg = build_config_from_args(args)
    return validate_templates(
        cfg,
        check_wav_duration=not args.skip_wav_duration_check,
        max_wav_seconds=args.max_wav_seconds,
        warn_wav_seconds=args.warn_wav_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
