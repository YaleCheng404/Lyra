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
        source = self.paths.workspace / "source"
        source.mkdir()
        (source / "game.html").write_text(
            "window.modDataValueZipList = [];\n// ZIP base", encoding="utf-8"
        )
        create_zip(source, self.paths.get_base_zip())
        apk_dir = self.paths.get_apk_dir() / "assets/www"
        apk_dir.mkdir(parents=True)
        (apk_dir / "index.html").write_text(
            "window.modDataValueZipList = [];\n// APK base", encoding="utf-8"
        )

    def builder(self, kind="zip"):
        return PackageBuilder(BuildTask(kind, 2, self.version, self.paths))

    def assert_cleaned(self, builder):
        self.assertFalse(builder.work_dir.exists())
        self.assertFalse(builder.lyra_mod_path.exists())
        self.assertFalse(self.paths.get_temp_apk(2).exists())
        self.assertFalse(self.paths.get_signed_dir(2).exists())
        self.assertEqual(list(self.paths.output_dir.glob("*.part")), [])

    def test_zip_reads_base_and_cleans_work_files(self):
        builder = self.builder()
        result = builder.build()
        self.assertTrue(result.success, result.error)
        with zipfile.ZipFile(result.output_path) as archive:
            html = archive.read("game.html").decode("utf-8")
        self.assertIn("// ZIP base", html)
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

    def test_apk_recompiles_signs_and_cleans(self):
        builder = self.builder("apk")

        def recompile():
            html = builder.html_path.read_text(encoding="utf-8")
            self.assertIn("// APK base", html)
            tmp = self.paths.get_temp_apk(2)
            tmp.write_bytes(b"unsigned")
            return tmp

        def sign(tmp):
            self.assertEqual(tmp.read_bytes(), b"unsigned")
            signed_dir = self.paths.get_signed_dir(2)
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
