from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from soundpack_builder.config import BuilderConfig
from soundpack_builder.phased_candidates import (
    DEFAULT_PHASED_MANIFEST,
    URL_KIND_ARCHIVE_ZIP,
    URL_KIND_DIRECT_MEDIA,
    URL_KIND_PORTAL,
    URL_KIND_SOUND_PAGE,
    _compile_regex_list,
    _discovery_rules,
    build_phase_manifests,
    classify_url,
)


class PhasedCandidatesTests(unittest.TestCase):
    def test_classify_url_generic(self) -> None:
        rules = {
            "soundPage": _compile_regex_list([r"example\.com/sound/\d+"], label="x"),
            "htmlAudio": [],
        }
        self.assertEqual(
            classify_url("https://cdn.example.com/files/pack.zip?x=1", rules),
            URL_KIND_ARCHIVE_ZIP,
        )
        self.assertEqual(classify_url("https://x/audio.wav", rules), URL_KIND_DIRECT_MEDIA)
        self.assertEqual(
            classify_url("https://example.com/sound/42", rules),
            URL_KIND_SOUND_PAGE,
        )
        self.assertEqual(classify_url("https://example.com/search?q=a", rules), URL_KIND_PORTAL)

    def test_site_min_phase_indirect(self) -> None:
        from soundpack_builder.phased_candidates import _site_min_phase

        phases = [
            {"id": 1, "sourceSiteIds": ["a", "shared"]},
            {"id": 2, "sourceSiteIds": ["b", "shared"]},
        ]
        self.assertEqual(_site_min_phase(phases, "a"), 1)
        self.assertEqual(_site_min_phase(phases, "b"), 2)
        self.assertEqual(_site_min_phase(phases, "shared"), 1)
        self.assertIsNone(_site_min_phase(phases, "missing"))

    def test_build_minimal_phases_no_universe(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        cfg = BuilderConfig.defaults(repo)
        phased = repo / "manifests" / DEFAULT_PHASED_MANIFEST
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            report = build_phase_manifests(
                cfg,
                phased_path=phased,
                universe_path=repo / "manifests" / "nonexistent-discovery.json",
                out_dir=out,
                fetch_sound_pages=False,
            )
            self.assertTrue(report["ok"])
            p1 = json.loads((out / "phase-1-candidates.json").read_text(encoding="utf-8"))
            self.assertGreater(len(p1["entries"]), 80)
            self.assertEqual(p1["entries"][0]["sourcingPhase"], 1)

    def test_discovery_rules_loads_from_repo_manifest(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        phased = _discovery_rules(json.loads((repo / "manifests" / DEFAULT_PHASED_MANIFEST).read_text()))
        self.assertTrue(len(phased["soundPage"]) >= 1)
        self.assertTrue(len(phased["htmlAudio"]) >= 1)


if __name__ == "__main__":
    unittest.main()
