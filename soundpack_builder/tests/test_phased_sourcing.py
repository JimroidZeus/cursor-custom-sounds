from __future__ import annotations

import json
import unittest
from pathlib import Path

from soundpack_builder.config import BuilderConfig
from soundpack_builder.phased_sourcing import build_report


class PhasedSourcingTests(unittest.TestCase):
    def test_build_report_has_three_phases_and_tier1(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        cfg = BuilderConfig.defaults(repo)
        report = build_report(cfg)
        self.assertEqual(len(report["phases"]), 3)
        self.assertEqual(report["phases"][0]["slug"], "video-games")
        self.assertTrue(len(report["tier1Characters"]) >= 10)
        p2 = report["phases"][1]
        ids = {s["id"] for s in p2["resolvedSourceSites"]}
        self.assertIn("voicy", ids)
        self.assertIn("hanna-barbera-wiki", ids)

    def test_json_roundtrip_schema(self) -> None:
        path = Path(__file__).resolve().parents[2] / "manifests" / "phased-sourcing.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["schemaVersion"], 1)
        self.assertEqual(len(data["phases"]), 3)


if __name__ == "__main__":
    unittest.main()
