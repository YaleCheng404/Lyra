"""Mod 编辑与构建注入的行为回归测试。"""

import base64
import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from lyra.build import BuildTask, PackageBuilder
from lyra.paths import BuildPaths
from lyra.utils import create_zip
from scripts import modmagic


class ModMagicTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.html = self.root / "game.html"
        self.html.write_text(
            'before\nwindow.modDataValueZipList = ["b2xk"];\nafter', encoding="utf-8"
        )
        self.mod = self.root / "new.mod.zip"
        with zipfile.ZipFile(self.mod, "w") as archive:
            archive.writestr("boot.json", json.dumps({"name": "New", "version": "1.0"}))
        self.encoded = base64.b64encode(self.mod.read_bytes()).decode("ascii")

    def mods(self):
        return modmagic.extract_mod_list(self.html.read_text(encoding="utf-8"))

    def test_add_replace_reorder_remove_preserve_surrounding_html(self):
        modmagic.add_mods_to_html(self.html, [self.mod])
        self.assertEqual(self.mods(), ["b2xk", self.encoded])
        modmagic.add_mods_to_html(self.html, [self.mod], "start")
        self.assertEqual(self.mods(), [self.encoded, "b2xk", self.encoded])
        modmagic.reorder_mods(self.html, [1, 0])
        self.assertEqual(self.mods(), ["b2xk", self.encoded])
        modmagic.replace_mod_by_id(self.html, 0, self.mod)
        self.assertEqual(self.mods(), [self.encoded] * 2)
        modmagic.remove_mods(self.html, [0])
        self.assertEqual(self.mods(), [self.encoded])
        content = self.html.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("before\n"))
        self.assertTrue(content.endswith("\nafter"))

    def test_invalid_inputs_leave_original_bytes(self):
        cases = [
            lambda: modmagic.add_mods_to_html(self.html, [self.root / "missing.zip"]),
            lambda: modmagic.add_mods_to_html(self.html, [self.mod], "invalid"),
            lambda: modmagic.replace_mod_by_id(self.html, -1, self.mod),
            lambda: modmagic.replace_mod_by_id(self.html, 1, self.mod),
            lambda: modmagic.reorder_mods(self.html, [0, 1]),
            lambda: modmagic.remove_mods(self.html, [-1]),
        ]
        original = self.html.read_bytes()
        for operation in cases:
            with (
                self.subTest(operation=operation),
                self.assertRaises((ValueError, OSError)),
            ):
                operation()
            self.assertEqual(self.html.read_bytes(), original)

    def test_missing_or_invalid_array_leaves_original_bytes(self):
        for content in (
            "no array",
            "window.modDataValueZipList = [broken];",
            "window.modDataValueZipList = [1];",
        ):
            with self.subTest(content=content):
                self.html.write_text(content, encoding="utf-8")
                original = self.html.read_bytes()
                with self.assertRaises(ValueError):
                    modmagic.add_mods_to_html(self.html, [self.mod])
                self.assertEqual(self.html.read_bytes(), original)

    def test_list_reports_boot_metadata(self):
        modmagic.replace_mod_by_id(self.html, 0, self.mod)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            modmagic.list_mods(self.html)
        self.assertIn("[0] New v1.0", output.getvalue())

    def test_cli_keeps_add_positions_and_returns_failure(self):
        for position in ("--start", "--end"):
            with patch(
                "sys.argv",
                ["modmagic.py", "add", str(self.html), str(self.mod), position],
            ):
                self.assertEqual(modmagic.main(), 0)
        with patch("sys.argv", ["modmagic.py", "remove", str(self.html), "99"]):
            self.assertEqual(modmagic.main(), 1)

    def test_injection_failure_fails_zip_build(self):
        paths = BuildPaths(workspace=self.root / "build")
        paths.ensure_dirs()
        source = self.root / "base"
        source.mkdir()
        (source / "game.html").write_text("no mod array", encoding="utf-8")
        create_zip(source, paths.get_base_zip())
        result = PackageBuilder(BuildTask("zip", 2, paths=paths)).build()
        self.assertFalse(result.success)
        self.assertIn("modDataValueZipList", result.error)
        self.assertEqual(list(paths.output_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
