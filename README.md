# Cursor Custom Sounds

This repository now uses Cursor's official Hooks system for chat lifecycle sounds.

## Config

Primary configuration lives in:

- `.cursor/hooks.json`
- `.cursor/hooks/sound-config.json`

For full setup and override details, see `docs/hooks-setup.md`.

Example `.cursor/hooks/sound-config.json`:

```json
{
  "enabled": true,
  "soundRoot": "sounds",
  "soundPack": "warcraft",
  "soundSubdir": "orc-peon",
  "events": {
    "beforeSubmitPrompt": [
      "beforeSubmitPrompt_1.wav",
      "beforeSubmitPrompt_2.wav"
    ],
    "afterAgentThought": ["afterAgentThought_1.wav", "afterAgentThought_2.wav"],
    "afterAgentResponse": ["afterAgentResponse_1.wav", "afterAgentResponse_2.wav"],
    "preToolUse": "preToolUse.wav",
    "postToolUse": "postToolUse.wav",
    "postToolUseFailure": "postToolUseFailure.wav",
    "stop": "stop.wav"
  }
}
```

Each event value can be either:
- a single path string, or
- an array of path strings (one is picked randomly each time).

Paths can be absolute or workspace-relative.
If `soundRoot` is set, relative paths resolve from that folder first.
If `soundPack` is set, relative event paths resolve under `soundRoot/<soundPack>/`.
If `soundSubdir` is set and an event value is just a filename (no folder path),
it resolves under `soundRoot/<soundPack>/<soundSubdir>/`.

## Event meanings in chat UI

- `beforeSubmitPrompt`: fires when you submit a prompt/message (right after send).
- `afterAgentThought`: fires after an internal reasoning/thought step.
- `afterAgentResponse`: fires when the agent posts a response.
- `preToolUse`: fires right before a tool runs.
- `postToolUse`: fires after a tool succeeds.
- `postToolUseFailure`: fires after a tool fails.
- `stop`: fires when generation is stopped/cancelled.

## Manifest workflow

Dependencies and the virtualenv live under `soundpack_builder/` with **uv**; see that folder’s README for flags, paths, and tests. One-time setup from repo root:

```bash
uv sync --project soundpack_builder
```

### Sound sourcing (pipeline)

Order is **`search_hints` → `candidates` → `downloader` → `templates` → `validate`**, with human edits to manifests between the first two steps and before the downloader. Print the checklist anytime:

```bash
uv run --project soundpack_builder python -m soundpack_builder.pipeline.workflow
```

1. Maintain **`manifests/sound-sites.json`** (verified site ids) and add **`candidateLinks`** in **`manifests/universe-character-hook-candidates.json`** (each **`siteId`** must exist in `sound-sites.json`).
2. **`search_hints`** prints **browser search URLs** (hook-pack character × site); nothing is scraped automatically.
3. **`candidates`** reads **`manifests/sourcing-config.json`**, classifies links, and writes **`manifests/candidates/`** (`candidates.json`, `review.json`, `downloadable-all.json`).
4. Review **`review.json`**, then curate **`manifests/download-manifest.json`**, or pass **`--manifest manifests/candidates/downloadable-all.json`** to the downloader.
5. **`downloader`** → **`templates`** → **`validate`**.

**Doc map:** **`docs/sound-sourcing.md`** (sourcing pipeline), **`docs/hooks-setup.md`** (hook playback in Cursor), **`manifests/README.md`** (manifest layout), **`soundpack_builder/README.md`** (builder modules and tests).

**Search hints**

```bash
uv run --project soundpack_builder python -m soundpack_builder.pipeline.search_hints
uv run --project soundpack_builder python -m soundpack_builder.pipeline.search_hints --json
```

**Optional: inspect verified sites + hook-pack roster**

```bash
uv run --project soundpack_builder python -m soundpack_builder.pipeline.workflow --sourcing-report
uv run --project soundpack_builder python -m soundpack_builder.pipeline.workflow --sourcing-report --json
```

**Inputs to `candidates`**

| Input | Role |
|-------|------|
| `manifests/sound-sites.json` | Verified site ids (must match `candidateLinks.siteId`) |
| `manifests/sourcing-config.json` | `discovery` URL patterns, optional `universeAliases`, optional `fetch` (HTTP retries/delay for `--fetch-sound-pages`) |
| `manifests/universe-character-hook-candidates.json` | Per-character `candidateLinks` (optional `matchQuality` per link is passed through to candidate rows) |

**Output** (default **`manifests/candidates/`**)

| File | Contents |
|------|----------|
| `candidates.json` | Downloader-ready entries |
| `review.json` | Portals and search/tag/pack landing pages; ZIPs missing paths; sound pages that still need a direct URL (or successful `--fetch-sound-pages`) |
| `downloadable-all.json` | Deduplicated merge |
| `freesound-resolved.json` | *(After running `freesound_resolve`.)* Freesound API preview URLs for rows in `review.json` with `siteId: freesound` — merge `entries` into your download manifest |

