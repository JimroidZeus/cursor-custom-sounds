# Sound sourcing (simplified)

**Pipeline:** `search_hints` → *(optional: crawl)* → *(edit manifests)* → `candidates` → *(curate download-manifest)* → `downloader` → `templates` → `validate`. Run `python -m soundpack_builder.pipeline.workflow` for a printable checklist; `python -m soundpack_builder.pipeline.workflow --sourcing-report` prints verified sites and the hook-pack roster.

## What you maintain

### Editing manifests in detail

**A. `manifests/sound-sites.json`**

- **`sites`** is an array of objects. Each site must have:
  - **`id`** — Stable slug (letters, numbers, hyphens). This exact string is what you put in **`candidateLinks.siteId`** elsewhere. Example: `"freesound"`, `"spriters-resource-sounds"`.
  - **`name`**, **`url`**, **`notes`** — Human-facing; **`url`** is the site home or main index (not a per-clip URL).
- Add a new row **before** referencing that **`id`** from the universe manifest. If **`candidates`** logs “approved site ids” and skips your links, the **`siteId`** on the link is missing from this file.

- Optional **`discovery`** on a site: **`soundPageUrlRegexes`** and **`htmlEmbeddedAudioRegexes`** — used by **`candidates`** for that `siteId`; if a list is empty or omitted, **`sourcing-config.json`** provides the fallback patterns.

**B. `manifests/universe-character-hook-candidates.json` (schema v3)**

- Top-level **`cursorHookEvents`** lists the hook names the runtime cares about (documentation / tooling).
- Each item under **`characters`** should include:
  - **`universe`**, **`character`** — Slugs used everywhere else (`sounds/<universe>/<character>/`, downloader rows, templates). Use lowercase with hyphens (e.g. `star-trek`, `jean-luc-picard`).
  - **`displayName`** — Optional; for humans only.
  - **`candidateLinks`** — Array of discovery URLs (sound pages, search pages, ZIPs, or direct media). **`candidates`** does **not** assign hook events here; it emits neutral filenames like **`discovery_001.wav`** per character. Hook assignment happens after download (e.g. **`downloader --recommend-config`** / transcript mapping).
- Each link object should have:
  - **`url`**, **`siteId`** (must match **`sound-sites.json`**), optional **`label`**, optional **`matchQuality`**, optional **`languageCode`** (2+ letters, e.g. `ENG`, `JP`).
- **Legacy:** manifests may still nest links under **`events.<hookEvent>.candidateLinks`**. **`candidates`** merges those with **`candidateLinks`** at read time (legacy blocks are optional). Run **`python -m soundpack_builder.tools.normalize_manifests`** once to flatten into **`candidateLinks`** only.

**C. Hook-pack roster vs. full universe file**

- **`search_hints`** and **`templates`** use **`HOOK_PACK_CHARACTERS`** in `soundpack_builder/templates.py`. Characters listed there get search URLs and template stubs.
- The universe JSON may list additional characters for documentation; any character with **`candidateLinks`** (or legacy **`events`**) feeds **`candidates`**.

**D. After large JSON edits**

- Run **`python -m soundpack_builder.tools.normalize_manifests`** to flatten legacy **`events`** blocks and keep a consistent shape.

---

1. **`manifests/sound-sites.json`** — Verified site registry (**§A** above).

2. **`manifests/universe-character-hook-candidates.json`** — Per-character **`candidateLinks`** (schema v3; **§B–C** above). Optional **`discoveryHints`** (`suggestedWavFiles`, `searchQueries`, `suggestedSourceSiteIds`) are hints for you / **`search_hints`**; they are not consumed by **`candidates`**. Optional **`matchQuality`** on a link is passed through **`candidates`** into downloader rows. **`sourceSitesRef`** points at **`sound-sites.json`**. Re-normalize after hand-edits: `uv run --project soundpack_builder python -m soundpack_builder.tools.normalize_manifests`.

3. **`manifests/sourcing-config.json`** — Technical settings: **`discovery`** regexes as **defaults** for classifying URLs (ZIP vs direct audio vs sound page) and for **fallback** media URL extraction from HTML when a site omits its own patterns; optional **`universeAliases`**; optional **`fetch`** (`maxRetries`, `delayBetweenRequestsSec`) for HTTP when running **`candidates --fetch-sound-pages`**. Freesound single-sound URLs (`/s/<id>/`, `/people/.../sounds/<id>/`) are listed as sound-page patterns so they are not lumped in with generic portals. You rarely need to edit this unless you add hosts with unusual URL shapes or tune network behavior.

4. **`manifests/download-manifest.json`** (schema v2) — **`entries`** array for the downloader; each row may include **`source`: `download-manifest`** and optional **`matchQuality`** (same semantics as in discovery manifests). Legacy **`sourcingPhase`** / **`sourcingSlug`** fields were removed. Optional **`languageCode`**; the downloader defaults to **`--language-codes ENG`** and skips entries whose resolved language is not in the allowlist; entries with no inferred or explicit language pass through.

Game-archive rows come from the builder’s internal list (`archive_entries` → `manifests/generated/archive-entries.json`); they are merged into the same `candidates` pipeline output. Layout: **`manifests/README.md`**.

