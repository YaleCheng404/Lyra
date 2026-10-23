"""资源预热模块。"""

import logging

from .config_loader import (
    ImagePackConfig,
    ModloaderModConfig,
    get_config_loader,
    load_build_config,
)
from .paths import BuildPaths
from .utils import (
    copy_directory,
    download_file,
    extract_tar_gz,
    get_gitgud_commit_hash,
    get_github_release_asset,
    safe_remove,
)
from .version import VersionInfo, VersionRegistry

logger = logging.getLogger(__name__)


class ResourceWarmer:
    """资源预热器。"""

    def __init__(self, paths: BuildPaths):
        """初始化预热器。"""
        self.paths = paths
        self.config = load_build_config()
        self.registry = VersionRegistry()

    def warmup_all(self) -> VersionRegistry:
        """预热所有美化资源。"""
        logger.info("========== 开始资源预热 ==========")

        self.paths.temp_dir.mkdir(parents=True, exist_ok=True)

        self._warmup_dolp_packs()

        self._warmup_modloader_mods()

        logger.info("========== 资源预热完成 ==========")
        self.registry.print_summary()

        return self.registry

    def _warmup_dolp_packs(self):
        """预热 DoL+ 图片包"""
        logger.info("--- 预热 DoL+ 图片包 ---")

        urls = {url for pack in self.config.imagepacks.values() for url in pack.urls}

        commit_hash = get_gitgud_commit_hash(
            "Frostberg/degrees-of-lewdity-plus", "master"
        )
        if commit_hash:
            self.registry.add(
                VersionInfo(
                    name="DoL+",
                    version=commit_hash,
                    source="gitgud.io/Frostberg/degrees-of-lewdity-plus",
                )
            )

        for url in sorted(urls):
            self._download_dolp_pack(url)
        for pack in self.config.imagepacks.values():
            self._process_image_pack(pack)

    def _download_dolp_pack(self, url: str):
        """下载单个 DoL+ 图片包。"""
        pack_name = url.rsplit("/", 1)[-1]
        tar_path = self.paths.temp_dir / f"dolp-{pack_name}.tar.gz"
        extract_dir = self.paths.temp_dir / f"dolp-{pack_name}"

        if extract_dir.exists() and (extract_dir / "img").exists():
            logger.debug(f"  {pack_name}: 已缓存")
            return

        logger.info(f"  下载: {pack_name}")
        download_file(url, tar_path, quiet=True)

        img_dir = extract_dir / "img"
        img_dir.mkdir(parents=True, exist_ok=True)
        extract_tar_gz(tar_path, img_dir, strip_components=3)

    def _process_image_pack(self, pack: ImagePackConfig):
        """按配置顺序合并图片包，再处理大小写与排除文件。"""
        root = self.paths.get_beautify_cache_dir(pack.name)
        dest = root / "img"
        if (dest / "body").exists():
            logger.debug("%s: 已处理", pack.name)
            return
        for url in pack.urls:
            source = self.paths.temp_dir / f"dolp-{url.rsplit('/', 1)[-1]}" / "img"
            copy_directory(source, dest)
        for source_name, target_name in pack.case_fixes.items():
            source, target = root / source_name, root / target_name
            if not source.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # Windows 上大小写不同的名字可能指向同一对象，不能先删除源路径。
            if target.exists() and source.samefile(target):
                source.rename(target)
            elif source.is_dir():
                copy_directory(source, target)
                safe_remove(source)
            else:
                source.replace(target)
        for name in pack.files_to_remove:
            safe_remove(root / name)
        logger.info("%s: 处理完成", pack.name)

    def _warmup_modloader_mods(self):
        """预热 modloader mod"""
        if not self.config.modloader_mods:
            return

        logger.info("--- 预热 modloader mod ---")
        config_loader = get_config_loader()

        for mod_config in self.config.modloader_mods:
            self._download_modloader_mod(mod_config, config_loader)

    def _download_modloader_mod(self, mod_config: ModloaderModConfig, config_loader):
        """下载单个 modloader mod。"""
        feature = config_loader.get_feature_by_id(mod_config.feature_id)
        display_name = feature.name if feature else mod_config.feature_id
        cache_name = mod_config.feature_id.replace("-", "_")
        dest_path = self.paths.get_mod_cache_path(cache_name)

        if dest_path.exists():
            logger.debug(f"  {display_name}: 已缓存")
            return

        asset = get_github_release_asset(
            mod_config.github_repo,
            mod_config.asset_pattern,
            tag=mod_config.release_tag,
        )

        if not asset:
            logger.warning(f"  {display_name}: 无法获取下载信息")
            return

        self.registry.add(
            VersionInfo(
                name=display_name,
                version=asset.version,
                source=mod_config.github_repo,
                filename=asset.name,
            )
        )

        download_file(asset.url, dest_path, quiet=True)
        logger.info(f"  {display_name}: 下载完成 ({asset.version})")
