"""资源下载模块。"""

import logging
from pathlib import Path

import requests

from .config_loader import load_build_config
from .paths import BuildPaths
from .utils import download_file
from .version import LyraVersion, VersionInfo, VersionRegistry

logger = logging.getLogger(__name__)


class Downloader:
    """资源下载器。"""

    def __init__(self, paths: BuildPaths):
        """初始化下载器。"""
        self.paths = paths
        self.registry = VersionRegistry()

    def download_from_chs_repo(
        self, version: LyraVersion | None = None
    ) -> dict[str, Path]:
        """从汉化仓库下载资源文件。"""
        logger.info("========== 从汉化仓库下载资源 ==========")

        build_config = load_build_config()
        chs_repo = build_config.chs_repo_url

        # 确定要获取的release tag
        if version:
            tag = f"v{version.dol_ver}-chs-{version.chs_ver}"
            release_data = self._get_github_release(chs_repo, tag)
        else:
            release_data = self._get_github_release(chs_repo, "latest")

        if not release_data:
            raise RuntimeError("无法获取汉化仓库release信息")

        # 记录版本信息
        release_tag = release_data.get("tag_name", "unknown")
        self.registry.add(
            VersionInfo(
                name="汉化仓库",
                version=release_tag,
                source=chs_repo,
            )
        )
        logger.info(f"汉化仓库版本: {release_tag}")

        # 定义需要下载的文件模式
        required_patterns = [
            (
                "polyfill_apk",
                lambda name: (
                    name.lower().endswith(".apk") and "polyfill" in name.lower()
                ),
            ),
            (
                "apk",
                lambda name: (
                    name.lower().endswith(".apk") and "polyfill" not in name.lower()
                ),
            ),
            (
                "zip",
                lambda name: (
                    name.endswith(".zip")
                    and "ModLoader" in name
                    and "polyfill" not in name.lower()
                ),
            ),
            (
                "polyfill_zip",
                lambda name: name.endswith(".zip") and "polyfill" in name.lower(),
            ),
            (
                "image_pack",
                lambda name: "GameOriginalImagePack" in name and name.endswith(".zip"),
            ),
            ("i18n", lambda name: "ModI18N" in name and name.endswith(".zip")),
        ]

        # 从release assets中筛选需要的文件
        assets_to_download = {}
        for asset in release_data.get("assets", []):
            asset_name = asset.get("name", "")
            for key, matcher in required_patterns:
                if key not in assets_to_download and matcher(asset_name):
                    assets_to_download[key] = {
                        "name": asset_name,
                        "url": asset.get("browser_download_url"),
                    }
                    break

        # 检查是否找到所有必需文件
        missing = [key for key, _ in required_patterns if key not in assets_to_download]
        if missing:
            logger.warning(f"未找到以下资源: {missing}")

        # 下载文件
        downloaded_files = {}
        download_dir = self.paths.base_dir
        download_dir.mkdir(parents=True, exist_ok=True)

        for key, asset_info in assets_to_download.items():
            dest_path = download_dir / asset_info["name"]
            download_file(asset_info["url"], dest_path)
            downloaded_files[key] = dest_path
            logger.info(f"  下载完成: {asset_info['name']}")

        return downloaded_files

    def download_extra_mods(self) -> dict[str, Path]:
        """下载额外的mod文件。"""
        logger.info("========== 下载额外mod ==========")

        build_config = load_build_config()
        downloaded_mods = {}
        download_dir = self.paths.base_dir / "mods"
        download_dir.mkdir(parents=True, exist_ok=True)

        for mod in build_config.base_mods:
            if not mod.github_repo:
                continue

            try:
                release_data = self._get_github_release(mod.github_repo, "latest")
                if not release_data:
                    logger.warning(f"无法获取 {mod.github_repo} 的release信息")
                    continue

                release_tag = release_data.get("tag_name", "unknown")

                # 查找mod.zip文件
                for asset in release_data.get("assets", []):
                    asset_name = asset.get("name", "")
                    if asset_name.endswith(".mod.zip"):
                        dest_path = download_dir / asset_name
                        download_file(asset.get("browser_download_url"), dest_path)
                        downloaded_mods[mod.key] = dest_path

                        # 记录版本信息
                        self.registry.add(
                            VersionInfo(
                                name=mod.key,
                                version=release_tag,
                                source=mod.github_repo,
                                filename=asset_name,
                            )
                        )
                        logger.info(f"  {mod.key}: {asset_name} ({release_tag})")
                        break

            except Exception as e:
                logger.error(f"下载 {mod.key} 失败: {e}")

        return downloaded_mods

    def download_apktool(self) -> Path:
        """下载apktool"""
        config = load_build_config()

        dest_path = self.paths.apktool_path
        download_file(
            config.apktool_url,
            dest_path,
            expected_sha256=config.apktool_sha256,
        )
        logger.info(f"apktool 已验证: {dest_path}")
        return dest_path

    def download_apksign(self) -> Path:
        """下载uber-apk-signer"""
        config = load_build_config()

        dest_path = self.paths.apksign_path
        download_file(
            config.uber_apk_signer_url,
            dest_path,
            expected_sha256=config.uber_apk_signer_sha256,
        )
        logger.info(f"uber-apk-signer 已验证: {dest_path}")
        return dest_path

    def _get_github_release(self, repo: str, tag: str) -> dict | None:
        """获取GitHub release信息。"""
        try:
            if tag == "latest":
                api_url = f"https://api.github.com/repos/{repo}/releases/latest"
            else:
                api_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"

            logger.debug(f"获取 GitHub Release: {api_url}")
            response = requests.get(api_url, timeout=30)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"获取 GitHub release 失败 ({repo}): {e}")
            return None
