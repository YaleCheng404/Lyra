"""资源合并、构建矩阵和并行错误传播回归测试。"""

import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import Mock, patch

from lyra.build import BuildTask, create_builder
from lyra.combo import CombinationCalculator
from lyra.config_loader import ImagePackConfig
from lyra.downloader import Downloader
from lyra.gen_page import DownloadPageConfig, DownloadPageGenerator
from lyra.parallel import build_all_parallel
from lyra.paths import BuildPaths
from lyra.prepare import GamePreparer
from lyra.utils import copy_directory
from lyra.version import LyraVersion
from lyra.warmup import ResourceWarmer


class BuildFlowTests(unittest.TestCase):
    @patch("lyra.downloader.download_file")
    def test_upstream_selects_distinct_normal_and_polyfill_apks(self, download):
        names = [
            "DoL-ModLoader-polyfill.APK",
            "DoL-ModLoader.APK",
            "DoL-ModLoader-polyfill.zip",
            "DoL-ModLoader.zip",
            "GameOriginalImagePack.mod.zip",
            "ModI18N.mod.zip",
        ]
        with tempfile.TemporaryDirectory() as directory:
            downloader = Downloader(BuildPaths(workspace=Path(directory)))
            release = {
                "tag_name": "latest",
                "assets": [
                    {
                        "name": name,
                        "browser_download_url": f"https://example.test/{name}",
                    }
                    for name in names
                ],
            }
            with patch.object(downloader, "_get_github_release", return_value=release):
                files = downloader.download_from_chs_repo()
        self.assertEqual(files["apk"].name, "DoL-ModLoader.APK")
        self.assertEqual(files["polyfill_apk"].name, "DoL-ModLoader-polyfill.APK")
        self.assertEqual(download.call_count, 6)

    def test_image_pack_config_controls_merge_order_fixes_and_removals(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = BuildPaths(workspace=Path(directory))
            paths.ensure_dirs()
            for name, content in (("first", b"first"), ("second", b"second")):
                source = paths.temp_dir / f"dolp-{name}" / "img"
                source.mkdir(parents=True)
                (source / "keep.png").write_bytes(content)
                (source / "Shoulder.png").write_bytes(b"rename")
                (source / "remove.png").write_bytes(b"remove")
            pack = ImagePackConfig(
                "besc",
                ["https://example.test/first", "https://example.test/second"],
                {"img/Shoulder.png": "img/shoulder.png"},
                ["img/remove.png"],
            )
            ResourceWarmer(paths)._process_image_pack(pack)
            result = paths.get_beautify_cache_dir("besc") / "img"
            self.assertEqual((result / "keep.png").read_bytes(), b"second")
            self.assertIn("shoulder.png", [path.name for path in result.iterdir()])
            self.assertFalse((result / "remove.png").exists())

    def test_directory_merge_overwrites_and_preserves_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, dest = root / "source", root / "dest"
            (source / "nested").mkdir(parents=True)
            dest.mkdir()
            (source / "same").write_bytes(b"new")
            (source / "nested" / "new").write_bytes(b"nested")
            (dest / "same").write_bytes(b"old")
            (dest / "keep").write_bytes(b"keep")
            copy_directory(source, dest)
            self.assertEqual((dest / "same").read_bytes(), b"new")
            self.assertEqual((dest / "keep").read_bytes(), b"keep")
            self.assertEqual((dest / "nested" / "new").read_bytes(), b"nested")

    def test_all_28_output_names_match_download_links(self):
        codes = CombinationCalculator().get_build_codes()
        self.assertEqual(
            set(codes),
            {
                "polyfill-3",
                "3",
                "35",
                "514",
                "1026",
                "2",
                "259",
                "291",
                "770",
                "1282",
                "2050",
                "2306",
                "4098",
                "4354",
            },
        )
        version = LyraVersion.from_tag("v0.5.12.13-1.0.1a-1023")
        config = DownloadPageConfig(version.tag, "owner", "repo")
        page = DownloadPageGenerator(config).generate()
        for kind in ("zip", "apk"):
            for code in codes:
                task = BuildTask.from_code_str(code, kind, version)
                filename = create_builder(task).get_output_name()
                with self.subTest(kind=kind, code=code):
                    self.assertEqual(
                        filename,
                        config.get_filename(task.mod_code, kind, task.is_polyfill),
                    )
                    self.assertIn(config.get_download_url(filename), page)

    def test_polyfill_apk_uses_its_own_upstream_file(self):
        preparer = GamePreparer(BuildPaths())
        files = {"apk": Path("normal.apk"), "polyfill_apk": Path("polyfill.apk")}
        with patch.object(preparer, "_process_apk_version") as process:
            preparer._prepare_apk(files, {})
        self.assertEqual(
            [call.args[0] for call in process.call_args_list],
            [files["apk"], files["polyfill_apk"]],
        )
        self.assertEqual(
            [call.kwargs["polyfill"] for call in process.call_args_list], [False, True]
        )

    @patch("lyra.parallel.CombinationCalculator")
    @patch("lyra.parallel.ProcessPoolExecutor")
    def test_parallel_counts_failed_results_and_worker_exceptions(
        self, pool, calculator
    ):
        calculator.return_value.get_build_codes.return_value = ["3", "2", "polyfill-3"]
        tasks = []

        def submit(worker, task, verbose):
            tasks.append(task)
            future = Future()
            if task.is_polyfill:
                future.set_exception(RuntimeError("worker stopped"))
            else:
                future.set_result((task.mod_code == 2, "build failed"))
            return future

        executor = Mock()
        executor.submit.side_effect = submit
        pool.return_value.__enter__.return_value = executor
        self.assertEqual(build_all_parallel(BuildPaths(), max_workers=2), (2, 4))
        self.assertEqual([task.pack_type for task in tasks], ["zip"] * 3 + ["apk"] * 3)

    def test_invalid_worker_count_is_rejected(self):
        with self.assertRaises(ValueError):
            build_all_parallel(BuildPaths(), max_workers=0)


if __name__ == "__main__":
    unittest.main()
