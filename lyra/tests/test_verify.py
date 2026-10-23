"""发布检查必须拒绝遗漏、变更、乱序和多余产物。"""

import base64
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from lyra.build import BuildTask, create_builder
from lyra.combo import CombinationCalculator
from lyra.config_loader import load_build_config
from lyra.paths import BuildPaths
from lyra.verify import verify_packages
from lyra.version import LyraVersion, VersionInfo, VersionRegistry


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.paths = BuildPaths(workspace=Path(self.directory.name))
        self.paths.ensure_dirs()
        self.version = LyraVersion.from_tag("v0.5.12.13-1.0.1a-1023")
        registry = VersionRegistry()
        self.payloads = []
        for mod in load_build_config().base_mods:
            if not mod.required:
                continue
            name = mod.key + (".mod.zip" if mod.key in {"maplebirch", "dynamicest"} else ".modpack")
            path = self.paths.base_dir / "mods" / name
            path.parent.mkdir(exist_ok=True)
            if name.endswith(".zip"):
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("boot.json", json.dumps({"name": mod.key}))
            else:
                path.write_bytes(b"JeremieModLoader" + mod.key.encode().ljust(140, b"\0"))
            self.payloads.append(base64.b64encode(path.read_bytes()).decode("ascii"))
            registry.add(VersionInfo(mod.name, "test", mod.github_repo, name))
        registry.save(self.paths.versions_file)
        self.targets = []
        for code in CombinationCalculator().get_build_codes():
            for kind in ("zip", "apk"):
                task = BuildTask.from_code_str(code, kind, self.version, self.paths)
                path = self.paths.output_dir / create_builder(task).get_output_name()
                html_name = "assets/www/index.html" if kind == "apk" else "game.html"
                self.targets.append((path, html_name))
                self.write_package(path, html_name, self.payloads)

    def write_package(self, path, html_name, payloads):
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(html_name, "window.modDataValueZipList = " + json.dumps(payloads) + ";")

    def test_complete_release_and_notes(self):
        report = verify_packages(self.paths, self.version)
        self.assertEqual(len(report), 16)
        self.assertEqual(len(report[0]["required_mods"]), 5)
        self.assertIn("Dynamicest", (self.paths.output_dir / "release-notes.md").read_text(encoding="utf-8"))

    def test_payload_changes_missing_duplicate_and_order_are_rejected(self):
        path, html_name = self.targets[0]
        for payloads in (self.payloads[:-1], self.payloads + self.payloads[:1],
                         list(reversed(self.payloads)), ["YmFk"] + self.payloads[1:]):
            with self.subTest(payloads=payloads):
                self.write_package(path, html_name, payloads)
                with self.assertRaises(ValueError):
                    verify_packages(self.paths, self.version)

    def test_missing_or_extra_artifact_rejected(self):
        extra = self.paths.output_dir / "obsolete-goose.zip"
        extra.write_bytes(b"old")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            verify_packages(self.paths, self.version)
        extra.unlink()
        self.targets[0][0].unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            verify_packages(self.paths, self.version)


if __name__ == "__main__":
    unittest.main()
