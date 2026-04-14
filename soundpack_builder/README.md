# soundpack_builder

Internal pipeline for generating and validating sound pack artifacts. It is separate from the Cursor hook runtime so it can be split out later with minimal churn.

## Environment

From the repository root, install dependencies with **`uv sync --project soundpack_builder`**. Python is constrained by [`pyproject.toml`](pyproject.toml) (`requires-python`; this directory also ships [`.python-version`](.python-version) for local tooling).

Examples below use **`uv run --project soundpack_builder python -m ...`** so modules run in that managed environment. Bare **`python -m soundpack_builder...`** is equivalent only when you have activated a matching interpreter or virtualenv yourself.

After install, run **`uv run --project soundpack_builder python -m soundpack_builder.tools.preflight`** to probe ffmpeg, torch, and optional NVIDIA support; add **`--sync`** to align dependencies (see **Using uv** and **Hardware/software preflight** below).

## Canonical pipeline

Run **`uv run --project soundpack_builder python -m soundpack_builder.pipeline.workflow`** from the repo root (or **`python -m soundpack_builder.pipeline.workflow`** inside an activated env) to print the ordered steps (add **`--json`** for machine-readable output).

| Step | Module | Role |
|------|--------|------|
| 1 | **`search_hints`** | DuckDuckGo URL lines for **hook-pack × verified sites** (no HTTP in the tool). |
| 2 | **`candidates`** | Merges **game-archive** rows with **discovery** links → `manifests/candidates/` (`candidates.json`, `review.json`, `downloadable-all.json`). |
| 3 | **`downloader`** | Fetches/converts into `sounds/<universe>/<character>/` (default **`manifests/download-manifest.json`**). |
| 4 | **`templates`** | Writes per-pack hook config stubs under `configs/` from the manifest. |
| 5 | **`validate`** | Checks template shape + WAV duration limits. |

**Between 1 and 2 (human):** maintain **`manifests/sound-sites.json`**, add **`candidateLinks`** in **`manifests/universe-character-hook-candidates.json`**.

**Between 2 and 3 (human):** read **`manifests/candidates/review.json`**, curate **`manifests/download-manifest.json`**, or pass **`--manifest manifests/candidates/downloadable-all.json`** to the downloader. For **Freesound** links in review, run **`freesound_resolve`** (needs **`FREESOUND_API_KEY`**) and merge **`freesound-resolved.json`** into the download manifest.

**Optional:** **`archive_entries`** (regenerate `generated/archive-entries.json`), **`normalize_manifests`**, **`inject_hook_candidate_links`**, **`freesound_resolve`** (Freesound API → preview URLs), **`repair_wavs`** (re-encode bad `.wav` files that fail validate — needs ffmpeg). Use **`workflow --sourcing-report`** to print verified sites + hook-pack roster.

Full narrative: **`../docs/sound-sourcing.md`** and **`../manifests/README.md`**.

## Scope

- Search + classify + download + template + validate for hook soundpacks
- Non-goal: runtime playback under `.cursor/hooks/`

## Breaking change (Option C)

Root-module entry points and imports have been removed. Use package paths only:

- CLI: `python -m soundpack_builder.pipeline.<name>` for pipeline steps, `python -m soundpack_builder.tools.<name>` for utilities.
- Imports: `soundpack_builder.core.*`, `soundpack_builder.audio.*`, `soundpack_builder.pipeline.*`, `soundpack_builder.tools.*`.

Examples:

- `python -m soundpack_builder.pipeline.downloader`
- `python -m soundpack_builder.pipeline.transcriber`
- `python -m soundpack_builder.pipeline.classifier`

## Project layout

All modules are package-native under the subpackages below (no root compatibility shims):

| Package | Role |
|---------|------|
| **`soundpack_builder.core`** | `config`, `console_progress`, `hook_events`, `manifest_io`, `media_urls`, `pack_label` |
| **`soundpack_builder.audio`** | `audio_duration`, `transcript_mapper`, `wav_convert` (RIFF/ffmpeg helpers) |
| **`soundpack_builder.crawlers`** | site-specific crawler framework + implementations (`sites/`) |
| **`soundpack_builder.pipeline`** | `workflow`, `search_hints`, `candidates`, `downloader`, `templates`, `validate`, **`transcriber`**, **`classifier`** |
| **`soundpack_builder.tools`** | `archive_entries`, `normalize_manifests`, `freesound_resolve`, `repair_wavs`, `inject_hook_candidate_links` |

