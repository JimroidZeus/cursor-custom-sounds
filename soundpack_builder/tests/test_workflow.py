from __future__ import annotations

import json
import io
import unittest
from contextlib import redirect_stdout
from soundpack_builder import describe_pipeline
from soundpack_builder.pipeline.workflow import PIPELINE_STEPS, main


class WorkflowTests(unittest.TestCase):
    def test_pipeline_order(self) -> None:
        modules = [m for m, _ in PIPELINE_STEPS]
        self.assertEqual(
            modules,
            ["search_hints", "candidates", "downloader", "templates", "validate"],
        )

    def test_describe_pipeline_text(self) -> None:
        text = describe_pipeline()
        self.assertIn("search_hints", text)
        self.assertIn("candidates", text)
        self.assertIn("Human steps", text)
        self.assertIn("--sourcing-report", text)

    def test_main_json(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["--json"])
        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(
            data["pipeline"],
            ["search_hints", "candidates", "downloader", "templates", "validate"],
        )

    def test_main_sourcing_report_json(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["--sourcing-report", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertIn("soundSites", data)
        self.assertIn("hookPackCharacters", data)


if __name__ == "__main__":
    unittest.main()
