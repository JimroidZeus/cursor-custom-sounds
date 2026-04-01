from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

CUDA_TORCH_INDEX_URL = "https://download.pytorch.org/whl/cu118"
TORCH_SPEC = "torch>=2.4.0,<2.6.0"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _builder_project_dir() -> Path:
    # tools/preflight.py -> soundpack_builder/tools -> soundpack_builder
    return Path(__file__).resolve().parents[1]


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _parse_nvidia_smi(system_name: str) -> tuple[bool, Optional[str]]:
    if system_name not in ("Linux", "Windows"):
        return False, None
    exe = shutil.which("nvidia-smi")
    if not exe:
        return False, None
    proc = _run([exe, "--query-gpu=name,driver_version", "--format=csv,noheader"])
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "nvidia-smi failed").strip()
    first = ""
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line:
            first = line
            break
    if not first:
        return False, "nvidia-smi returned no GPUs"
    return True, first


def choose_accelerator(system_name: str, has_nvidia_gpu: bool, force: str = "auto") -> str:
    forced = (force or "auto").strip().lower()
    if forced in ("cpu", "gpu"):
        return forced
    if system_name in ("Linux", "Windows") and has_nvidia_gpu:
        return "gpu"
    # macOS and CPU-only hosts use CPU install, runtime auto can still use MPS/CUDA if present.
    return "cpu"


def _uv_sync(project_dir: Path) -> CheckResult:
    proc = _run(["uv", "sync", "--project", str(project_dir)])
    if proc.returncode == 0:
        return CheckResult("uv_sync", True, "uv sync completed")
    return CheckResult("uv_sync", False, (proc.stderr or proc.stdout).strip() or "uv sync failed")


def _install_cuda_torch(project_dir: Path) -> CheckResult:
    # Use uv-managed venv through `uv run` for consistent behavior across OSes.
    proc = _run(
        [
            "uv",
            "run",
            "--project",
            str(project_dir),
            "python",
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--index-url",
            CUDA_TORCH_INDEX_URL,
            TORCH_SPEC,
        ]
    )
    if proc.returncode == 0:
        return CheckResult("cuda_torch_install", True, f"Installed {TORCH_SPEC} from cu118 index")
    return CheckResult(
        "cuda_torch_install",
        False,
        (proc.stderr or proc.stdout).strip() or "Failed to install CUDA torch wheel",
    )


def _torch_runtime_check(project_dir: Path) -> CheckResult:
    snippet = (
        "import json, platform\n"
        "try:\n"
        "  import torch\n"
        "  payload = {\n"
        "    'platform': platform.system(),\n"
        "    'torch': torch.__version__,\n"
        "    'cuda_available': bool(torch.cuda.is_available()),\n"
        "    'cuda_version': torch.version.cuda,\n"
        "    'mps_available': bool(getattr(torch.backends, 'mps', None) and torch.backends.mps.is_available()),\n"
        "  }\n"
        "  print(json.dumps(payload))\n"
        "except Exception as e:\n"
        "  print(json.dumps({'error': str(e)}))\n"
    )
    proc = _run(["uv", "run", "--project", str(project_dir), "python", "-c", snippet])
    if proc.returncode != 0:
        return CheckResult("torch_runtime", False, (proc.stderr or proc.stdout).strip() or "torch check failed")
    out = (proc.stdout or "").strip()
    return CheckResult("torch_runtime", True, out or "{}")


def _classifier_import_check(project_dir: Path) -> CheckResult:
    proc = _run(
        [
            "uv",
            "run",
            "--project",
            str(project_dir),
            "python",
            "-c",
            "from transformers import pipeline; print('pipeline ok')",
        ]
    )
    if proc.returncode == 0:
        return CheckResult("classifier_import", True, (proc.stdout or "pipeline ok").strip())
    return CheckResult(
        "classifier_import", False, (proc.stderr or proc.stdout).strip() or "transformers pipeline import failed"
    )


def _recommendation(accelerator: str) -> str:
    if accelerator == "gpu":
        return (
            "Run downloader with defaults for full capability (auto device selection). "
            "Example: uv run --project soundpack_builder python -m soundpack_builder.pipeline.downloader"
        )
    return (
        "CPU install selected. Downloader defaults still work across systems. "
        "If classifier runtime is unstable, use --disable-llm-classifier."
    )


def run_preflight(*, force_accelerator: str, apply_sync: bool, project_dir: Path) -> dict[str, Any]:
    system_name = platform.system()
    has_nvidia, nvidia_detail = _parse_nvidia_smi(system_name)
    accelerator = choose_accelerator(system_name, has_nvidia_gpu=has_nvidia, force=force_accelerator)

    checks: list[CheckResult] = []
    checks.append(
        CheckResult(
            "hardware_probe",
            True,
            nvidia_detail if has_nvidia else (nvidia_detail or "No NVIDIA GPU detected (or not applicable)"),
        )
    )

    if apply_sync:
        checks.append(_uv_sync(project_dir))
        if accelerator == "gpu":
            checks.append(_install_cuda_torch(project_dir))
        checks.append(_torch_runtime_check(project_dir))
        checks.append(_classifier_import_check(project_dir))

    ok = all(c.ok for c in checks)
    return {
        "ok": ok,
        "platform": system_name,
        "acceleratorTarget": accelerator,
        "projectDir": str(project_dir),
        "applySync": apply_sync,
        "recommended": _recommendation(accelerator),
        "syncPlan": (
            [
                f"uv sync --project {project_dir}",
                (
                    f"uv run --project {project_dir} python -m pip install --upgrade --index-url "
                    f"{CUDA_TORCH_INDEX_URL} '{TORCH_SPEC}'"
                )
                if accelerator == "gpu"
                else "(no extra torch wheel step required)",
            ]
            if apply_sync
            else [
                f"uv sync --project {project_dir}",
                "If GPU target is desired on Windows/Linux, rerun with --sync (or install CUDA torch manually)."
                if accelerator == "gpu"
                else "No additional package step required.",
            ]
        ),
        "checks": [asdict(c) for c in checks],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-platform environment preflight for downloader transcript/classifier runtime. "
            "Use --sync to run uv sync and install a matching torch wheel for detected hardware."
        )
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Run uv sync (and GPU torch install on supported NVIDIA hosts).",
    )
    parser.add_argument(
        "--force-accelerator",
        choices=("auto", "cpu", "gpu"),
        default="auto",
        help="Override accelerator target for planning/install steps.",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=_builder_project_dir(),
        help="Path to soundpack_builder project directory (default: package root).",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")
    args = parser.parse_args(argv)

    payload = run_preflight(
        force_accelerator=args.force_accelerator,
        apply_sync=bool(args.sync),
        project_dir=args.project_dir.resolve(),
    )

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"platform: {payload['platform']}")
        print(f"target accelerator: {payload['acceleratorTarget']}")
        print(f"project: {payload['projectDir']}")
        print(f"sync executed: {payload['applySync']}")
        for chk in payload["checks"]:
            marker = "ok" if chk["ok"] else "fail"
            print(f"- [{marker}] {chk['name']}: {chk['detail']}")
        print(f"recommendation: {payload['recommended']}")
        print("sync plan:")
        for step in payload["syncPlan"]:
            print(f"  - {step}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
