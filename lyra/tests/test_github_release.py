"""Tests for GitHub release asset selection."""

import unittest
from unittest.mock import Mock, patch

from lyra.utils import get_github_release_asset


class GitHubReleaseAssetTests(unittest.TestCase):
    @staticmethod
    def response(assets):
        response = Mock()
        response.json.return_value = {"tag_name": "mod", "assets": assets}
        return response

    @patch("lyra.utils.requests.get")
    def test_selects_highest_matching_version(self, get):
        get.return_value = self.response(
            [
                {
                    "name": "AUfemale.model_v0.8.0.zip",
                    "browser_download_url": "https://example.test/0.8.0.zip",
                },
                {
                    "name": "AUfemale.model_v0.10.0.zip",
                    "browser_download_url": "https://example.test/0.10.0.zip",
                },
                {
                    "name": "AUmale.model_v9.0.0.zip",
                    "browser_download_url": "https://example.test/other.zip",
                },
            ]
        )

        result = get_github_release_asset(
            "AOKIUTAGE/UTAGEsDOL3.0", "AUfemale.model", "mod"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.version, "v0.10.0")
        self.assertEqual(result.url, "https://example.test/0.10.0.zip")
        get.return_value.raise_for_status.assert_called_once_with()

    @patch("lyra.utils.requests.get")
    def test_returns_none_without_a_matching_asset(self, get):
        get.return_value = self.response([])

        result = get_github_release_asset("owner/repo", "missing")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
