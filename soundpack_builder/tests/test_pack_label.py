from __future__ import annotations

import unittest

from soundpack_builder.core.pack_label import pack_label_key_and_slug


class PackLabelTests(unittest.TestCase):
    def test_empty_label_is_default_pack(self) -> None:
        self.assertEqual(pack_label_key_and_slug(None), ("", None))
        self.assertEqual(pack_label_key_and_slug(""), ("", None))
        self.assertEqual(pack_label_key_and_slug("   "), ("", None))

    def test_distinct_labels_distinct_slugs(self) -> None:
        a = pack_label_key_and_slug("Pack A")
        b = pack_label_key_and_slug("Pack B")
        self.assertNotEqual(a[0], b[0])
        self.assertEqual(a[1], "pack-a")
        self.assertEqual(b[1], "pack-b")

    def test_long_label_uses_short_path_segment(self) -> None:
        long = (
            "beforeSubmitPrompt — miked312 — Borg Voices (Star Trek franchise VO pack; "
            'not "make it so")'
        )
        key, slug = pack_label_key_and_slug(long)
        self.assertIsNotNone(slug)
        assert slug is not None
        self.assertLessEqual(len(slug), 40, msg="avoid Windows path length failures")
        self.assertNotEqual(slug, pack_label_key_and_slug(long + " x")[1])

    def test_cursor_hook_tag_stripped_from_slug(self) -> None:
        key, slug = pack_label_key_and_slug("[afterAgentResponse] GamingWithJumbo — desk slam")
        self.assertIsNotNone(slug)
        assert slug is not None
        self.assertFalse(slug.startswith("afteragentresponse"))
        self.assertIn("gamingwithjumbo", slug)

    def test_non_hook_bracket_prefix_not_stripped(self) -> None:
        """Only HOOK_EVENT_ORDER tags are removed; other [brackets] stay in the slug."""
        _, slug = pack_label_key_and_slug("[special edition] My Pack")
        self.assertIsNotNone(slug)
        assert slug is not None
        self.assertIn("special", slug)
        self.assertIn("edition", slug)


if __name__ == "__main__":
    unittest.main()
