"""资源下载模块。"""

import json
import logging
from fnmatch import fnmatchcase
from pathlib import Path

import requests

from .config_loader import load_build_config
from .paths import BuildPaths
from .utils import download_file, get_file_hash
from .version import LyraVersion, VersionInfo, VersionRegistry

logger = logging.getLogger(__name__)


class Downloader:
    """资源下载器。"""

    def __init__(self, paths: BuildPaths):
        self.paths = paths
        self.registry = VersionRegistry()

    def download_from_chs_repo(
        self, version: LyraVersion | None = None
    ) -> dict[str, Path]:
        """从汉化仓库下载资源文件。"""
        logger.info("========== 从汉化仓库下载资源 ==========")

        build_config = load_build_config()
        chs_repo = build_config.chs_repo_url

        tag = f"v{version.dol_ver}-chs-{version.chs_ver}" if version else "latest"
        release_data = self._get_github_release(chs_repo, tag)

        if not release_data:
            raise RuntimeError("无法获取汉化仓库release信息")

        release_tag = release_data.get("tag_name", "unknown")
        self.registry.add(
            VersionInfo(
                name="汉化仓库",
                version=release_tag,
                source=chs_repo,
            )
        )
        logger.info(f"汉化仓库版本: {release_tag}")

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

        missing = [key for key, _ in required_patterns if key not in assets_to_download]
        if missing:
            logger.warning(f"未找到以下资源: {missing}")

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

        releases = {}
        for mod in build_config.base_mods:
            if not mod.github_repo:
                continue

            try:
                if mod.github_repo not in releases:
                    releases[mod.github_repo] = self._get_github_release(
                        mod.github_repo, "latest"
                    )
                release_data = releases[mod.github_repo]
                if not release_data or release_data.get("draft") or release_data.get("prerelease"):
                    raise RuntimeError(f"无法获取 {mod.github_repo} 的正式 Release")

                release_tag = release_data.get("tag_name", "unknown")

                assets = [
                    asset for asset in release_data.get("assets", [])
                    if fnmatchcase(asset.get("name", ""), mod.asset_pattern)
                ]
                if len(assets) != 1:
                    raise ValueError(
                        f"{mod.key}: {mod.asset_pattern} 匹配到 {len(assets)} 个附件"
                    )
                asset = assets[0]
                dest_path = self._download_mod_asset(asset, download_dir)
                downloaded_mods[mod.key] = dest_path
                self.registry.add(
                    VersionInfo(
                        name=mod.name or mod.key,
                        version=release_tag,
                        source=mod.github_repo,
                        filename=asset["name"],
                    )
                )
                logger.info(f"  {mod.name or mod.key}: {dest_path.name} ({release_tag})")

            except Exception as e:
                if mod.required:
                    raise RuntimeError(f"必需 Mod {mod.name or mod.key} 获取失败: {e}") from e
                logger.error(f"下载 {mod.key} 失败: {e}")

        return downloaded_mods

    @staticmethod
    def _download_mod_asset(asset: dict, download_dir: Path) -> Path:
        """校验来源身份和摘要，避免同名附件更新后继续使用旧缓存。"""
        name = asset.get("name", "")
        if not name or name in {".", ".."} or Path(name).name != name or "/" in name or "\\" in name:
            raise ValueError(f"无效附件名称: {name}")
        url = asset.get("browser_download_url")
        if not url:
            raise ValueError(f"附件缺少下载链接: {name}")
        dest = download_dir / name
        metadata = dest.with_name(name + ".source.json")
        identity = {key: asset.get(key) for key in (
            "id", "updated_at", "size", "browser_download_url"
        )}
        digest = asset.get("digest")
        if digest and not digest.startswith("sha256:"):
            raise ValueError(f"不支持的附件摘要: {name}")
        reusable = False
        if dest.is_file() and dest.stat().st_size == asset.get("size"):
            if digest:
                reusable = "sha256:" + get_file_hash(dest, "sha256") == digest
            elif all(value is not None for value in identity.values()):
                try:
                    reusable = json.loads(metadata.read_text(encoding="utf-8")) == identity
                except (OSError, ValueError):
                    pass
        if not reusable:
            # download_file 通过 .part 校验后原子替换，失败不会损坏原缓存。
            download_file(
                url, dest, expected_sha256=digest, force=True,
                expected_size=asset.get("size"),
            )
            temp_metadata = metadata.with_name(metadata.name + ".part")
            try:
                temp_metadata.write_text(json.dumps(identity, sort_keys=True), encoding="utf-8")
                temp_metadata.replace(metadata)
            finally:
                temp_metadata.unlink(missing_ok=True)
        return dest

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
