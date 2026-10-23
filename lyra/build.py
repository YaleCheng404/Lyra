"""ZIP 与 APK 打包。"""

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from scripts.modmagic import add_mods_to_html

from .config import ModCode
from .config_loader import get_config_loader
from .lyra_mod import build_lyra_mod
from .paths import BuildPaths
from .utils import (
    copy_directory,
    create_zip,
    extract_zip,
    run_command,
    safe_remove,
)
from .version import LyraVersion, VersionRegistry, package_filename

logger = logging.getLogger(__name__)


@dataclass
class BuildTask:
    """构建任务。"""

    pack_type: str  # zip 或 apk
    mod_code: int  # MOD代码
    is_polyfill: bool = False  # 是否为polyfill版本
    version: LyraVersion | None = None  # 版本信息
    paths: BuildPaths | None = None  # 路径管理器

    def __post_init__(self):
        if self.paths is None:
            self.paths = BuildPaths()

    @property
    def code_str(self) -> str:
        """获取构建代码字符串"""
        prefix = "polyfill-" if self.is_polyfill else ""
        return f"{prefix}{self.mod_code}"

    @classmethod
    def from_code_str(
        cls,
        code_str: str,
        pack_type: str,
        version: LyraVersion | None = None,
        paths: BuildPaths | None = None,
    ) -> "BuildTask":
        """从代码字符串创建任务。"""
        is_polyfill = code_str.startswith("polyfill-")
        mod_code = int(code_str.removeprefix("polyfill-"))
        return cls(
            pack_type=pack_type,
            mod_code=mod_code,
            is_polyfill=is_polyfill,
            version=version,
            paths=paths,
        )


@dataclass
class BuildResult:
    """构建结果"""

    success: bool
    output_path: Path | None = None
    error: str | None = None


