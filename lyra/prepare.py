"""预处理模块。"""

import logging
from pathlib import Path

from scripts.modmagic import add_mods_to_html, replace_mod_by_id

from .config_loader import load_build_config
from .paths import BuildPaths
from .utils import (
    copy_directory,
    create_zip,
    extract_zip,
    run_command,
    safe_remove,
)
from .version import VersionRegistry

logger = logging.getLogger(__name__)


class ApkProcessor:
    """APK 处理器。"""

    def __init__(self, paths: BuildPaths):
        """初始化 APK 处理器。"""
        self.paths = paths
        self.config = load_build_config()

    def decompile(self, apk_path: Path, dest_dir: Path) -> Path:
        """反编译 APK。"""
        logger.info(f"反编译 APK: {apk_path}")

        if dest_dir.exists():
            safe_remove(dest_dir)

        apktool_path = self.paths.apktool_path
        run_command(
            [
                "java",
                "-jar",
                str(apktool_path),
                "d",
                str(apk_path),
                "-o",
                str(dest_dir),
            ]
        )

        return dest_dir

    def apply_replacements(self, apk_dir: Path):
        """应用配置中的替换规则。"""
        logger.info("应用 APK 配置替换...")

        # 按文件分组替换规则
        file_replacements: dict[str, list] = {}
        for replacement in self.config.apk_replacements:
            file_replacements.setdefault(replacement.file, []).append(replacement)

        # 应用替换规则
        for file_path, replacements in file_replacements.items():
            full_path = apk_dir / file_path
            if not full_path.exists():
                logger.warning(f"  文件不存在: {file_path}")
                continue

            content = full_path.read_text(encoding="utf-8")
            modified = False

            for r in replacements:
                if r.pattern in content:
                    content = content.replace(r.pattern, r.replacement)
                    modified = True
                    logger.debug(f"  替换: {r.pattern} -> {r.replacement}")

            if modified:
                full_path.write_text(content, encoding="utf-8")
                logger.info(f"  已修改: {file_path}")


class ModInjector:
    """Mod 注入器。"""

    add_mods = staticmethod(add_mods_to_html)
    replace_mod = staticmethod(replace_mod_by_id)

    def patch_modloader_code(self, html_path: Path):
        """修改 HTML 文件中 ModLoader 的 JavaScript 代码。"""
        if not html_path.exists():
            raise FileNotFoundError(html_path)

        try:
            content = html_path.read_text(encoding="utf-8")

            # 查找并修改 ModLoader 代码
            # 将 modReadCache.clone() 后添加过滤逻辑
            old_pattern = "const remodloader = modReadCache.clone();"
            new_pattern = """const remodloader = modReadCache.clone();
            remodloader.filterItems((mod) => mod.bootJson && mod.bootJson.name !== 'ModLoader');"""

            if old_pattern in content:
                content = content.replace(old_pattern, new_pattern)
                html_path.write_text(content, encoding="utf-8")
                logger.info(f"  已修补 ModLoader 代码: {html_path.name}")
            else:
                logger.debug(f"  未找到需要修补的代码: {html_path.name}")

        except Exception as e:
            raise RuntimeError(f"修补 ModLoader 代码失败: {html_path}") from e


