"""资源合并、构建矩阵和并行错误传播回归测试。"""

import tarfile
import tempfile
import unittest
from concurrent.futures import Future
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
from pathlib import Path
from subprocess import CalledProcessError
from threading import Thread
from unittest.mock import Mock, call, patch
from zipfile import ZipFile

from lyra.build import BuildTask
from lyra.combo import CombinationCalculator
from lyra.config_loader import ImagePackConfig
from lyra.downloader import Downloader
from lyra.gen_page import DownloadPageConfig, DownloadPageGenerator
from lyra.parallel import build_all_parallel
from lyra.paths import BuildPaths
from lyra.prepare import GamePreparer
from lyra.utils import extract_zip
from lyra.version import LyraVersion, package_filename
from lyra.warmup import ResourceWarmer


class BuildFlowTests(unittest.TestCase):
    def test_archive_download_respects_retry_after_and_recovers(self):
        archive = BytesIO()
        with tarfile.open(fileobj=archive, mode="w:gz") as tar:
            image = tarfile.TarInfo("project/imagepacks/b3s/body/test.png")
            image.size = 3
            tar.addfile(image, BytesIO(b"img"))
        statuses = iter((429, 429, 200))

        class ArchiveHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                status = next(statuses)
                self.send_response(status)
                if status == 429:
                    self.send_header("Retry-After", "10")
                self.end_headers()
                if status == 200:
                    self.wfile.write(archive.getvalue())

            def log_message(self, *_args):
                pass

        with HTTPServer(("127.0.0.1", 0), ArchiveHandler) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with (
                    tempfile.TemporaryDirectory() as directory,
                    patch("lyra.warmup.get_gitgud_commit_hash", return_value=None),
                    patch("urllib3.util.retry.time.sleep") as sleep,
                ):
                    paths = BuildPaths(workspace=Path(directory))
                    warmer = ResourceWarmer(paths)
                    pack = ImagePackConfig("besc", [f"http://127.0.0.1:{server.server_port}/b3s"])
                    warmer.config = replace(warmer.config, imagepacks={"besc": pack})
                    warmer._warmup_dolp_packs()
                    self.assertEqual(sleep.call_args_list, [call(10), call(10)])
                    image = paths.get_beautify_cache_dir("besc") / "img/body/test.png"
                    self.assertEqual(image.read_bytes(), b"img")
                    self.assertFalse(list(paths.temp_dir.glob("*.part")))
            finally:
                server.shutdown()
                thread.join()

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

    def test_prepare_reuses_images_and_keeps_normal_and_polyfill_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = BuildPaths(workspace=root)
            preparer = GamePreparer(paths)
            preparer.config = replace(preparer.config, base_mods=[], apk_replacements=[])
            files = {key: root / f"{key}.zip" for key in (
                "zip", "polyfill_zip", "apk", "polyfill_apk", "image_pack"
            )}
            with ZipFile(files["image_pack"], "w") as archive:
                archive.writestr("pack/img/same.png", b"overlay")
            for key in ("zip", "polyfill_zip", "apk", "polyfill_apk"):
                prefix = "assets/www/" if key.endswith("apk") else ""
                with ZipFile(files[key], "w") as archive:
                    archive.writestr(prefix + "index.html", key)
                    archive.writestr(prefix + "img/same.png", b"original")
                    archive.writestr(prefix + "img/keep.png", b"keep")
                    if key == "zip":
                        archive.writestr("obsolete.png", b"old")

            def decompile(command, **kwargs):
                extract_zip(Path(command[-3]), Path(command[-1]))

            with (
                patch("lyra.prepare.extract_zip", wraps=extract_zip) as extract,
                patch("lyra.prepare.subprocess.run", side_effect=decompile),
            ):
                preparer.prepare_all(files, {})
                self.assertEqual(
                    sum(call.args[0] == files["image_pack"] for call in extract.call_args_list),
                    1,
                )
                with ZipFile(files["zip"], "w") as archive:
                    archive.writestr("index.html", "zip")
                preparer.prepare_all(files, {})

            for polyfill, prefix in ((False, ""), (True, "polyfill_")):
                with ZipFile(paths.get_base_zip(polyfill)) as archive:
                    self.assertEqual(archive.read("index.html").decode(), prefix + "zip")
                    self.assertEqual(archive.read("img/same.png"), b"overlay")
                    self.assertNotIn("obsolete.png", archive.namelist())
                    if polyfill:
                        self.assertEqual(archive.read("img/keep.png"), b"keep")
                apk = paths.get_apk_dir(polyfill) / "assets/www"
                self.assertEqual((apk / "index.html").read_text(), prefix + "apk")
                self.assertEqual((apk / "img/same.png").read_bytes(), b"overlay")
                self.assertEqual((apk / "img/keep.png").read_bytes(), b"keep")
            self.assertEqual(
                {p.name for p in paths.prepare_dir.iterdir()}, {"apk", "apk-polyfill"}
            )

    def test_prepare_failure_cleans_extraction_and_preserves_base(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = BuildPaths(workspace=root)
            paths.ensure_dirs()
            preparer = GamePreparer(paths)
            preparer.config = replace(preparer.config, base_mods=[])
            source = root / "missing-html.zip"
            with ZipFile(source, "w") as archive:
                archive.writestr("img/test.png", b"image")
            base = paths.get_base_zip()
            base.write_bytes(b"existing base")
            with self.assertRaisesRegex(FileNotFoundError, "未找到游戏 HTML"):
                preparer.prepare_all({"zip": source, "image_pack": source}, {})
            self.assertEqual(base.read_bytes(), b"existing base")
            self.assertEqual(list(paths.prepare_dir.iterdir()), [])
            self.assertEqual(list(paths.base_dir.iterdir()), [base])

    def test_failed_apk_decode_preserves_previous_prepared_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = BuildPaths(workspace=Path(directory))
            apk_dir = paths.get_apk_dir()
            apk_dir.mkdir(parents=True)
            (apk_dir / "original").write_bytes(b"old")
            preparer = GamePreparer(paths)
            preparer.config = replace(preparer.config, base_mods=[])

            def fail(command, **kwargs):
                decoded = Path(command[-1])
                decoded.mkdir()
                (decoded / "partial").write_bytes(b"incomplete")
                raise CalledProcessError(1, command)

            with patch("lyra.prepare.subprocess.run", side_effect=fail):
                with self.assertRaises(CalledProcessError):
                    preparer.prepare_all({"apk": Path("input.apk")}, {})
            self.assertEqual((apk_dir / "original").read_bytes(), b"old")
            self.assertEqual(list(paths.prepare_dir.iterdir()), [apk_dir])

    def test_all_16_output_names_match_download_links(self):
        codes = CombinationCalculator().get_build_codes()
        self.assertEqual(
            set(codes),
            {
                "polyfill-3",
                "3",
                "35",
                "1026",
                "2",
                "259",
                "291",
                "1282",
            },
        )
        version = LyraVersion.from_tag("v0.5.12.13-1.0.1a-1023")
        config = DownloadPageConfig(version.tag, "owner", "repo")
        page = DownloadPageGenerator(config).generate()
        for kind in ("zip", "apk"):
            for code in codes:
                task = BuildTask.from_code_str(code, kind, version)
                filename = package_filename(
                    task.version, task.mod_code, task.pack_type, task.is_polyfill
                )
                with self.subTest(kind=kind, code=code):
                    self.assertEqual(
                        filename,
                        config.get_filename(task.mod_code, kind, task.is_polyfill),
                    )
                    self.assertIn(config.get_download_url(filename), page)

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
