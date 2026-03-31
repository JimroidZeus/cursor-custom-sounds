from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from soundpack_builder.pipeline.candidates import (
    DEFAULT_SOURCING_CONFIG,
    URL_KIND_ARCHIVE_ZIP,
    URL_KIND_DIRECT_MEDIA,
    URL_KIND_PORTAL,
    URL_KIND_SOUND_PAGE,
    _compile_regex_list,
    _discovery_rules,
    _iter_discovery_links,
    _regex_first_audio_match,
    _pack_manifest_fields,
    _crawler_queries_from_universe,
    build_candidate_manifests,
    classify_url,
    extract_audio_urls_from_html,
    list_zip_audio_members,
)
from soundpack_builder.core.hook_events import discovery_target_filename
from soundpack_builder.core.config import BuilderConfig


class CandidatesTests(unittest.TestCase):
    def test_auto_crawler_queries_skip_when_direct_zip_exists(self) -> None:
        universe_data = {
            "characters": [
                {
                    "universe": "dc",
                    "character": "batman",
                    "candidateLinks": [
                        {
                            "url": "https://sounds.spriters-resource.com/media/assets/401/403988.zip",
                            "siteId": "spriters-resource-sounds",
                        }
                    ],
                    "discoveryHints": {
                        "suggestedSourceSiteIds": ["spriters-resource-sounds"],
                    },
                },
                {
                    "universe": "dc",
                    "character": "joker",
                    "candidateLinks": [
                        {
                            "url": "https://sounds.spriters-resource.com/wii_u/legodimensions/asset/403999/",
                            "siteId": "spriters-resource-sounds",
                        }
                    ],
                    "discoveryHints": {
                        "suggestedSourceSiteIds": ["spriters-resource-sounds"],
                    },
                },
            ]
        }
        queries = _crawler_queries_from_universe(
            universe_data,
            supported_site_ids={"spriters-resource-sounds"},
            max_results=5,
        )
        self.assertEqual(len(queries), 1)
        self.assertEqual(queries[0].character, "joker")

    def test_discovery_target_filename_sequence(self) -> None:
        self.assertEqual(discovery_target_filename(0), "discovery_001.wav")
        self.assertEqual(discovery_target_filename(99), "discovery_100.wav")

    def test_iter_discovery_links_merges_flat_and_legacy_events(self) -> None:
        data = {
            "characters": [
                {
                    "universe": "u",
                    "character": "c",
                    "candidateLinks": [
                        {"url": "https://cdn.example.com/a.wav", "siteId": "kenney"},
                    ],
                    "events": {
                        "stop": {
                            "candidateLinks": [
                                {"url": "https://cdn.example.com/b.mp3", "siteId": "kenney"},
                            ],
                        },
                    },
                }
            ]
        }
        rows = _iter_discovery_links(data)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["url"], "https://cdn.example.com/a.wav")
        self.assertEqual(rows[1]["url"], "https://cdn.example.com/b.mp3")
        self.assertNotIn("hookEvent", rows[0])

    def test_iter_discovery_links_includes_cross_franchise_packs(self) -> None:
        data = {
            "characters": [],
            "crossFranchiseOneVoicePacks": [
                {
                    "universe": "x",
                    "character": "_bundle",
                    "candidateLinks": [
                        {"url": "https://example.com/z.zip", "siteId": "kenney"},
                    ],
                }
            ],
        }
        rows = _iter_discovery_links(data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["character"], "_bundle")

    def test_site_id_alias_siteID(self) -> None:
        data = {
            "characters": [
                {
                    "universe": "u",
                    "character": "c",
                    "candidateLinks": [
                        {"url": "https://example.com/a.zip", "siteID": "kenney"},
                    ],
                }
            ]
        }
        rows = _iter_discovery_links(data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["siteId"], "kenney")

    def test_classify_url_generic(self) -> None:
        rules = {
            "soundPage": _compile_regex_list([r"example\.com/sound/\d+"], label="x"),
            "htmlAudio": [],
        }
        self.assertEqual(
            classify_url("https://cdn.example.com/files/pack.zip?x=1", rules),
            URL_KIND_ARCHIVE_ZIP,
        )
        self.assertEqual(classify_url("https://x/audio.wav", rules), URL_KIND_DIRECT_MEDIA)
        self.assertEqual(
            classify_url("https://example.com/sound/42", rules),
            URL_KIND_SOUND_PAGE,
        )
        self.assertEqual(classify_url("https://example.com/search?q=a", rules), URL_KIND_PORTAL)

    def test_distinct_candidate_labels_separate_discovery_packs(self) -> None:
        """Different ``label`` values for the same character get separate packLabelSlug + counters."""
        repo = Path(__file__).resolve().parents[2]
        cfg = BuilderConfig.defaults(repo)
        sourcing = {
            "discovery": {
                "soundPageUrlRegexes": [],
                "htmlEmbeddedAudioRegexes": [],
            }
        }
        universe = {
            "characters": [
                {
                    "universe": "u",
                    "character": "c",
                    "candidateLinks": [
                        {
                            "url": "https://cdn.example.com/first.mp3",
                            "siteId": "testsite",
                            "label": "Variant A",
                        },
                        {
                            "url": "https://cdn.example.com/second.mp3",
                            "siteId": "testsite",
                            "label": "Variant B",
                        },
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "sourcing.json").write_text(json.dumps(sourcing), encoding="utf-8")
            (root / "sites.json").write_text(
                json.dumps({"sites": [{"id": "testsite"}]}),
                encoding="utf-8",
            )
            (root / "universe.json").write_text(json.dumps(universe), encoding="utf-8")
            out = root / "out"
            report = build_candidate_manifests(
                cfg,
                sourcing_config_path=root / "sourcing.json",
                sound_sites_path=root / "sites.json",
                universe_path=root / "universe.json",
                out_dir=out,
                fetch_sound_pages=False,
                progress=False,
            )
            self.assertTrue(report["ok"])
            data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
            disc = [
                e
                for e in data["entries"]
                if e.get("source") == "discovery"
                and e.get("universe") == "u"
                and e.get("character") == "c"
            ]
            self.assertEqual(len(disc), 2)
            by_slug = {e.get("packLabelSlug"): e for e in disc}
            self.assertEqual(set(by_slug), {"variant-a", "variant-b"})
            self.assertEqual(by_slug["variant-a"]["targetFile"], "discovery_001.wav")
            self.assertEqual(by_slug["variant-b"]["targetFile"], "discovery_001.wav")

    def test_pack_manifest_fields_empty_without_slug(self) -> None:
        self.assertEqual(_pack_manifest_fields({"label": "x"}), {})

    def test_build_minimal_candidates_no_universe(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        cfg = BuilderConfig.defaults(repo)
        sourcing = repo / "manifests" / DEFAULT_SOURCING_CONFIG
        sound_sites = repo / "manifests" / "sound-sites.json"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            report = build_candidate_manifests(
                cfg,
                sourcing_config_path=sourcing,
                sound_sites_path=sound_sites,
                universe_path=repo / "manifests" / "nonexistent-discovery.json",
                out_dir=out,
                fetch_sound_pages=False,
                progress=False,
            )
            self.assertTrue(report["ok"])
            data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
            self.assertGreater(len(data["entries"]), 80)
            self.assertEqual(data["entries"][0]["source"], "archive")

    def test_discovery_rules_loads_from_repo_manifest(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        rules = _discovery_rules(json.loads((repo / "manifests" / DEFAULT_SOURCING_CONFIG).read_text()))
        self.assertTrue(len(rules["soundPage"]) >= 1)
        self.assertTrue(len(rules["htmlAudio"]) >= 1)

    def test_extract_audio_urls_resolves_relative_src(self) -> None:
        html = '<audio src="/files/voice.wav"></audio><a href="https://cdn.example.com/x.mp3">x</a>'
        page = "https://voicy.network/pages/foo"
        urls = extract_audio_urls_from_html(html, page)
        self.assertIn("https://voicy.network/files/voice.wav", urls)
        self.assertIn("https://cdn.example.com/x.mp3", urls)

    def test_list_zip_audio_members_sorted(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("z/first.wav", b"x")
            zf.writestr("a/second.mp3", b"y")
        buf.seek(0)
        got = list_zip_audio_members(buf.read())
        self.assertEqual(got, ["a/second.mp3", "z/first.wav"])

    def test_spriters_zip_expands_to_path_in_archive_rows(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("Voice/a.wav", b"x")
            zf.writestr("Voice/b.wav", b"y")
        zip_bytes = buf.getvalue()

        repo = Path(__file__).resolve().parents[2]
        cfg = BuilderConfig.defaults(repo)
        sourcing = {
            "discovery": {
                "soundPageUrlRegexes": [],
                "htmlEmbeddedAudioRegexes": [],
            }
        }
        universe = {
            "characters": [
                {
                    "universe": "portal",
                    "character": "glados",
                    "candidateLinks": [
                        {
                            "url": "https://sounds.spriters-resource.com/media/assets/392/395531.zip",
                            "siteId": "spriters-resource-sounds",
                            "label": "GLaDOS pack",
                        },
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "sourcing.json").write_text(json.dumps(sourcing), encoding="utf-8")
            (root / "sites.json").write_text(
                json.dumps({"sites": [{"id": "spriters-resource-sounds"}]}),
                encoding="utf-8",
            )
            (root / "universe.json").write_text(json.dumps(universe), encoding="utf-8")
            out = root / "out"
            with patch("soundpack_builder.pipeline.candidates.http_get_bytes", return_value=zip_bytes):
                report = build_candidate_manifests(
                    cfg,
                    sourcing_config_path=root / "sourcing.json",
                    sound_sites_path=root / "sites.json",
                    universe_path=root / "universe.json",
                    out_dir=out,
                    fetch_sound_pages=False,
                    progress=False,
                    inventory_spriters_zips=True,
                )
            self.assertTrue(report["ok"])
            data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
            disc = [e for e in data["entries"] if e.get("source") == "discovery"]
            self.assertEqual(len(disc), 2)
            paths = sorted(e.get("pathInArchive") for e in disc)
            self.assertEqual(paths, ["Voice/a.wav", "Voice/b.wav"])
            self.assertEqual(disc[0]["targetFile"], "discovery_001.wav")
            self.assertEqual(disc[1]["targetFile"], "discovery_002.wav")

    def test_regex_fallback_uses_capture_group_for_src(self) -> None:
        html = '<embed src="https://static.example.com/quote.wav" />'
        rules = _discovery_rules(
            {
                "discovery": {
                    "htmlEmbeddedAudioRegexes": [r'src=["\']([^"\']+\.(?:wav|mp3))["\']'],
                }
            }
        )
        got = _regex_first_audio_match(html, rules)
        self.assertEqual(got, "https://static.example.com/quote.wav")

    def test_site_discovery_overrides_global_for_classification(self) -> None:
        """Site-specific soundPageUrlRegexes in sound-sites.json override global sourcing-config."""
        global_rules = {
            "soundPage": _compile_regex_list([r"global-only\.com/x"], label="g.sp"),
            "htmlAudio": [],
        }
        with tempfile.TemporaryDirectory() as td:
            sites = Path(td) / "sites.json"
            sites.write_text(
                json.dumps(
                    {
                        "sites": [
                            {
                                "id": "tests-only-site",
                                "discovery": {
                                    "soundPageUrlRegexes": [r"site-specific\.example\.com/p/\d+"],
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            from soundpack_builder.pipeline.candidates import _effective_discovery_rules, _site_discovery_maps

            smap = _site_discovery_maps(sites)
            eff = _effective_discovery_rules("tests-only-site", global_rules, smap)
            self.assertTrue(any(p.search("https://site-specific.example.com/p/99") for p in eff["soundPage"]))
            self.assertFalse(any(p.search("https://site-specific.example.com/p/99") for p in global_rules["soundPage"]))

    def test_language_filter_drops_jp_path_when_default_eng(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        cfg = BuilderConfig.defaults(repo)
        sourcing = {
            "discovery": {
                "soundPageUrlRegexes": [],
                "htmlEmbeddedAudioRegexes": [],
            }
        }
        universe = {
            "characters": [
                {
                    "universe": "u",
                    "character": "c",
                    "candidateLinks": [
                        {
                            "url": "https://cdn.example.com/voice_jp.wav",
                            "siteId": "testsite",
                        },
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "sourcing.json").write_text(json.dumps(sourcing), encoding="utf-8")
            (root / "sites.json").write_text(
                json.dumps({"sites": [{"id": "testsite"}]}),
                encoding="utf-8",
            )
            (root / "universe.json").write_text(json.dumps(universe), encoding="utf-8")
            out = root / "out"
            build_candidate_manifests(
                cfg,
                sourcing_config_path=root / "sourcing.json",
                sound_sites_path=root / "sites.json",
                universe_path=root / "universe.json",
                out_dir=out,
                fetch_sound_pages=False,
                progress=False,
                language_filter_codes={"ENG"},
            )
            data = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
            disc = [e for e in data["entries"] if e.get("source") == "discovery"]
            self.assertEqual(len(disc), 0)

            build_candidate_manifests(
                cfg,
                sourcing_config_path=root / "sourcing.json",
                sound_sites_path=root / "sites.json",
                universe_path=root / "universe.json",
                out_dir=out,
                fetch_sound_pages=False,
                progress=False,
                language_filter_codes={"ENG", "JP"},
            )
            data2 = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
            disc2 = [e for e in data2["entries"] if e.get("source") == "discovery"]
            self.assertEqual(len(disc2), 1)
            self.assertEqual(disc2[0].get("languageCode"), "JP")


if __name__ == "__main__":
    unittest.main()
