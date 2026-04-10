import tempfile
import unittest
from pathlib import Path

from soundpack_builder.core.pack_paths import (
    entry_matches_pack_key,
    pack_dir_under_sound_root,
    parse_pack_key,
    sound_subdir_for_pack,
)


class PackPathsTest(unittest.TestCase):
    def test_sound_subdir_no_slug(self) -> None:
        self.assertEqual(sound_subdir_for_pack("gandalf", ""), "gandalf")

    def test_sound_subdir_with_slug(self) -> None:
        self.assertEqual(sound_subdir_for_pack("gandalf", "pack"), "gandalf/pack")

    def test_pack_dir_same_slug_different_characters(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = pack_dir_under_sound_root(root, "batman", "the-joker", "same-slug")
            b = pack_dir_under_sound_root(root, "batman", "two-face", "same-slug")
            self.assertNotEqual(a.resolve(), b.resolve())

    def test_parse_pack_key_two_segments(self) -> None:
        self.assertEqual(parse_pack_key("batman/batman-animated"), ("batman", "batman-animated", None))

    def test_parse_pack_key_three_segments(self) -> None:
        self.assertEqual(
            parse_pack_key("batman/batman-animated/foo-slug"),
            ("batman", "batman-animated", "foo-slug"),
        )

    def test_parse_pack_key_rejects_bad_arity(self) -> None:
        with self.assertRaises(ValueError):
            parse_pack_key("only-one")
        with self.assertRaises(ValueError):
            parse_pack_key("a/b/c/d")

    def test_entry_matches_pack_key(self) -> None:
        self.assertTrue(
            entry_matches_pack_key(
                "u",
                "c",
                "slug-a",
                key_universe="u",
                key_character="c",
                key_slug="slug-a",
            )
        )
        self.assertFalse(
            entry_matches_pack_key(
                "u",
                "c",
                "slug-b",
                key_universe="u",
                key_character="c",
                key_slug="slug-a",
            )
        )
        self.assertTrue(
            entry_matches_pack_key(
                "u",
                "c",
                "anything",
                key_universe="u",
                key_character="c",
                key_slug=None,
            )
        )


if __name__ == "__main__":
    unittest.main()