| Module | Purpose |
|------|---------|
| `pipeline.workflow` | **Pipeline summary** + **`--sourcing-report`** (sites + hook roster) |
| `core.config` | Paths, CLI/env overrides |
| `core.console_progress` | Shared stderr progress |
| `core.hook_events` | Single source for hook event names, per-event WAV filenames, and slot counts |
| `core.manifest_io` | Shared JSON read/write helpers for manifests |
| `tools.archive_entries` | Curated game ZIP rows → `manifests/generated/archive-entries.json` |
| `pipeline.candidates` | Archive rows + discovery → `manifests/candidates/` |
| `tools.freesound_resolve` | Optional: Freesound **`review.json`** rows → `freesound-resolved.json` |
| `pipeline.search_hints` | Step 1 of pipeline |
| `crawl` | Optional crawler entrypoint (`python -m soundpack_builder.crawl`) that discovers site links and can append deduped `candidateLinks` |
| `pipeline.templates` | Step 4; uses **`HOOK_PACK_CHARACTERS`** + `download-manifest.json` |
| `pipeline.validate` | Step 5 |
| `pipeline.downloader` | Step 3 |
| `tools.normalize_manifests` | Schema v2 normalization |
| `tools.repair_wavs` | Re-encode `sounds/**/*.wav` that are not PCM RIFF |
| `tools.inject_hook_candidate_links` | Advanced bulk edits to universe JSON |
| `audio.transcript_mapper` | Whisper + zero-shot labels + global per-slot mapping |
| `pipeline.transcriber` | Transcribe a pack folder → per-pack **`transcripts.json`** sidecar |
| `pipeline.classifier` | Classify from **`transcripts.json`** → **`classifier-scores.json`** |

**Sidecar files (per pack directory under `sounds/`):** **`transcripts.json`**, **`classifier-scores.json`**. The downloader can load them with **`--use-existing-transcripts`** and **`--use-existing-classifier-scores`** instead of re-running inference when present.

## Path configuration

Defaults are repository-relative:

- manifests: `manifests/`
- configs: `configs/`
- sounds: `sounds/`

Override with **`SOUNDPACK_BUILDER_*`** env vars or **`--repo-root`**, **`--out-manifests-dir`**, **`--out-configs-dir`**, **`--out-sounds-dir`** on CLIs that support them.

Packs live under **`sounds/<universe>/<character>/`** and, when a row has **`packLabelSlug`**, **`sounds/<universe>/<character>/<packLabelSlug>/`**. The `character` segment keeps packs distinct when different personas share a universe (e.g. the same slug string under another character is still a different folder). If you rename a hook-pack **`character`** in **`universe-character-hook-candidates.json`**, move the matching tree under **`sounds/`** and update **`soundSubdir`** in pack **`sound-config.json`** (and any Cursor hook config that points at that pack).

**Other env (optional):**

