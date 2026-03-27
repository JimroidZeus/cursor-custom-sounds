# soundpack_builder

Internal builder pipeline for generating and validating sound pack artifacts.

This module is intentionally separate from the Cursor hook runtime so it can be
split into its own repository later with minimal churn.

## Scope

- Builds candidate manifests
- Generates per-character sound config templates
- Validates template structure and event filename conventions
- Validates WAV playback duration limits under `sounds/`
- Downloads and converts approved clips into `sounds/<universe>/<character>/`
  - Preserves source clip basenames (normalizes extension to `.wav`)
  - Generates recommended per-pack `sound-config.json` using transcript + filename mapping

Non-goal: runtime playback logic under `.cursor/hooks/`.

## Project Layout

- `config.py` - shared path config and CLI/env overrides
- `tier1_candidates.py` - manifest candidate builder
- `phased_sourcing.py` - print phased sourcing plan (`manifests/phased-sourcing.json`)
- `phased_candidates.py` - write `manifests/phased/phase-*-candidates.json` and review queues from tier1 + discovery JSON
- `templates.py` - template generator
- `validate.py` - template validator
- `downloader.py` - manifest downloader/converter

## Path Configuration

Defaults are repository-relative:

- manifests: `manifests/`
- configs: `configs/`
- sounds: `sounds/`

Override using env vars:

- `SOUNDPACK_BUILDER_REPO_ROOT`
- `SOUNDPACK_BUILDER_MANIFESTS_DIR`
- `SOUNDPACK_BUILDER_CONFIGS_DIR`
- `SOUNDPACK_BUILDER_SOUNDS_DIR`
- `SOUNDPACK_BUILDER_WAV_DURATION_WARN_SECONDS` (default warning threshold: `10.0`)
- `SOUNDPACK_BUILDER_WAV_DURATION_MAX_SECONDS` (default failure threshold: `15.0`)

Override using CLI flags (supported by all builder entry points):

- `--repo-root`
- `--out-manifests-dir`
- `--out-configs-dir`
- `--out-sounds-dir`

## Using uv

`soundpack_builder` has its own `pyproject.toml` so it can be managed as a
standalone Python project even while living in this repo.

From the repository root:

1. Install uv (one-time):
   - PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
2. Install/select a compatible Python for this project (recommended 3.12):
   - `uv python install 3.12`
3. Create the local environment:
   - `uv sync --project soundpack_builder`
   - If you previously synced with incompatible wheels, force a refresh:
     - `uv sync --project soundpack_builder --refresh`

## Running the Builder

Run from repository root so `soundpack_builder` imports resolve cleanly.

- Build tier-1 candidates:
  - `uv run --project soundpack_builder python -m soundpack_builder.tier1_candidates`
- Print phased sourcing plan (video games → cartoons → movies):
  - `uv run --project soundpack_builder python -m soundpack_builder.phased_sourcing`
  - `uv run --project soundpack_builder python -m soundpack_builder.phased_sourcing --phase 2 --json`
- Build phased downloader manifests + review lists (`manifests/phased/`):
  - `uv run --project soundpack_builder python -m soundpack_builder.phased_candidates`
  - `uv run --project soundpack_builder python -m soundpack_builder.phased_candidates --fetch-sound-pages`
- Generate templates:
  - `uv run --project soundpack_builder python -m soundpack_builder.templates`
- Validate templates + WAV duration constraints:
  - `uv run --project soundpack_builder python -m soundpack_builder.validate`
  - Default thresholds:
    - warning at `10.0s` (`--warn-wav-seconds`)
    - failure at `15.0s` (`--max-wav-seconds`)
  - Configure/disable:
    - `--warn-wav-seconds 12`
    - `--max-wav-seconds 18`
    - `--skip-wav-duration-check` (template-only validation)
- Download approved clips:
  - `uv run --project soundpack_builder python -m soundpack_builder.downloader`
  - Shows progress/status lines by default (disable with `--no-progress`)
  - Also writes `sounds/<universe>/<character>/sound-config.json` recommendations by default

Examples with output overrides:

- `uv run --project soundpack_builder python -m soundpack_builder.tier1_candidates --out-manifests-dir ".tmp/manifests"`
- `uv run --project soundpack_builder python -m soundpack_builder.templates --out-configs-dir ".tmp/configs"`

## ffmpeg

`soundpack_builder.downloader` may need ffmpeg when the source is not already WAV.

- Verify: `ffmpeg -version`

## Transcript-driven recommendations

Downloader now attempts local speech-to-text transcription (Whisper) to improve event mapping quality.

- Dependency is managed in `soundpack_builder/pyproject.toml` (`faster-whisper`).
- Optional zero-shot event classifier uses `transformers`. Ranking is **tiered**: clips with a non-empty transcript **and** classifier scores for that clip are ordered by `modelScore` first (with a small heuristic tie-break); all other clips use normalized filename + text heuristics only.
- If transcription fails or is unavailable for a clip, or the classifier did not produce scores for that clip, that clip uses the heuristic tier.
- `mapping-report.json` lists each candidate with `rankingTier` set to `model` or `heuristic_fallback`, and `score` reflects the tier (`modelScore * classifier-weight` plus a tiny tie-break for the model tier, or normalized heuristic score for the fallback tier).
- Generated recommendation path:
  - `sounds/<universe>/<character>/sound-config.json`
  - `sounds/<universe>/<character>/mapping-report.json` (scores + transcripts + selected files)

Useful flags:

- `--skip-transcript-analysis` - skip Whisper and use filename heuristics only.
- `--whisper-model tiny` - choose model size (`tiny` default).
- `--whisper-language en` - force language (`auto` for autodetect).
- `--whisper-device auto` - runtime device selection.
- `--whisper-compute-type auto` - backend compute type.
- `--overwrite-recommended-config` - replace existing generated pack config files.
- `--no-recommended-config` - disable generation entirely.
- `--disable-llm-classifier` - disable zero-shot event classification (heuristics only).
- `--classifier-model valhalla/distilbart-mnli-12-1` - choose classifier model.
- `--classifier-weight 5.0` - scales the **displayed** model contribution in `mapping-report.json` (`score` for `rankingTier: model`); ordering within the model tier is by raw `modelScore` (weight is a common factor).

## Tests

There is a small regression test suite under `soundpack_builder/tests`.

- Run all tests from repo root:
  - `uv run --project soundpack_builder python -m unittest discover -s soundpack_builder/tests -p "test_*.py"`

