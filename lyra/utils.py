"""工具函数模块。"""

import hashlib
import logging
import re
import shutil
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import requests
from packaging.version import Version
from packaging.version import parse as parse_version
from tqdm import tqdm

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """配置日志系统"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def download_file(
    url: str, dest: Path, quiet: bool = False, expected_sha256: str | None = None,
    force: bool = False,
    expected_size: int | None = None,
) -> Path:
    """下载文件到指定路径。"""
    expected_sha256 = (
        expected_sha256.removeprefix("sha256:").lower() if expected_sha256 else None
    )
    if expected_sha256 and (
        len(expected_sha256) != 64
        or any(char not in "0123456789abcdef" for char in expected_sha256)
    ):
        raise ValueError("expected_sha256 必须是 64 位十六进制字符串")

    if not force and dest.exists() and (
        not expected_sha256 or get_file_hash(dest, "sha256") == expected_sha256
    ):
        logger.debug(f"文件已存在，跳过下载: {dest}")
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"下载: {url}")
    partial = dest.with_name(f"{dest.name}.part")
    try:
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            total_size = int(response.headers.get("content-length", 0))
            with (
                partial.open("wb") as stream,
                tqdm(
                    total=total_size, unit="B", unit_scale=True, desc=dest.name,
                    disable=quiet or total_size == 0,
                ) as progress,
            ):
                for chunk in response.iter_content(chunk_size=8192):
                    stream.write(chunk)
                    progress.update(len(chunk))

        if expected_sha256:
            actual = get_file_hash(partial, "sha256")
            if actual != expected_sha256:
                raise ValueError(
                    f"{dest.name} SHA-256 校验失败: expected={expected_sha256}, actual={actual}"
                )
        if expected_size is not None and partial.stat().st_size != expected_size:
            raise ValueError(f"{dest.name} 附件大小不符")
        partial.replace(dest)
    finally:
        partial.unlink(missing_ok=True)

    return dest


def extract_zip(zip_path: Path, dest_dir: Path) -> Path:
    """解压ZIP文件。"""
    logger.info(f"解压ZIP: {zip_path} -> {dest_dir}")
    dest_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)

    return dest_dir


def create_zip(source_dir: Path, dest_path: Path) -> Path:
    """创建ZIP压缩包。"""
    logger.info(f"创建ZIP: {source_dir} -> {dest_path}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                arc_name = file_path.relative_to(source_dir)
                zf.write(file_path, arc_name)

    return dest_path


def extract_tar_gz(tar_path: Path, dest_dir: Path, strip_components: int = 0) -> Path:
    """解压tar.gz文件。"""
    logger.info(f"解压tar.gz: {tar_path} -> {dest_dir}")
    dest_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(tar_path, "r:gz") as tf:
        for member in tf.getmembers():
            name = _safe_tar_name(member.name, strip_components)
            if name is None:
                continue
            if member.issym() or member.islnk():
                raise ValueError(f"不允许 TAR 链接成员: {member.name}")
            tf.extract(member.replace(name=name), dest_dir, filter="data")

    return dest_dir


def _safe_tar_name(name: str, strip_components: int) -> str | None:
    """校验并裁剪 TAR 内部路径。"""
    if "\\" in name:
        raise ValueError(f"不安全的 TAR 路径: {name}")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"不安全的 TAR 路径: {name}")
    parts = path.parts[strip_components:]
    return str(PurePosixPath(*parts)) if parts else None


def safe_remove(path: Path) -> bool:
    """安全删除文件或目录。"""
    try:
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            return True
    except Exception as e:
        logger.warning(f"删除失败 {path}: {e}")
    return False


def get_file_hash(path: Path, algorithm: str = "md5") -> str:
    """计算文件哈希值。"""
    with open(path, "rb") as f:
        return hashlib.file_digest(f, algorithm).hexdigest()


@dataclass
class GitHubReleaseAsset:
    """GitHub Release 资源信息。"""

    url: str
    name: str
    tag: str
    version: str  # 从文件名提取的版本号


def get_github_release_asset(
    repo: str, asset_pattern: str, tag: str = "latest"
) -> GitHubReleaseAsset | None:
    """从 GitHub Release 获取资源信息。"""
    try:
        if tag == "latest":
            api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        else:
            api_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
        logger.debug(f"获取 GitHub Release 信息: {api_url}")

        response = requests.get(api_url, timeout=10)
        response.raise_for_status()

        release_data = response.json()
        release_tag = release_data.get("tag_name", tag)
        assets = release_data.get("assets", [])

        matched_assets: list[tuple[GitHubReleaseAsset, Version]] = []

        for asset in assets:
            name = asset.get("name", "")
            if asset_pattern in name:
                download_url = asset.get("browser_download_url")
                version = _extract_version_from_filename(name)
                logger.debug(f"找到资源: {name} (version={version}) -> {download_url}")

                matched_assets.append(
                    (
                        GitHubReleaseAsset(
                            url=download_url,
                            name=name,
                            tag=release_tag,
                            version=version,
                        ),
                        (
                            parse_version(version)
                            if version != "unknown"
                            else parse_version("0")
                        ),
                    )
                )

        if not matched_assets:
            logger.warning(f"未找到匹配 '{asset_pattern}' 的资源")
            return None

        best_asset, best_version = max(matched_assets, key=lambda x: x[1])
        logger.debug(f"选择最高版本: {best_asset.name} (version={best_version})")
        return best_asset

    except Exception as e:
        logger.error(f"获取 GitHub Release 失败: {e}")
        return None


def _extract_version_from_filename(filename: str) -> str:
    """从文件名提取版本号。"""
    match = re.search(r"[_-](v?\d+\.\d+\.\d+[^.]*)\.zip", filename, re.IGNORECASE)
    return match.group(1) if match else "unknown"


def get_gitgud_commit_hash(repo: str, branch: str = "master") -> str | None:
    """获取 GitGud 仓库的最新 commit hash。"""
    try:
        # GitGud API: https://gitgud.io/api/v4/projects/:id/repository/branches/:branch
        # 需要将 / 编码为 %2F
        encoded_repo = repo.replace("/", "%2F")
        api_url = f"https://gitgud.io/api/v4/projects/{encoded_repo}/repository/branches/{branch}"

        logger.debug(f"获取 GitGud commit hash: {api_url}")

        response = requests.get(api_url, timeout=10)
        response.raise_for_status()

        data = response.json()
        commit = data.get("commit", {})
        full_hash = commit.get("id", "")

        if full_hash:
            short_hash = full_hash[:7]
            logger.debug(f"GitGud {repo} commit: {short_hash}")
            return short_hash

        return None
    except Exception as e:
        logger.warning(f"获取 GitGud commit hash 失败: {e}")
        return None