**Freesound:** `manifests/sourcing-config.json` classifies single-sound URLs (`freesound.org/s/<id>/`, `freesound.org/people/.../sounds/<id>/`) as sound pages so `candidates` can try **`--fetch-sound-pages`**. For reliable direct preview links, set **`FREESOUND_API_KEY`** (see [Freesound API](https://freesound.org/help/developers/)) and run:

```bash
uv run --project soundpack_builder python -m soundpack_builder.tools.freesound_resolve
```

Then merge **`manifests/candidates/freesound-resolved.json`** → `entries` into **`manifests/download-manifest.json`** (or combine with `downloadable-all.json` before **`downloader`**).

```bash
uv run --project soundpack_builder python -m soundpack_builder.pipeline.candidates
uv run --project soundpack_builder python -m soundpack_builder.pipeline.candidates --fetch-sound-pages
```

**Reference dump (optional):** **`archive_entries`** writes **`manifests/generated/archive-entries.json`** — same game-archive source merged into **`candidates`**; not required for the main pipeline.

**Downloader manifest:** **`manifests/download-manifest.json`** — curated rows for **`downloader`** (default **`--manifest`**). Populate by hand, from reviewed **`candidates/`** output, or use **`downloadable-all.json`** as **`--manifest`**.

### Typical end-to-end flow

```bash
uv run --project soundpack_builder python -m soundpack_builder.pipeline.search_hints
# Edit sound-sites + universe-character-hook-candidates

uv run --project soundpack_builder python -m soundpack_builder.pipeline.candidates
# Review manifests/candidates/review.json; optionally resolve Freesound URLs:
#   set FREESOUND_API_KEY, then:
#   uv run --project soundpack_builder python -m soundpack_builder.tools.freesound_resolve
# Merge freesound-resolved.json entries + curated rows into download-manifest.json

uv run --project soundpack_builder python -m soundpack_builder.pipeline.downloader --manifest manifests/download-manifest.json
uv run --project soundpack_builder python -m soundpack_builder.pipeline.templates
uv run --project soundpack_builder python -m soundpack_builder.pipeline.validate
```

**Environment (optional):** `FREESOUND_API_KEY` — Freesound API token for **`freesound_resolve`** (can live in `soundpack_builder/.env`). `HF_TOKEN` — Hugging Face token for downloader transcript/classifier features (see **`soundpack_builder/README.md`**).

**Validate thresholds** (defaults warn 10s, fail 15s):

```bash
uv run --project soundpack_builder python -m soundpack_builder.pipeline.validate --warn-wav-seconds 12 --max-wav-seconds 18
```

### Console output

Several CLIs print **progress on stderr** so **stdout** stays clean for JSON (`candidates`, `archive_entries`, `validate`, etc.). Use **`--no-progress`** where supported.

### Notes

- Regenerate **`candidates/`** anytime; **`download-manifest.json`** is the usual gate for what the downloader fetches. See **`manifests/README.md`**.
- Downloader: **`--dry-run`**, **`--limit`**, **`--overwrite`** for safer iteration; **`--preset fast`** / **`--preset quality`** set Whisper model size for recommended configs; optional **`matchQuality`** on manifest rows nudges event mapping. Details: **`soundpack_builder/README.md`**.

## Platform support

- Windows: supported via PowerShell `MediaPlayer`.
- macOS: supported via `afplay`.
- Linux: supported via `paplay` (preferred) or `aplay` fallback.
- Playback runs as detached background processes to avoid blocking editor workflow.

## Tuning tips

- If it feels too noisy, remove `afterAgentThought` first.
- If tool sounds are too chatty, keep only `postToolUseFailure`.
- Use 2-3 sounds per event for variety; random selection is automatic.
- Keep success and failure sounds distinct so status is obvious.
- Prefer short sounds for `beforeSubmitPrompt` and `preToolUse`.

## Manual test

Run from repo root:

```bash
python .cursor/hooks/play-sound.py --test afterAgentResponse
```

## Switching soundpacks quickly

Run from repo root:

```bash
# list installed packs under sounds/ (active pack is marked with *)
python .cursor/hooks/switch-soundpack.py --list

# activate by slug (path under sounds/ with / replaced by -)
python .cursor/hooks/switch-soundpack.py warcraft-orc-peon

# nested pack example (Batman LEGO Dimensions under batman/batman-animated/...)
python .cursor/hooks/switch-soundpack.py batman-batman-animated-batman-lego-dimensions
```

`--list` only shows packs that actually exist on disk: each `sounds/**/sound-config.json`
is one activatable pack. Friendly titles come from `manifests/universe-character-hook-candidates.json`
when possible. Files in `configs/sound-config/*.json` are **templates** for the builder;
they are not listed until you download or generate audio and a pack config under `sounds/`.

Activation source order:

1. Installed pack: copy `sounds/**/sound-config.json` whose path matches the slug (hyphen-separated segments).
2. Otherwise: `configs/sound-config/<slug>.json`, preferring `sounds/<soundPack>/<soundSubdir>/sound-config.json` when that file exists (stderr notes when falling back to the template only).

The selected config is copied to `.cursor/hooks/sound-config.json`, so you do not
need to edit JSON manually.

To remap sounds quickly, edit only the `events` section and swap filenames between
event keys.
