# Verifies hook playback (track A) and optionally preflight (track B). Run from repo root or any directory.
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

Write-Host "== Repo root: $Root"
Write-Host "== python"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "python not on PATH (see README Getting started)"
}
python --version

Write-Host "== Hook playback test"
python .cursor/hooks/play-sound.py --test afterAgentResponse

Write-Host "== uv (optional, track B)"
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv --version
    Write-Host "== soundpack_builder preflight"
    uv run --project soundpack_builder python -m soundpack_builder.tools.preflight
} else {
    Write-Host "uv not found; skipping preflight. Install uv for the builder pipeline (README Getting started, track B)."
}
