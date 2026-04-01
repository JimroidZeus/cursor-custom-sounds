from __future__ import annotations

import unittest

from soundpack_builder.tools.preflight import choose_accelerator, run_preflight


class PreflightTests(unittest.TestCase):
    def test_choose_accelerator_gpu_on_windows_with_nvidia(self) -> None:
        self.assertEqual(choose_accelerator("Windows", has_nvidia_gpu=True), "gpu")

    def test_choose_accelerator_cpu_on_linux_without_nvidia(self) -> None:
        self.assertEqual(choose_accelerator("Linux", has_nvidia_gpu=False), "cpu")

    def test_choose_accelerator_cpu_on_macos(self) -> None:
        self.assertEqual(choose_accelerator("Darwin", has_nvidia_gpu=False), "cpu")

    def test_force_accelerator_override(self) -> None:
        self.assertEqual(choose_accelerator("Linux", has_nvidia_gpu=False, force="gpu"), "gpu")
        self.assertEqual(choose_accelerator("Linux", has_nvidia_gpu=True, force="cpu"), "cpu")

    def test_preflight_plan_without_sync(self) -> None:
        payload = run_preflight(force_accelerator="cpu", apply_sync=False, project_dir=self._project_dir())
        self.assertIn("syncPlan", payload)
        self.assertEqual(payload["acceleratorTarget"], "cpu")
        self.assertFalse(payload["applySync"])

    @staticmethod
    def _project_dir():
        # tests/ -> soundpack_builder
        from pathlib import Path

        return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main()
