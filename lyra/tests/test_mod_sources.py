"""基础 Mod 同步、缓存失效和注入的回归测试。"""

import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

from lyra.combo import CombinationCalculator
from lyra.config_loader import BaseModConfig, load_build_config
from lyra.downloader import Downloader
from lyra.paths import BuildPaths
from lyra.prepare import GamePreparer


class ModSourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.paths = BuildPaths(workspace=self.root)
        self.downloader = Downloader(self.paths)

    def asset(self, name="pack.modpack", content=b"old"):
        return {"name": name, "id": 1, "updated_at": "2026-10-23T00:00:00Z",
                "size": len(content), "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
                "browser_download_url": "https://example.test/" + name}

    def response(self, content):
        response = Mock()
        response.headers = {"content-length": str(len(content))}
        response.iter_content.return_value = [content]
        return response

    @patch("lyra.utils.requests.get")
    def test_same_name_same_size_refresh_and_unchanged_cache(self, get):
        get.return_value = self.response(b"old")
        asset = self.asset()
        dest = self.downloader._download_mod_asset(asset, self.root)
        self.downloader._download_mod_asset(asset, self.root)
        self.assertEqual(get.call_count, 1)
        get.return_value = self.response(b"new")
        self.downloader._download_mod_asset(self.asset(content=b"new"), self.root)
        self.assertEqual(dest.read_bytes(), b"new")
        self.assertEqual(get.call_count, 2)

    @patch("lyra.utils.requests.get")
    def test_metadata_cache_and_insufficient_identity(self, get):
        get.return_value = self.response(b"old")
        asset = self.asset()
        asset.pop("digest")
        self.downloader._download_mod_asset(asset, self.root)
        self.downloader._download_mod_asset(asset, self.root)
        self.assertEqual(get.call_count, 1)
        asset["updated_at"] = "changed"
        self.downloader._download_mod_asset(asset, self.root)
        self.assertEqual(get.call_count, 2)
        asset.pop("id")
        self.downloader._download_mod_asset(asset, self.root)
        self.downloader._download_mod_asset(asset, self.root)
        self.assertEqual(get.call_count, 4)

    @patch("lyra.utils.requests.get")
    def test_bad_download_keeps_previous_payload_and_metadata(self, get):
        get.return_value = self.response(b"old")
        dest = self.downloader._download_mod_asset(self.asset(), self.root)
        metadata = dest.with_name(dest.name + ".source.json")
        previous = metadata.read_bytes()
        get.return_value = self.response(b"bad")
        with self.assertRaises(ValueError):
            self.downloader._download_mod_asset(self.asset(content=b"new"), self.root)
        self.assertEqual(dest.read_bytes(), b"old")
        self.assertEqual(metadata.read_bytes(), previous)
        asset = self.asset(content=b"new")
        asset.pop("digest")
        asset["size"] = 20
        with self.assertRaises(ValueError):
            self.downloader._download_mod_asset(asset, self.root)
        self.assertEqual(dest.read_bytes(), b"old")

    @patch("lyra.downloader.load_build_config")
    def test_main_audio_distinct_and_share_one_release_query(self, config):
        mods = [m for m in load_build_config().base_mods if m.key.startswith("deadwood-")]
        config.return_value = SimpleNamespace(base_mods=mods)
        names = ["deadwood-reblooms-audio-0.5.12.13-v2.4.5.modpack",
                 "deadwood-reblooms-0.5.12.13-v2.4.5.modpack"]
        release = {"tag_name": "v2.4.5", "assets": [self.asset(n) for n in names]}
        with patch.object(self.downloader, "_get_github_release", return_value=release) as fetch:
            with patch.object(self.downloader, "_download_mod_asset", side_effect=lambda a, d: d / a["name"]):
                files = self.downloader.download_extra_mods()
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(files["deadwood-reblooms"].name, names[1])
        self.assertEqual(files["deadwood-reblooms-audio"].name, names[0])
        self.assertEqual({v.version for v in self.downloader.registry}, {"v2.4.5"})

    @patch("lyra.downloader.load_build_config")
    def test_required_source_errors_propagate(self, config):
        config.return_value = SimpleNamespace(base_mods=[BaseModConfig("required", "owner/repo", required=True)])
        for release in (None, {"assets": []}, {"prerelease": True},
                        {"assets": [self.asset("a.mod.zip"), self.asset("b.mod.zip")]}):
            with self.subTest(release=release), patch.object(self.downloader, "_get_github_release", return_value=release):
                with self.assertRaises(RuntimeError):
                    self.downloader.download_extra_mods()
        with patch.object(self.downloader, "_get_github_release", return_value={"assets": [self.asset("a.mod.zip")]}):
            with patch.object(self.downloader, "_download_mod_asset", side_effect=OSError("offline")):
                with self.assertRaisesRegex(RuntimeError, "offline"):
                    self.downloader.download_extra_mods()

    def test_required_missing_before_any_package_changes(self):
        preparer = GamePreparer(self.paths)
        with patch.object(preparer, "_prepare_zip_base") as process:
            with self.assertRaises(FileNotFoundError):
                preparer.prepare_all({}, {})
            process.assert_not_called()

    def test_all_required_payloads_are_embedded_in_order_for_each_html(self):
        mods = {}
        expected = []
        for index, mod in enumerate(load_build_config().base_mods):
            if mod.required:
                path = self.root / (mod.key + ".modpack")
                path.write_bytes(b"JeremieModLoader" + bytes([index]) * 150)
                mods[mod.key] = path
                expected.append(base64.b64encode(path.read_bytes()).decode("ascii"))
        from scripts.modmagic import extract_mod_list
        for name in ("normal.html", "polyfill.html", "apk.html", "polyfill-apk.html"):
            html = self.root / name
            html.write_text("window.modDataValueZipList = [];", encoding="utf-8")
            GamePreparer(self.paths)._inject_mods(html, mods)
            self.assertEqual(extract_mod_list(html.read_text(encoding="utf-8")), expected)

    def test_removed_bits_rejected_in_whitelist_and_polyfill(self):
        calculator = CombinationCalculator()
        self.assertTrue(calculator._should_skip(514))
        with patch.object(type(calculator), "combinations_config", new_callable=PropertyMock) as config:
            config.return_value = SimpleNamespace(whitelist=[514], recommended=[], blacklist=[], polyfill_enabled=False)
            with self.assertRaisesRegex(ValueError, "未定义"):
                calculator.calculate()
            config.return_value = SimpleNamespace(whitelist=[], recommended=[], blacklist=[], polyfill_enabled=True, polyfill_code=2050)
            with self.assertRaisesRegex(ValueError, "未定义"):
                calculator.calculate()


if __name__ == "__main__":
    unittest.main()
