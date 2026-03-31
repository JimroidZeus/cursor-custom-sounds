from __future__ import annotations

import json
import unittest
from pathlib import Path

from soundpack_builder.core.config import BuilderConfig
from soundpack_builder.pipeline.workflow import build_sourcing_report


class SourcingReportTests(unittest.TestCase):
    def test_build_report_has_sites_and_hook_pack(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        cfg = BuilderConfig.defaults(repo)
        report = build_sourcing_report(cfg)
        self.assertGreaterEqual(len(report["soundSites"]), 5)
        self.assertGreaterEqual(len(report["hookPackCharacters"]), 10)
        ids = {s["id"] for s in report["soundSites"]}
        self.assertIn("spriters-resource-sounds", ids)
        self.assertIn("voicy", ids)

    def test_json_roundtrip_schema(self) -> None:
        path = Path(__file__).resolve().parents[2] / "manifests" / "sound-sites.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["schemaVersion"], 1)
        self.assertGreaterEqual(len(data["sites"]), 5)


if __name__ == "__main__":
    unittest.main()
