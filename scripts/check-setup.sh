#!/usr/bin/env bash
# Run from anywhere; changes to repo root. Verifies hook playback (track A) and optionally preflight (track B).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

echo "== Repo root: $ROOT"
echo "== python"
if ! command -v python >/dev/null 2>&1; then
  echo "error: python not on PATH (see README Getting started)" >&2
  exit 1
fi
python --version

echo "== Hook playback test"
python .cursor/hooks/play-sound.py --test afterAgentResponse

echo "== uv (optional, track B)"
if command -v uv >/dev/null 2>&1; then
  uv --version
  echo "== soundpack_builder preflight"
  uv run --project soundpack_builder python -m soundpack_builder.tools.preflight
else
  echo "uv not found; skipping preflight. Install uv for the builder pipeline (README Getting started, track B)."
fi
