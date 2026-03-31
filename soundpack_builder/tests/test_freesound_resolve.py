from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from soundpack_builder.pipeline.candidates import (
    URL_KIND_PORTAL,
    URL_KIND_SOUND_PAGE,
    _discovery_rules,
    classify_url,
)
from soundpack_builder.tools.freesound_resolve import (
    parse_freesound_url,
    pick_preview_url,
    resolve_review_items,
)


class FreesoundResolveTests(unittest.TestCase):
    def test_parse_sound_short(self) -> None:
        p = parse_freesound_url("https://freesound.org/s/243601/")
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.kind, "sound")
        self.assertEqual(p.sound_id, 243601)

    def test_parse_user_sound(self) -> None:
        p = parse_freesound_url("https://freesound.org/people/x/sounds/99/")
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.sound_id, 99)

    def test_parse_search(self) -> None:
        p = parse_freesound_url("https://freesound.org/search/?q=picard+make+it+so")
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.kind, "search")
        self.assertEqual(p.search_query, "picard make it so")

    def test_parse_pack(self) -> None:
        p = parse_freesound_url("https://freesound.org/people/joe93barlow/packs/6726/")
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.kind, "pack")
        self.assertEqual(p.pack_id, 6726)

    def test_parse_tag(self) -> None:
        p = parse_freesound_url("https://freesound.org/browse/tags/Harry-Potter/")
        self.assertIsNotNone(p)
        assert p is not None
        self.assertEqual(p.kind, "tag")
        self.assertEqual(p.tag_slug, "Harry-Potter")

    def test_pick_preview_url(self) -> None:
        u = pick_preview_url(
            {
                "previews": {
                    "preview-hq-mp3": "https://cdn.freesound.org/previews/1/1_123-hq.mp3",
                }
            }
        )
        self.assertEqual(u, "https://cdn.freesound.org/previews/1/1_123-hq.mp3")

    def test_classify_freesound_sound_page_from_repo_config(self) -> None:
        repo = Path(__file__).resolve().parents[2]
        raw = json.loads((repo / "manifests" / "sourcing-config.json").read_text(encoding="utf-8"))
        rules = _discovery_rules(raw)
        self.assertEqual(
            classify_url("https://freesound.org/s/243601/", rules),
            URL_KIND_SOUND_PAGE,
        )
        self.assertEqual(
            classify_url("https://freesound.org/people/foo/sounds/123/", rules),
            URL_KIND_SOUND_PAGE,
        )
        self.assertEqual(
            classify_url("https://freesound.org/search/?q=test", rules),
            URL_KIND_PORTAL,
        )

    def test_resolve_review_items_mocks_sound(self) -> None:
        items = [
            {
                "universe": "u",
                "character": "c",
                "hookEvent": "beforeSubmitPrompt",
                "siteId": "freesound",
                "url": "https://freesound.org/s/1/",
                "label": "x",
                "proposedTargetFile": "beforeSubmitPrompt_1.wav",
            }
        ]
        fake_sound = {
            "id": 1,
            "name": "test",
            "previews": {"preview-hq-mp3": "https://cdn.example.com/p.mp3"},
        }
        with mock.patch(
            "soundpack_builder.tools.freesound_resolve.resolve_parsed_to_sound_dict",
            return_value=fake_sound,
        ):
            entries, skipped = resolve_review_items(items, "fake-token", delay_sec=0.0)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["url"], "https://cdn.example.com/p.mp3")
        self.assertEqual(skipped, [])


if __name__ == "__main__":
    unittest.main()