class PackageBuilder:
    """准备资源、注入 Mod，并生成单个 ZIP 或签名 APK。"""

    KEYSTORE_PATH = Path("dol.jks")
    KEYSTORE_ALIAS = "dol"
    KEYSTORE_PASSWORD = "dolchs"

    def __init__(self, task: BuildTask):
        self.task = task
        self.pack_type = task.pack_type.lower()
        if self.pack_type not in {"zip", "apk"}:
            raise ValueError(f"不支持的包类型: {task.pack_type}")
        self.paths = task.paths
        self.mod_code = ModCode(task.mod_code)
        self.work_dir = self.paths.get_build_work_dir(
            self.pack_type, task.mod_code, task.is_polyfill
        )
        self.lyra_mod_path = (
            self.paths.temp_dir / f"Lyra-{self.pack_type}-{task.code_str}.mod.zip"
        )

    @property
    def html_dir(self) -> Path:
        return (
            self.work_dir / "assets/www" if self.pack_type == "apk" else self.work_dir
        )

    @property
    def img_path(self) -> Path:
        return self.html_dir / "img"

    @property
    def html_path(self) -> Path:
        if self.pack_type == "apk":
            return self.html_dir / "index.html"
        return next(self.html_dir.glob("*.html"), self.html_dir / "index.html")

    def _apply_beautify(self):
        # 覆盖顺序影响最终图片，UCB 必须最后应用。
        for code, name in (
            (ModCode.BESC, "besc"),
            (ModCode.SIDEVIEW_HIKARI, "hikari"),
            (ModCode.UCB, "ucb"),
        ):
            if self.mod_code & code:
                source = self.paths.get_beautify_cache_dir(name) / "img"
                if source.exists():
                    copy_directory(source, self.img_path)
                else:
                    logger.warning("美化资源不存在: %s", source)

    def _inject_modloader_mods(self):
        loader = get_config_loader()
        mods = []
        for mod in loader.build.modloader_mods:
            feature = loader.get_feature_by_id(mod.feature_id)
            if not feature:
                logger.warning("未找到功能: %s", mod.feature_id)
                continue
            if self.mod_code & feature.bit:
                path = self.paths.get_mod_cache_path(mod.feature_id.replace("-", "_"))
                if path.exists():
                    mods.append(path)
                else:
                    logger.warning("Mod 文件不存在: %s", path)
        if mods:
            add_mods_to_html(self.html_path, mods)

    def _inject_lyra_mod(self):
        """构建并注入 Lyra 信息 mod。"""
        registry = VersionRegistry.load(self.paths.versions_file)

        mod_suffix = self.mod_code.get_suffix()

        # 构建 Lyra mod（使用任务唯一路径避免并行竞态）
        lyra_mod_path = self.lyra_mod_path
        build_lyra_mod(lyra_mod_path, self.task.version, list(registry), mod_suffix)

        add_mods_to_html(self.html_path, [lyra_mod_path])

    def build(self) -> BuildResult:
        output = self.paths.output_dir / package_filename(
            self.task.version, self.task.mod_code, self.pack_type, self.task.is_polyfill
        )
        partial = output.with_name(output.name + ".part")
        tmp_apk = self.paths.get_temp_apk(self.task.mod_code, self.task.is_polyfill)
        signed_dir = self.paths.get_signed_dir(
            self.task.mod_code, self.task.is_polyfill
        )
        logger.info("构建 %s: %s", self.pack_type.upper(), self.task.code_str)
        try:
            safe_remove(self.work_dir)
            if self.pack_type == "zip":
                extract_zip(
                    self.paths.get_base_zip(self.task.is_polyfill), self.work_dir
                )
            else:
                copy_directory(
                    self.paths.get_apk_dir(self.task.is_polyfill), self.work_dir
                )
                safe_remove(signed_dir)
            self._apply_beautify()
            self._inject_modloader_mods()
            self._inject_lyra_mod()
            output.parent.mkdir(parents=True, exist_ok=True)
            if self.pack_type == "zip":
                create_zip(self.work_dir, partial)
            else:
                shutil.move(str(self._sign(self._recompile())), str(partial))
            partial.replace(output)
            logger.info("完成: %s", output.name)
            return BuildResult(True, output_path=output)
        except Exception as exc:
            logger.error("%s 构建失败: %s", self.pack_type.upper(), exc)
            logger.debug("构建异常", exc_info=True)
            return BuildResult(False, error=str(exc))
        finally:
            for path in (self.work_dir, self.lyra_mod_path, partial):
                safe_remove(path)
            if self.pack_type == "apk":
                safe_remove(tmp_apk)
                safe_remove(signed_dir)

    def _recompile(self) -> Path:
        """重新编译APK"""
        logger.debug("重新编译APK...")

        apktool_path = self.paths.apktool_path
        tmp_apk = self.paths.get_temp_apk(self.task.mod_code, self.task.is_polyfill)

        run_command(
            [
                "java",
                "-jar",
                str(apktool_path),
                "b",
                str(self.work_dir),
                "-o",
                str(tmp_apk),
            ]
        )

        return tmp_apk

    def _sign(self, apk_path: Path) -> Path:
        """签名APK"""
        logger.debug("签名APK...")

        apksign_path = self.paths.apksign_path
        signed_dir = self.paths.get_signed_dir(
            self.task.mod_code, self.task.is_polyfill
        )
        signed_dir.mkdir(parents=True, exist_ok=True)

        run_command(
            [
                "java",
                "--enable-native-access=ALL-UNNAMED",
                "-jar",
                str(apksign_path),
                "-a",
                str(apk_path),
                "--ks",
                str(self.KEYSTORE_PATH),
                "--ksAlias",
                self.KEYSTORE_ALIAS,
                "--ksKeyPass",
                self.KEYSTORE_PASSWORD,
                "--ksPass",
                self.KEYSTORE_PASSWORD,
                "-o",
                str(signed_dir),
            ]
        )

        for f in signed_dir.iterdir():
            if f.suffix == ".apk":
                return f

        raise FileNotFoundError("签名后的APK未找到")
