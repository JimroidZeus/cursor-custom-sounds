# Manifests layout

## Canonical (edit / review)

| File | Purpose |
|------|---------|
| [sound-sites.json](sound-sites.json) | Verified `siteId` registry; optional per-site `discovery.soundPageUrlRegexes` / `htmlEmbeddedAudioRegexes` (candidates merges with global fallback from [sourcing-config.json](sourcing-config.json)) |
| [sourcing-config.json](sourcing-config.json) | Global `discovery` regex defaults; optional `universeAliases`, optional `fetch` (HTTP retries / delay for `candidates --fetch-sound-pages`) |
| [download-manifest.json](download-manifest.json) | **Downloader** manifest — curated rows (`schemaVersion` 2, `entries`); optional `languageCode` (2+ letter code, e.g. ENG, JP) |
| [universe-character-hook-candidates.json](universe-character-hook-candidates.json) | Discovery: flat per-character `candidateLinks` + optional `discoveryHints` (`schemaVersion` 3); optional `languageCode` on links; run `normalize_manifests` if you still have legacy `events.*` blocks |

Machine-readable index: [manifest-index.json](manifest-index.json).

**Pipeline overview** (full detail in [`docs/sound-sourcing.md`](../docs/sound-sourcing.md)): `search_hints` → `candidates` → `downloader` → `templates` → `validate`. Print steps: `uv run --project soundpack_builder python -m soundpack_builder.pipeline.workflow`.

## Generated (do not hand-edit; safe to delete)

| Path | Produced by |
|------|-------------|
| `generated/archive-entries.json` | `python -m soundpack_builder.tools.archive_entries` — game ZIP rows from builder code (same logical source as rows merged into `candidates`) |
| `candidates/*.json` | `python -m soundpack_builder.pipeline.candidates` — classified pipeline output (`candidates.json`, `review.json`, `downloadable-all.json`) |
| `candidates/*-crawl.json` | `python -m soundpack_builder.crawl` — optional crawler-discovered candidate links before curation/apply |
| `candidates/freesound-resolved.json` | `python -m soundpack_builder.tools.freesound_resolve` — optional; **`FREESOUND_API_KEY`** required. Merge **`entries`** into **`download-manifest.json`**. |

`generated/` and `candidates/` JSON files are gitignored when produced locally; regenerate with the commands above.

## Workflow

1. Curate **`download-manifest.json`** for what the downloader should fetch.
2. Maintain **`universe-character-hook-candidates.json`** for discovery URLs; run **`candidates`** to refresh `candidates/`.
3. Run **`archive_entries`** only when you want a fresh dump of builder-defined game-archive rows (optional reference).

Normalize JSON shape after bulk edits:

`uv run --project soundpack_builder python -m soundpack_builder.tools.normalize_manifests`
