from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from soundpack_builder.config import BuilderConfig
from soundpack_builder.phased_candidates import (
    _site_min_phase,
    _url_kind,
    build_phase_manifests,
)


class PhasedCandidatesTests(unittest.TestCase):
    def test_url_kind(self) -> None:
        self.assertEqual(
            _url_kind("https://sounds.spriters-resource.com/media/assets/422/425494.zip?x=1"),
            "spriters_zip",
        )
        self.assertEqual(_url_kind("https://freesound.org/s/123/"), "freesound_page")
        self.assertEqual(_url_kind("https://x/audio.wav"), "direct_audio")
        self.assertEqual(_url_kind("https://freesound.org/search/?q=test"), "portal")

    def test_site_min_phase(self) -> None:
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
        phased = repo / "manifests" / "phased-sourcing.json"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            report = build_phase_manifests(
                cfg,
                phased_path=phased,
                universe_path=repo / "manifests" / "nonexistent.json",
                out_dir=out,
                resolve_freesound=False,
            )
            self.assertTrue(report["ok"])
            p1 = json.loads((out / "phase-1-candidates.json").read_text(encoding="utf-8"))
            self.assertGreater(len(p1["entries"]), 80)
            self.assertEqual(p1["entries"][0]["sourcingPhase"], 1)
