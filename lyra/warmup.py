"""资源预热模块。"""

import logging
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from .config_loader import (
    ImagePackConfig,
    ModloaderModConfig,
    get_config_loader,
    load_build_config,
)
from .paths import BuildPaths
from .utils import (
    download_file,
    extract_tar_gz,
    get_github_release_asset,
    safe_remove,
)
from .version import VersionInfo, VersionRegistry

logger = logging.getLogger(__name__)

DOLP_SOURCE = "gitgud.io/Frostberg/degrees-of-lewdity-plus"
DOLP_ARCHIVE_PREFIX = (
    f"https://{DOLP_SOURCE}/-/archive/master/"
    "degrees-of-lewdity-plus-master.tar.gz?path=imagepacks/"
)


class ResourceWarmer:
    """资源预热器。"""

    def __init__(self, paths: BuildPaths):
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

        git_urls = {url for url in urls if url.startswith(DOLP_ARCHIVE_PREFIX)}
        git_names = sorted(url.removeprefix(DOLP_ARCHIVE_PREFIX) for url in git_urls)
        missing = [
            name for name in git_names
            if not (self.paths.temp_dir / f"dolp-{name}" / "img").is_dir()
        ]
        if missing:
            commit_hash = self._checkout_dolp_packs(missing)
            self.registry.add(
                VersionInfo(
                    name="DoL+",
                    version=commit_hash,
                    source=DOLP_SOURCE,
                )
            )

        self._download_archives(sorted(urls - git_urls))
        for pack in self.config.imagepacks.values():
            self._process_image_pack(pack)

    def _checkout_dolp_packs(self, names: list[str]) -> str:
        # GitGud limits archive downloads. A single sparse checkout fetches these paths.
        folders = [f"imagepacks/{name}" for name in names]
        if any(not name or name in {".", ".."} or "/" in name or "\\" in name for name in names):
            raise ValueError("DoL+ 图片包目录名称无效")
        logger.info("从 Git 获取 DoL+ 图片包: %s", ", ".join(names))
        with TemporaryDirectory(dir=self.paths.temp_dir, prefix="dolp-src-") as directory:
            checkout = Path(directory) / "repo"
            subprocess.run(
                [
                    "git", "clone", "--depth", "1", "--single-branch", "--no-checkout",
                    "--filter=blob:none", "--branch", "master", "--config", "core.autocrlf=false",
                    "--config", "core.longpaths=true", f"https://{DOLP_SOURCE}.git", str(checkout),
                ],
                check=True,
            )
            git = ["git", "-C", str(checkout)]
            tree = subprocess.check_output([*git, "ls-tree", "-r", "HEAD", "--", *folders])
            if any(entry.startswith((b"120000 ", b"160000 ")) for entry in tree.splitlines()):
                raise ValueError("DoL+ 图片包包含符号链接或子模块")
            subprocess.run([*git, "sparse-checkout", "set", "--cone", "--", *folders], check=True)
            subprocess.run([*git, "checkout", "--detach", "HEAD"], check=True)
            sources = [checkout / folder for folder in folders]
            for source in sources:
                if not source.is_dir():
                    raise FileNotFoundError(f"上游缺少图片包: {source.name}")
            for source in sources:
                destination = self.paths.temp_dir / f"dolp-{source.name}" / "img"
                destination.parent.mkdir(parents=True, exist_ok=True)
                source.rename(destination)
            return subprocess.check_output([*git, "rev-parse", "--short=7", "HEAD"], text=True).strip()

    def _download_archives(self, urls: list[str]):
        if not urls:
            return
        retries = Retry(
            total=10,
            connect=0,
            read=0,
            other=0,
            allowed_methods={"GET"},
            status_forcelist={429},
            backoff_factor=5,
            backoff_max=30,
            raise_on_status=False,
        )
        with Session() as session:
            for scheme in ("http://", "https://"):
                session.mount(scheme, HTTPAdapter(max_retries=retries))
            for url in urls:
                self._download_dolp_pack(url, session)

    def _download_dolp_pack(self, url: str, session: Session):
        """下载单个 DoL+ 图片包。"""
        pack_name = url.rsplit("/", 1)[-1]
        tar_path = self.paths.temp_dir / f"dolp-{pack_name}.tar.gz"
        extract_dir = self.paths.temp_dir / f"dolp-{pack_name}"

        if extract_dir.exists() and (extract_dir / "img").exists():
            logger.debug(f"  {pack_name}: 已缓存")
            return

        logger.info(f"  下载: {pack_name}")
        download_file(url, tar_path, quiet=True, session=session)

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
            shutil.copytree(source, dest, dirs_exist_ok=True)
        for source_name, target_name in pack.case_fixes.items():
            source, target = root / source_name, root / target_name
            if not source.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # Windows 上大小写不同的名字可能指向同一对象，不能先删除源路径。
            if target.exists() and source.samefile(target):
                source.rename(target)
            elif source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
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