**Character roster:** `HOOK_PACK_CHARACTERS` in `soundpack_builder/templates.py` lists every pack that gets templates and `search_hints` URLs. It includes the quote-focused cast already described in `universe-character-hook-candidates.json` (Star Trek, LOTR, Portal, Marvel, etc.) plus existing game packs (Warcraft, TF2, …). Add or remove rows there if you narrow the scope.

**Hook filenames and slot counts** (per-event WAV names, order of slots) live in **`soundpack_builder/hook_events.py`** so `templates`, `candidates`, and mapping logic stay aligned.

## What the builder does

- **`python -m soundpack_builder.pipeline.search_hints`** — Prints **DuckDuckGo search URLs** for each hook-pack character × each verified site. Nothing is scraped automatically; open links in a browser, find clips, then paste URLs into the universe manifest.

- **`python -m soundpack_builder.crawl`** — Optional site-specific crawler to collect discovery links into `manifests/candidates/<site-id>-crawl.json`; with `--apply`, appends deduped links into `universe-character-hook-candidates.json`. First implementation supports `spriters-resource-sounds`: search `browse/?name=<character>` → parse `/asset/<id>/` results → resolve `.zip` links from asset pages. Step-by-step for adding another site: [`docs/plans/add-site-crawler.md`](plans/add-site-crawler.md).

- **`python -m soundpack_builder.pipeline.candidates`** — Reads verified sites + sourcing config + universe manifest, classifies each candidate link (per-site **`discovery`** regexes with global fallback), and writes **`manifests/candidates/`** (`candidates.json`, `review.json`, `downloadable-all.json`). With **`--fetch-sound-pages`**, fetches sound-page URLs, parses HTML for audio links (including relative `src`/`href`), applies optional **`fetch`** retries/delay from **`sourcing-config.json`**, and falls back to regex rules when needed. Optional **`matchQuality`** on a **`candidateLinks`** entry is copied onto discovery rows for the downloader. Default **`--language-codes ENG`** filters discovery rows by explicit or path-inferred language (`--no-language-filter` to disable).

- **`python -m soundpack_builder.tools.freesound_resolve`** — *(Optional.)* For rows in **`review.json`** with **`siteId: freesound`**, calls the **Freesound API** and writes **`manifests/candidates/freesound-resolved.json`** with preview MP3 URLs suitable for the downloader. Set **`FREESOUND_API_KEY`** (see [Freesound API](https://freesound.org/help/developers/)); then merge **`entries`** into **`download-manifest.json`**. Search, tag browse, and pack URLs resolve to the **first** API hit (documented in **`soundpack_builder/tools/freesound_resolve.py`**).

- **`python -m soundpack_builder.pipeline.downloader`** — Downloads from **`manifests/download-manifest.json`** (or **`--manifest`** pointing at `candidates/downloadable-all.json` after review). Same language filter as **`candidates`** (`--language-codes` / `--no-language-filter`) using manifest **`languageCode`** and path inference. Can generate per-pack **`sound-config.json`** recommendations using Whisper + optional zero-shot classifier; maps WAVs to hook events with **global** slot assignment (each file used at most once when there are enough clips). Use **`--preset quality`** / **`--preset fast`** as shorthand for Whisper model size; **`matchQuality`** on an entry nudges ranking. See **`soundpack_builder/README.md`** for flags.

- **`python -m soundpack_builder.pipeline.templates`** and **`python -m soundpack_builder.pipeline.validate`** — Unchanged.

## Flow

1. Verify or extend **`sound-sites.json`**.
2. Run **`search_hints`** and/or **`crawl`**, then add/curate **`candidateLinks`** for the hook-pack characters (see `soundpack_builder/templates.py` → `HOOK_PACK_CHARACTERS`).
3. Run **`candidates`**, review **`review.json`**, promote good rows into **`download-manifest.json`**. For Freesound-heavy review queues, run **`freesound_resolve`** and merge **`freesound-resolved.json`** **`entries`** into the download manifest.
4. Run **`downloader`** → **`templates`** → **`validate`**.

## Related documentation

| Doc | Contents |
|-----|----------|
| **[`README.md`](../README.md)** (repo root) | End-to-end commands, manifest workflow, validation |
| **[`soundpack_builder/README.md`](../soundpack_builder/README.md)** | Module table, `--no-progress`, tests |
| **[`manifests/README.md`](../manifests/README.md)** | Canonical vs generated paths under `manifests/` |
| **[`hooks-setup.md`](hooks-setup.md)** | Cursor hook runtime (`play-sound.py`, `.cursor/hooks/`) — not the downloader pipeline |
| **[`plans/add-site-crawler.md`](plans/add-site-crawler.md)** | How to implement and register a new `crawl` site module |

**Utilities:** `python -m soundpack_builder.pipeline.workflow` (pipeline checklist), `workflow --sourcing-report`, `python -m soundpack_builder.tools.normalize_manifests` (schema v2 after bulk JSON edits), `python -m soundpack_builder.tools.archive_entries` (optional ZIP reference dump), `python -m soundpack_builder.tools.freesound_resolve` (Freesound API resolution for **`review.json`**).
