"""生成 ZIP 基包和 APK 解包目录。"""

import logging
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.modmagic import add_mods_to_html, replace_mod_by_id

from .config_loader import Replacement, load_build_config
from .paths import BuildPaths
from .utils import create_zip, extract_zip, safe_remove

logger = logging.getLogger(__name__)


def patch_modloader_code(html_path: Path):
    # 重载时跳过 ModLoader 本身，避免再次初始化加载器。
    marker = "const remodloader = modReadCache.clone();"
    content = html_path.read_text(encoding="utf-8")
    if marker in content:
        replacement = (
            marker + "\n        remodloader.filterItems("
            "(mod) => mod.bootJson && mod.bootJson.name !== 'ModLoader');"
        )
        html_path.write_text(content.replace(marker, replacement), encoding="utf-8")
        logger.info("已修补 ModLoader: %s", html_path.name)


class GamePreparer:
    def __init__(self, paths: BuildPaths):
        self.paths = paths
        self.config = load_build_config()

    def prepare_all(
        self, downloaded_files: dict[str, Path], extra_mods: dict[str, Path]
    ) -> None:
        for mod in self.config.base_mods:
            if mod.required and (
                mod.key not in extra_mods or not extra_mods[mod.key].is_file()
            ):
                raise FileNotFoundError(f"缺少必需 Mod: {mod.name or mod.key}")

        self.paths.prepare_dir.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=self.paths.prepare_dir, prefix="images-") as directory:
            images = None
            if image_pack := downloaded_files.get("image_pack"):
                root = extract_zip(image_pack, Path(directory))
                images = root / "img"
                if not images.exists():
                    images = next((p for p in root.glob("*/img") if p.is_dir()), None)

            for key, polyfill in (("zip", False), ("polyfill_zip", True)):
                if key in downloaded_files:
                    self._prepare_zip(downloaded_files[key], images, extra_mods, polyfill)

            for key, polyfill in (("apk", False), ("polyfill_apk", True)):
                if key not in downloaded_files:
                    raise FileNotFoundError(f"未找到上游资源: {key}")
                self._prepare_apk(downloaded_files[key], images, extra_mods, polyfill)

    def _prepare_zip(
        self, source: Path, images: Path | None, extra_mods: dict[str, Path], polyfill: bool
    ) -> None:
        output = self.paths.get_base_zip(polyfill)
        partial = output.with_name(output.name + ".part")
        try:
            with TemporaryDirectory(dir=self.paths.prepare_dir, prefix="zip-") as directory:
                root = extract_zip(source, Path(directory))
                if images:
                    shutil.copytree(images, root / "img", dirs_exist_ok=True)
                html = next(root.glob("*.html"), None)
                if html is None:
                    raise FileNotFoundError(f"ZIP 中未找到游戏 HTML: {source}")
                self._inject_mods(html, extra_mods)
                create_zip(root, partial)
            partial.replace(output)
            logger.info("基包已创建: %s", output)
        finally:
            partial.unlink(missing_ok=True)

    def _prepare_apk(
        self, source: Path, images: Path | None, extra_mods: dict[str, Path], polyfill: bool
    ) -> None:
        apk_dir = self.paths.get_apk_dir(polyfill)
        with TemporaryDirectory(dir=self.paths.prepare_dir, prefix="apk-") as directory:
            decoded = Path(directory) / "decoded"
            logger.info("反编译 APK: %s", source)
            subprocess.run(
                ["java", "-jar", str(self.paths.apktool_path), "d", str(source), "-o", str(decoded)],
                check=True,
                text=True,
            )
            self._apply_apk_replacements(decoded)
            html_dir = decoded / "assets" / "www"
            if images:
                shutil.copytree(images, html_dir / "img", dirs_exist_ok=True)
            self._inject_mods(html_dir / "index.html", extra_mods)
            safe_remove(apk_dir)
            decoded.replace(apk_dir)
        logger.info("APK 目录已准备: %s", apk_dir)

    def _apply_apk_replacements(self, apk_dir: Path) -> None:
        by_file: dict[str, list[Replacement]] = defaultdict(list)
        for replacement in self.config.apk_replacements:
            by_file[replacement.file].append(replacement)

        for filename, replacements in by_file.items():
            path = apk_dir / filename
            if not path.exists():
                logger.warning("文件不存在: %s", path)
                continue

            original = content = path.read_text(encoding="utf-8")
            for rule in replacements:
                content = content.replace(rule.pattern, rule.replacement)
            if content != original:
                path.write_text(content, encoding="utf-8")
                logger.info("已修改: %s", path)

    def _inject_mods(self, html_path: Path, extra_mods: dict[str, Path]) -> None:
        mods_to_add = []
        for mod in self.config.base_mods:
            if mod.key not in extra_mods:
                continue
            if mod.inject == "replace":
                replace_mod_by_id(html_path, mod.replace_slot, extra_mods[mod.key])
            else:
                mods_to_add.append(extra_mods[mod.key])

        if mods_to_add:
            add_mods_to_html(html_path, mods_to_add)
        patch_modloader_code(html_path)