| Variable | Used by |
|----------|---------|
| **`FREESOUND_API_KEY`** | **`freesound_resolve`** — [Freesound API v2](https://freesound.org/help/developers/) token (same as `Authorization: Token …`). Load from `soundpack_builder/.env` via **`config.freesound_api_key()`**. |
| **`HF_TOKEN`** | Downloader transcript / zero-shot classifier — see **`config.hf_token()`**. |

**Two GPUs (typical setup):** run the downloader with e.g. **`--whisper-device cuda:0`** and **`--classifier-device cuda:1`** so Whisper and the Hugging Face classifier use different devices. File-level parallel inference across GPUs is not built in; run separate **`transcriber`** / **`classifier`** processes with different **`CUDA_VISIBLE_DEVICES`** if you need that.

## Candidate manifests (`candidates`)

**Inputs:** `manifests/sound-sites.json`, `manifests/sourcing-config.json`, `manifests/universe-character-hook-candidates.json`.

**`sourcing-config.json`** supplies:

- **`discovery`** — Regexes for classifying URLs (ZIP vs direct media vs sound-page hosts) and for **fallback** extraction of media URLs from raw HTML when structured parsing does not find a link. Includes **Freesound** single-sound URL patterns (`freesound.org/s/<id>/`, `freesound.org/people/.../sounds/<id>/`) so those links are treated as sound pages (not generic portals). Search, tag, and pack URLs stay **portal** until you resolve them (see **`freesound_resolve`** below).
- **`universeAliases`** — Map discovery universe slugs to archive rows when needed.
- **`fetch`** (optional) — **`maxRetries`** and **`delayBetweenRequestsSec`** for HTTP when using **`--fetch-sound-pages`** (GET sound pages, parse HTML for `src` / `href` / `data-src`, resolve relative URLs, then regex fallback).

**What it does**

1. Stages **game-archive** rows (same source as `archive_entries.build()`), tagged **`source`: `archive`**.
2. If the universe manifest exists, classifies each **`candidateLinks`** URL (ZIP, direct, sound page, portal) for approved **`siteId`**s and appends downloader rows or **`review.json`** items (**`source`: `discovery`**). Discovery rows use neutral **`discovery_NNN.wav`** names (no hook preclassification). Optional **`matchQuality`** on a link is copied onto downloader-ready rows when present.
3. Writes **`manifests/candidates/`** outputs.

```bash
uv run --project soundpack_builder python -m soundpack_builder.pipeline.candidates
uv run --project soundpack_builder python -m soundpack_builder.pipeline.candidates --fetch-sound-pages
```

- `--sourcing-config`, `--sound-sites`, `--universe-manifest`, `--out-dir` — see `--help`.
- `--no-progress` — JSON summary on stdout only.

## Crawler module (`crawl`)

Crawler support is additive: it helps populate discovery links but does not bypass manifest review.

```bash
uv run --project soundpack_builder python -m soundpack_builder.crawl --site-id spriters-resource-sounds --universe dc --character batman --max-results 5 --json
uv run --project soundpack_builder python -m soundpack_builder.crawl --site-id spriters-resource-sounds --universe dc --character batman --apply
```

- Generated output defaults to `manifests/candidates/<site-id>-crawl.json`.
- `--apply` appends deduped URLs to `manifests/universe-character-hook-candidates.json`.
- Current first crawler: **The Sounds Resource** (`sounds.spriters-resource.com`) search page -> asset page -> ZIP URL discovery.
- Keep `download-manifest.json` curation as the gate before `downloader`.

## Freesound resolver (`freesound_resolve`)

After **`candidates`**, **`review.json`** may list Freesound portals, search pages, tag browse URLs, packs, or sound pages that still need a direct media URL. **`freesound_resolve`** reads every row with **`siteId: freesound`**, calls the **Freesound API v2**, and writes **`manifests/candidates/freesound-resolved.json`** with downloader-shaped **`entries`** plus **`skipped`** (unrecognized URL, no search hit, API error, etc.). Search/tag/pack modes take the **first** API result (same idea as the top hit on the site).

**Requires** **`FREESOUND_API_KEY`** in the environment or **`--token`**.

```bash
uv run --project soundpack_builder python -m soundpack_builder.tools.freesound_resolve
uv run --project soundpack_builder python -m soundpack_builder.tools.freesound_resolve --help
```

**Common flags:** `--review <path>`, `--out <path>`, `--delay-sec` (default `0.25` between API calls).

Merge **`entries`** from **`freesound-resolved.json`** into **`manifests/download-manifest.json`** (or combine with **`downloadable-all.json`**) before **`downloader`**.

## Console output and `--no-progress`

| Module | stdout | stderr | `--no-progress` |
|--------|--------|--------|-----------------|
| `workflow` | pipeline text or `--json` | — | n/a |
| `archive_entries` | `{"ok","count","out"}` | status | yes |
| `candidates` | JSON report | progress | yes |
| `validate` | JSON on exit | progress | yes |
| `templates` | — | per-template lines | yes |
| `downloader` | structured logs | progress | yes |
| `workflow --sourcing-report` | text or `--json` | — | n/a |
| `search_hints` | lines or `--json` | — | n/a |
| `freesound_resolve` | JSON summary (`ok`, `out`, `resolved`, `skipped`) | — | n/a |

## Using uv

From repo root:

```bash
uv sync --project soundpack_builder
uv run --project soundpack_builder python -m soundpack_builder.pipeline.workflow
```

### Hardware/software preflight (Windows, macOS, Linux)

Use preflight to validate runtime compatibility and optionally install the matching torch build:

```bash
# probe only
uv run --project soundpack_builder python -m soundpack_builder.tools.preflight

# probe + run uv sync + install CUDA torch on supported NVIDIA hosts
uv run --project soundpack_builder python -m soundpack_builder.tools.preflight --sync
```

The downloader already defaults to `--whisper-device auto` and `--classifier-device auto`, so once dependencies match the host, full capability is used automatically.

## Suggested commands (copy-paste)

```bash
uv run --project soundpack_builder python -m soundpack_builder.pipeline.search_hints
# Edit universe manifests + sound-sites

uv run --project soundpack_builder python -m soundpack_builder.pipeline.candidates
# Review manifests/candidates/review.json; optional Freesound API resolution:
#   uv run --project soundpack_builder python -m soundpack_builder.tools.freesound_resolve
# Merge freesound-resolved.json entries into download-manifest.json

uv run --project soundpack_builder python -m soundpack_builder.pipeline.downloader
# One logical pack only (download + recommended config for that pack):
#   ... pipeline.downloader --pack-key UNIVERSE/CHARACTER
#   ... pipeline.downloader --pack-key UNIVERSE/CHARACTER/PACK_LABEL_SLUG
uv run --project soundpack_builder python -m soundpack_builder.pipeline.templates
uv run --project soundpack_builder python -m soundpack_builder.pipeline.validate
```

**Reference only (game ZIP dump):**

```bash
uv run --project soundpack_builder python -m soundpack_builder.tools.archive_entries
```

## ffmpeg

Downloader may use ffmpeg when the source is not already WAV (`ffmpeg -version`).

## Transcript-driven recommendations (downloader)

When **`--no-recommended-config`** is not set, the downloader can generate **`sounds/<universe>/<character>/sound-config.json`** and **`mapping-report.json`** per pack:

- **Transcription:** faster-whisper (default model **`tiny`**; override with **`--whisper-model`** or shorthand **`--preset fast`** / **`--preset quality`** → **`tiny`** / **`small`**).
- **Optional classifier:** Hugging Face zero-shot NLI (unless **`--disable-llm-classifier`**). **`--classifier-weight`** blends classifier scores with filename/heuristic signals.
- **Event mapping:** Each hook WAV is assigned to **at most one** slot when there are enough files; with fewer clips than slots, the best semantic match per slot is reused as needed. **`matchQuality`** on a manifest row (numeric 0–1 or labels like **`high`** / **`medium`**) adds a small boost when ranking clips.
- **Speech verification (Whisper runs):** By default, clips whose transcript is empty or not lexical speech (e.g. only `[music]`-style noise) are **omitted** from the recommended `sound-config.json` and listed under **`speechVerification.excludedClips`** in **`mapping-report.json`**. If **no** clip passes, the pack config file is **not** written and the downloader reports an error. Disable with **`--no-speech-verification`** (all WAVs participate, as before this check). With **`--skip-transcript-analysis`**, verification is not run; **`speechVerification.mode`** is **`skipped`** and clips are **`notAssessed`**.
- **Outputs:** Recommended `sound-config.json` plus **`mapping-report.json`** (scores per clip × event for review, plus speech verification metadata).

## Tests

```bash
uv run --project soundpack_builder python -m unittest discover -s soundpack_builder/tests -p "test_*.py"
```

## Dependency smoke check (Windows)

Use this quick import check after dependency upgrades to catch classifier runtime regressions early:

```bash
uv run --project soundpack_builder python -c "from transformers import pipeline; print('pipeline ok')"
```

## Windows CUDA / classifier troubleshooting

- Run preflight first to validate host/runtime fit and apply a matching install plan:

```bash
uv run --project soundpack_builder python -m soundpack_builder.tools.preflight --sync
```

- If `nvidia-smi` reports `CUDA Version: N/A`, CUDA torch install fails, or transcription logs `CUDA driver version is insufficient for CUDA runtime version`, use CPU flags.
- If classifier runtime is unstable on your host, keep recommendation generation reliable with:

```bash
uv run --project soundpack_builder python -m soundpack_builder.pipeline.downloader --whisper-device cpu --disable-llm-classifier
```

- Re-enable classifier only after this import gate passes:

```bash
uv run --project soundpack_builder python -c "from transformers import pipeline; print('pipeline ok')"
```
