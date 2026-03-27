"""Tests for soundpack_builder.config (HF_TOKEN / dotenv)."""

from __future__ import annotations

import importlib
import os
import unittest
from unittest.mock import patch

import soundpack_builder.config as config


class TestHfToken(unittest.TestCase):
    def test_hf_token_returns_stripped_value(self) -> None:
        with patch.dict(os.environ, {"HF_TOKEN": "  test-token  "}):
            self.assertEqual(config.hf_token(), "test-token")

    def test_hf_token_returns_none_when_empty(self) -> None:
        with patch.dict(os.environ, {"HF_TOKEN": ""}):
            self.assertIsNone(config.hf_token())

    def test_hf_token_returns_none_when_whitespace_only(self) -> None:
        with patch.dict(os.environ, {"HF_TOKEN": "   \t  "}):
            self.assertIsNone(config.hf_token())

    def test_load_dotenv_called_on_config_import(self) -> None:
        # Reload picks up `from dotenv import load_dotenv` while patched.
        with patch("dotenv.load_dotenv") as mock_load:
            importlib.reload(config)
            try:
                mock_load.assert_called()
                args, kwargs = mock_load.call_args
                path_arg = args[0] if args else kwargs.get("dotenv_path")
                self.assertTrue(
                    str(path_arg).endswith(".env"),
                    msg=f"expected .env path, got args={args} kwargs={kwargs}",
                )
            finally:
                importlib.reload(config)


if __name__ == "__main__":
    unittest.main()
