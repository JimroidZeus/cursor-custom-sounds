"""Optional: normalize download-manifest.json and universe-character-hook-candidates.json to current schema.

Not part of the linear pipeline; run after bulk JSON edits. From repo root:
  uv run --project soundpack_builder python -m soundpack_builder.tools.normalize_manifests
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from soundpack_builder.core.hook_events import TARGET_TO_EVENT


DOWNLOAD_MANIFEST_DESC = (
    "Downloader entries (ZIP + pathInArchive or direct media). "
    "Edit this file or merge from manifests/candidates/downloadable-all.json after review."
)
UNIVERSE_DESC = (
    "Character discovery: flat candidateLinks per character (page URLs or direct media). "
    "Legacy manifests may still use events.*.candidateLinks; run this tool to merge into candidateLinks. "
    "Site ids must match manifests/sound-sites.json. Optional discoveryHints hold search helpers."
)


def _load_download_entries(path: Path) -> list:
    text = path.read_text(encoding="utf-8")
    text = text.replace("n    }", "    }").strip()
    if not text.startswith("{"):
        text = "{" + text + "}"
    data = json.loads(text)
    if isinstance(data, dict) and "entries" in data:
        return data["entries"]
    if isinstance(data, list):
        return data
    raise ValueError("download-manifest: expected {entries:[...]} or [...]")


def normalize_download_manifest_entries(entries: list) -> list:
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        row = {k: v for k, v in e.items() if k not in ("sourcingPhase", "sourcingSlug", "source")}
        tf = str(row.get("targetFile") or "").strip()
        if tf and not row.get("event"):
            ev = TARGET_TO_EVENT.get(tf)
            if ev:
                row["event"] = ev
        row["source"] = "download-manifest"
        out.append(row)
    return out


def _normalize_character(ch: Dict[str, Any]) -> Dict[str, Any]:
    """Merge character.candidateLinks + legacy events.*.candidateLinks into a single flat list."""
    base = {k: v for k, v in ch.items() if k not in ("events", "candidateLinks")}
    merged: list = []
    for link in ch.get("candidateLinks") or []:
        if isinstance(link, dict):
            merged.append(link)
    raw_events = ch.get("events") or {}
    if isinstance(raw_events, dict):
        for ev_name in sorted(raw_events.keys()):
            ev = raw_events[ev_name]
            if not isinstance(ev, dict):
                continue
            ev_note = str(ev.get("note") or ev.get("rationale", "") or "").strip()
            for link in ev.get("candidateLinks") or []:
                if not isinstance(link, dict):
                    continue
                lk = dict(link)
                lab = str(lk.get("label") or "").strip()
                if ev_note:
                    if lab:
                        lk["label"] = f"[{ev_name}] {lab}"
                    else:
                        lk["label"] = f"[{ev_name}] {ev_note}"
                merged.append(lk)
    base["candidateLinks"] = merged
    return base


def _normalize_cross_pack(pack: Dict[str, Any]) -> Dict[str, Any]:
    p = dict(pack)
    sid = p.pop("suggestedSourceSiteIds", None)
    if sid:
        p.setdefault("discoveryHints", {})["suggestedSourceSiteIds"] = sid
    return p


def normalize_universe(data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "schemaVersion": 3,
        "description": UNIVERSE_DESC,
        "sourceSitesRef": "sound-sites.json",
        "sourceSitesNote": (
            "Canonical verified site list with stable ids for candidateLinks.siteId. "
            "Do not duplicate full site rows here."
        ),
        "cursorHookEvents": data.get(
            "cursorHookEvents",
            [
                "beforeSubmitPrompt",
                "afterAgentThought",
                "afterAgentResponse",
                "preToolUse",
                "postToolUse",
                "postToolUseFailure",
                "stop",
            ],
        ),
        "characters": [_normalize_character(ch) for ch in data.get("characters") or [] if isinstance(ch, dict)],
        "crossFranchiseOneVoicePacks": [
            _normalize_cross_pack(p) for p in data.get("crossFranchiseOneVoicePacks") or [] if isinstance(p, dict)
        ],
        "soundConfigTemplate": data.get("soundConfigTemplate", {}),
    }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize manifest JSON files to schema v2.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: parent of soundpack_builder).",
    )
    args = parser.parse_args()
    root = args.repo_root or Path(__file__).resolve().parents[2]
    manifests = root / "manifests"

    download_path = manifests / "download-manifest.json"
    entries_in = _load_download_entries(download_path)
    download_payload = {
        "schemaVersion": 2,
        "description": DOWNLOAD_MANIFEST_DESC,
        "entries": normalize_download_manifest_entries(entries_in),
    }
    download_path.write_text(json.dumps(download_payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {download_path} ({len(download_payload['entries'])} entries)")

    uni_path = manifests / "universe-character-hook-candidates.json"
    uni_data = json.loads(uni_path.read_text(encoding="utf-8"))
    uni_out = normalize_universe(uni_data)
    uni_path.write_text(json.dumps(uni_out, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {uni_path} ({len(uni_out['characters'])} characters)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
