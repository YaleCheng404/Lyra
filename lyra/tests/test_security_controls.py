"""Regression tests for build-input security controls."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main
from lyra.config_loader import load_build_config
from lyra.gen_page import DownloadPageConfig, DownloadPageGenerator
from lyra.utils import _safe_tar_name, download_file
from lyra.version import LyraVersion


class SecurityControlTests(unittest.TestCase):
    def test_tool_hashes_are_pinned(self):
        config = load_build_config()
        self.assertEqual(len(config.apktool_sha256), 64)
        self.assertEqual(len(config.uber_apk_signer_sha256), 64)

    @patch("lyra.utils.requests.get")
    def test_download_verifies_sha256(self, get):
        content = b"verified release asset"
        response = Mock()
        response.headers = {"content-length": str(len(content))}
        response.iter_content.return_value = [content]
        get.return_value = response

        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "tool.jar"
            download_file(
                "https://example.test/tool.jar",
                dest,
                quiet=True,
                expected_sha256=hashlib.sha256(content).hexdigest(),
            )
            self.assertEqual(dest.read_bytes(), content)

        response.raise_for_status.assert_called_once_with()

    @patch("lyra.utils.requests.get")
    def test_download_rejects_wrong_sha256(self, get):
        response = Mock()
        response.headers = {}
        response.iter_content.return_value = [b"different bytes"]
        get.return_value = response

        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "tool.jar"
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                download_file(
                    "https://example.test/tool.jar",
                    dest,
                    quiet=True,
                    expected_sha256="0" * 64,
                )
            self.assertFalse(dest.exists())
            self.assertFalse(dest.with_name("tool.jar.part").exists())

    def test_tar_path_validation(self):
        self.assertEqual(_safe_tar_name("root/a/b/image.png", 3), "image.png")
        for name in ("/absolute/image.png", "root/../image.png", r"root\image.png"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                _safe_tar_name(name, 0)

    def test_release_tag_parser_is_strict(self):
        version = LyraVersion.from_tag("v0.5.7.9-5.0.2a-0112")
        self.assertEqual(version.tag, "v0.5.7.9-5.0.2a-0112")
        for tag in ("v0.5.7.9-5.0.2a-0112-extra", "not-a-release"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                LyraVersion.from_tag(tag)

    def test_native_markdown_table_renderer(self):
        config = DownloadPageConfig(
            version="v0.5.7.9-5.0.2a-0112",
            github_owner="owner",
            github_repo="repo",
        )
        content = DownloadPageGenerator(config).generate()
        self.assertIn("|版本选择|ZIP|APK|", content)
        self.assertIn("https://github.com/owner/repo/releases/download", content)

    @patch("requests.get")
    def test_check_rejects_invalid_upstream_tag(self, get):
        response = Mock()
        response.json.return_value = {"tag_name": "not-a-release"}
        get.return_value = response
        args = SimpleNamespace(
            verbose=False,
            source_repo="upstream/repo",
            github_owner="owner",
            github_repo="repo",
            github_output=None,
        )

        self.assertEqual(main.cmd_check(args), 1)
        response.raise_for_status.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
