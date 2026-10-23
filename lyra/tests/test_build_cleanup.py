"""构建分支、原子输出和失败清理的行为回归。"""

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from lyra.build import BuildTask, PackageBuilder
from lyra.paths import BuildPaths
from lyra.utils import create_zip
from lyra.version import LyraVersion, package_filename


class BuildCleanupTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.paths = BuildPaths(workspace=Path(directory.name))
        self.paths.ensure_dirs()
        self.version = LyraVersion.from_tag("v0.5.12.13-1.0.1a-1023")
        for polyfill in (False, True):
            source = self.paths.workspace / f"source-{polyfill}"
            source.mkdir()
            content = f"window.modDataValueZipList = [];\npolyfill={polyfill}"
            (source / "game.html").write_text(content, encoding="utf-8")
            create_zip(source, self.paths.get_base_zip(polyfill))
            apk_dir = self.paths.get_apk_dir(polyfill) / "assets/www"
            apk_dir.mkdir(parents=True)
            (apk_dir / "index.html").write_text(content, encoding="utf-8")

    def builder(self, kind="zip", polyfill=False):
        return PackageBuilder(BuildTask(kind, 2, polyfill, self.version, self.paths))

    def assert_cleaned(self, builder):
        self.assertFalse(builder.work_dir.exists())
        self.assertFalse(builder.lyra_mod_path.exists())
        self.assertFalse(self.paths.get_temp_apk(2, builder.task.is_polyfill).exists())
        self.assertFalse(
            self.paths.get_signed_dir(2, builder.task.is_polyfill).exists()
        )
        self.assertEqual(list(self.paths.output_dir.glob("*.part")), [])

    def test_zip_reads_normal_and_polyfill_bases_and_cleans_work_files(self):
        for polyfill in (False, True):
            with self.subTest(polyfill=polyfill):
                builder = self.builder(polyfill=polyfill)
                result = builder.build()
                self.assertTrue(result.success, result.error)
                with zipfile.ZipFile(result.output_path) as archive:
                    html = archive.read("game.html").decode("utf-8")
                self.assertIn(f"polyfill={polyfill}", html)
                self.assertNotIn("modDataValueZipList = []", html)
                self.assert_cleaned(builder)

    def test_packaging_failure_preserves_existing_output(self):
        builder = self.builder()
        output = self.paths.output_dir / package_filename(self.version, 2, "zip")
        output.write_bytes(b"existing release")

        def fail_after_write(source, partial):
            partial.write_bytes(b"incomplete")
            raise OSError("disk write failed")

        with patch("lyra.build.create_zip", side_effect=fail_after_write):
            result = builder.build()
        self.assertFalse(result.success)
        self.assertIn("disk write failed", result.error)
        self.assertEqual(output.read_bytes(), b"existing release")
        self.assert_cleaned(builder)

    def test_apk_branches_recompile_sign_and_clean(self):
        for polyfill in (False, True):
            with self.subTest(polyfill=polyfill):
                builder = self.builder("apk", polyfill)

                def recompile():
                    html = builder.html_path.read_text(encoding="utf-8")
                    self.assertIn(f"polyfill={polyfill}", html)
                    tmp = self.paths.get_temp_apk(2, polyfill)
                    tmp.write_bytes(b"unsigned")
                    return tmp

                def sign(tmp):
                    self.assertEqual(tmp.read_bytes(), b"unsigned")
                    signed_dir = self.paths.get_signed_dir(2, polyfill)
                    signed_dir.mkdir(parents=True)
                    signed = signed_dir / "signed.apk"
                    signed.write_bytes(b"signed")
                    return signed

                with (
                    patch.object(builder, "_recompile", side_effect=recompile),
                    patch.object(builder, "_sign", side_effect=sign),
                ):
                    result = builder.build()
                self.assertTrue(result.success, result.error)
                self.assertEqual(result.output_path.read_bytes(), b"signed")
                self.assert_cleaned(builder)

    def test_signing_failure_cleans_unsigned_apk_and_signer_directory(self):
        builder = self.builder("apk")
        tmp = self.paths.get_temp_apk(2)
        signed_dir = self.paths.get_signed_dir(2)

        def recompile():
            tmp.write_bytes(b"unsigned")
            return tmp

        def fail_signing(_tmp):
            signed_dir.mkdir(parents=True)
            (signed_dir / "signer.tmp").write_bytes(b"partial")
            raise RuntimeError("signer failed")

        with (
            patch.object(builder, "_recompile", side_effect=recompile),
            patch.object(builder, "_sign", side_effect=fail_signing),
        ):
            result = builder.build()
        self.assertFalse(result.success)
        self.assertIn("signer failed", result.error)
        self.assertEqual(list(self.paths.output_dir.iterdir()), [])
        self.assert_cleaned(builder)
