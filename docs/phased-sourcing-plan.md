# Phased approach: sourcing hook sounds

Approved resources only. Order matters: **video games first** (indexed rips), then **cartoons/anime**, then **movies** (quote sites; review each clip).

Repo workflow stays: discover → `manifests/tier1-approved.json` → `python -m soundpack_builder.downloader` → `python -m soundpack_builder.templates` → `python -m soundpack_builder.validate`.

Discovery metadata and extra site IDs also live in `manifests/universe-character-hook-candidates.json` (`sourceSites`, per-character `candidateLinks`).

---

## Phase 1 — Video games

**Goal:** Fill packs from indexed game audio and mod communities (same pattern as existing packs pulled from game archives).

### Primary

- **[The Sounds Resource](https://sounds.spriters-resource.com)** — Console/PC → game title → character / “Player” / “Voices” asset pages; download ZIPs. Prefer character-named sets over huge misc dumps.

### Workflow

1. Open the **game hub**, then pick **character** (or class) asset pages.
2. Map clips to the ten hook files (`beforeSubmitPrompt_1/2` … `stop.wav`).
3. Promote URLs only after review into `manifests/tier1-approved.json`.

### Supplementary (approved toolbox)

Use when Sounds Resource has no good line for an event:

- [Freesound](https://freesound.org) — per-clip license
- [GameBanana](https://gamebanana.com)
- [Nexus Mods](https://www.nexusmods.com)
- [ModDB](https://www.moddb.com)
- [OpenGameArt](https://opengameart.org)
- [itch.io game audio](https://itch.io/game-assets/audio)
- [Steam Workshop](https://steamcommunity.com/workshop)

Also: [Zapsplat](https://www.zapsplat.com), [Pixabay SFX](https://pixabay.com/sound-effects/), [Mixkit](https://mixkit.co/free-sound-effects/), [BBC Sound Effects](https://sound-effects.bbcrewind.co.uk), [Unity Asset Store](https://assetstore.unity.com), [Unreal Marketplace](https://www.unrealengine.com/marketplace), [GameDev Market](https://www.gamedevmarket.net), [Kenney](https://kenney.nl/assets), [CurseForge](https://www.curseforge.com), [Internet Archive](https://archive.org) (extra diligence), [Sonniss GDC](https://sonniss.com/gameaudiogdc) — see `sourceSites` in `universe-character-hook-candidates.json` for roles and notes.

### Phase 1 exit criteria

- Each target character has enough **short** clips per hook event, or a note that Phase 2/3 must cover specific events.

---

## Phase 2 — Cartoons / anime

**Goal:** Cover cartoon/anime packs where Phase 1 left gaps.

### Approved resources

- **[Hanna-Barbera Sound Effects Library](https://soundeffects.fandom.com/wiki/Hanna-Barbera_Sound_Effects_Library)** — classic cartoon **SFX** (boings, footsteps, etc.); strong for non-dialog hooks or stylized packs; not character dialogue.
- **[Voicy — character sound effects](https://www.voicy.network/search/character-sound-effects)** — character-tagged clips; verify license and length per clip.

### Combine with Phase 1 for anime

Many anime lines still come from **licensed games** on [The Sounds Resource](https://sounds.spriters-resource.com) (fighting games, crossover titles). Use Phase 2 when no suitable game rip exists.

### Phase 2 exit criteria

- Packs sound **intentional** (dialog vs SFX mix). Each approved URL documented (manifest `note` or `candidateLinks` style metadata).

---

## Phase 3 — Movies

**Goal:** Film line stingers where games/cartoons cannot match the tone.

### Approved resources

- [movie-sounds.org](https://movie-sounds.org/)
- [Famous movie characters (audio)](https://movie-sounds.org/famous-characters)
- [moviesoundclips.net — movies A–Z](https://www.moviesoundclips.net/movies.php)
- [Voicy — character sound effects](https://www.voicy.network/search/character-sound-effects)

Read each site’s disclaimer/terms. Prefer **short** samples; keep movie-sourced entries easy to audit (e.g. `note` on manifest entries).

### Phase 3 exit criteria

- Movie-backed hooks are **explicitly approved** one-by-one, not bulk-downloaded.

---

## Cross-phase rules

| Rule | Notes |
|------|--------|
| Manifest-first | Only promote URLs into `tier1-approved.json` after review. |
| License | Tag entries: game rip / CC / site terms / personal-use-only as appropriate. |
| Hook fit | Map to events (send, thought, response, tool success/failure, stop), not only “cool line”. |
| Validate | Run `python -m soundpack_builder.validate` after each batch. |

---

## Suggested execution order (each phase)

1. **Inventory** — `(universe, character)` from `soundpack_builder/templates.py` (`TIER1_CHARACTERS`) or your expansion list.
2. **Search** — Sounds Resource hub first; Voicy / movie sites only where needed.
3. **Record** — `tier1-approved.json` (and optionally `candidateLinks` in the discovery manifest).
4. **Download** — `python -m soundpack_builder.downloader --manifest manifests/tier1-approved.json`
5. **Switch & spot-check** — `python .cursor/hooks/switch-soundpack.py <slug>` and exercise hooks.