class GamePreparer:
    """游戏资源预处理器。"""

    def __init__(self, paths: BuildPaths):
        """初始化预处理器。"""
        self.paths = paths
        self.apk_processor = ApkProcessor(paths)
        self.mod_injector = ModInjector()
        self.registry = VersionRegistry()

    def prepare_all(
        self,
        downloaded_files: dict[str, Path],
        extra_mods: dict[str, Path],
    ) -> VersionRegistry:
        """完整的预处理流程。"""
        logger.info("========== 开始游戏预处理 ==========")

        self._validate_required_mods(extra_mods)

        # 准备 ZIP 基包
        self._prepare_zip_base(downloaded_files, extra_mods)

        # 准备 APK
        self._prepare_apk(downloaded_files, extra_mods)

        logger.info("========== 游戏预处理完成 ==========")
        return self.registry

    def _prepare_zip_base(
        self,
        downloaded_files: dict[str, Path],
        extra_mods: dict[str, Path],
    ):
        """准备 ZIP 基包"""
        # 处理普通版
        if "zip" in downloaded_files:
            self._process_zip_version(
                downloaded_files["zip"],
                downloaded_files.get("image_pack"),
                extra_mods,
                polyfill=False,
            )

        # 处理 polyfill 版
        if "polyfill_zip" in downloaded_files:
            self._process_zip_version(
                downloaded_files["polyfill_zip"],
                downloaded_files.get("image_pack"),
                extra_mods,
                polyfill=True,
            )

    def _process_zip_version(
        self,
        zip_path: Path,
        image_pack_path: Path | None,
        extra_mods: dict[str, Path],
        polyfill: bool,
    ):
        """处理单个 ZIP 版本"""
        suffix = "-polyfill" if polyfill else ""
        logger.info(f"处理 ZIP{suffix}...")

        # 解压到临时目录
        extract_dir = self.paths.prepare_dir / f"zip{suffix}"
        extract_zip(zip_path, extract_dir)

        # 合并图片包
        if image_pack_path:
            self._merge_image_pack(image_pack_path, extract_dir)

        # 注入 mod
        html_files = list(extract_dir.glob("*.html"))
        if html_files:
            self._inject_mods(html_files[0], extra_mods)

        # 创建基包
        base_zip = self.paths.get_base_zip(polyfill)
        create_zip(extract_dir, base_zip)
        logger.info(f"  基包已创建: {base_zip}")

    def _prepare_apk(
        self,
        downloaded_files: dict[str, Path],
        extra_mods: dict[str, Path],
    ):
        """准备 APK"""
        for key, polyfill in (("apk", False), ("polyfill_apk", True)):
            if key not in downloaded_files:
                raise FileNotFoundError(f"未找到上游资源: {key}")
            self._process_apk_version(
                downloaded_files[key],
                downloaded_files.get("image_pack"),
                extra_mods,
                polyfill=polyfill,
            )

    def _process_apk_version(
        self,
        apk_path: Path,
        image_pack_path: Path | None,
        extra_mods: dict[str, Path],
        polyfill: bool,
    ):
        """处理单个 APK 版本"""
        suffix = "-polyfill" if polyfill else ""
        logger.info(f"处理 APK{suffix}...")

        # 反编译
        apk_dir = self.paths.get_apk_dir(polyfill)
        self.apk_processor.decompile(apk_path, apk_dir)

        # 应用替换规则
        self.apk_processor.apply_replacements(apk_dir)

        # 合并图片包
        if image_pack_path:
            img_dest = apk_dir / "assets" / "www" / "img"
            self._merge_image_pack(image_pack_path, img_dest.parent)

        # 注入 mod
        html_path = apk_dir / "assets" / "www" / "index.html"
        if html_path.exists():
            self._inject_mods(html_path, extra_mods)

        logger.info(f"  APK 目录已准备: {apk_dir}")

    def _inject_mods(self, html_path: Path, extra_mods: dict[str, Path]):
        """向 HTML 文件注入所有基础 mod。"""
        build_config = load_build_config()
        self._validate_required_mods(extra_mods)

        mods_to_add = []
        for mod in build_config.base_mods:
            if mod.key not in extra_mods:
                continue
            if mod.inject == "replace":
                self.mod_injector.replace_mod(
                    html_path, mod.replace_slot, extra_mods[mod.key]
                )
            else:
                mods_to_add.append(extra_mods[mod.key])

        if mods_to_add:
            self.mod_injector.add_mods(html_path, mods_to_add)

        # 修补 ModLoader 代码
        self.mod_injector.patch_modloader_code(html_path)

    @staticmethod
    def _validate_required_mods(extra_mods: dict[str, Path]):
        for mod in load_build_config().base_mods:
            if mod.required and (
                mod.key not in extra_mods or not extra_mods[mod.key].is_file()
            ):
                raise FileNotFoundError(f"缺少必需 Mod: {mod.name or mod.key}")

    def _merge_image_pack(self, image_pack_path: Path, target_dir: Path):
        """合并图片包"""
        # 解压图片包
        temp_dir = self.paths.temp_dir / "image_pack_temp"
        extract_zip(image_pack_path, temp_dir)

        # 查找 img 目录
        img_src = (
            temp_dir / "img"
            if (temp_dir / "img").exists()
            else next(
                (
                    d / "img"
                    for d in temp_dir.iterdir()
                    if d.is_dir() and (d / "img").exists()
                ),
                None,
            )
        )

        if img_src:
            img_dest = target_dir / "img"
            copy_directory(img_src, img_dest)
            logger.debug(f"  合并图片包: {img_src} -> {img_dest}")

        # 清理
        safe_remove(temp_dir)
