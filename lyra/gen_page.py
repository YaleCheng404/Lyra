"""Markdown 下载页面生成模块。"""

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .combo import CombinationCalculator, ModCombination
from .config_loader import load_build_config
from .version import LyraVersion, VersionInfo, VersionRegistry, package_filename


def _github_repo_from_env() -> tuple[str, str]:
    """从 GitHub Actions 环境变量读取当前仓库。"""
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    owner, sep, repo = repository.partition("/")
    if sep:
        return owner, repo
    return "", ""


@dataclass
class DownloadPageConfig:
    """下载页面配置"""

    version: str
    github_owner: str = ""
    github_repo: str = ""
    include_zip: bool = True
    include_apk: bool = True
    mirror_base: str = "https://ghfast.top/https://github.com"
    base_game_version: str = ""
    chs_version: str = ""
    date_suffix: str = ""
    versions_file: Path | None = None  # 版本信息文件路径
    version_info: list[VersionInfo] = field(default_factory=list)  # 版本信息列表

    def __post_init__(self):
        """如果没有指定 GitHub 信息，从配置文件加载"""
        if not self.github_owner or not self.github_repo:
            env_owner, env_repo = _github_repo_from_env()
            try:
                build_config = load_build_config()
                if not self.github_owner:
                    self.github_owner = env_owner or build_config.github_owner
                if not self.github_repo:
                    self.github_repo = env_repo or build_config.github_repo
            except Exception:
                if not self.github_owner:
                    self.github_owner = env_owner
                if not self.github_repo:
                    self.github_repo = env_repo

        if not self.github_owner or not self.github_repo:
            raise ValueError(
                "无法确定 GitHub 仓库，请传入 github_owner/github_repo 或设置 GITHUB_REPOSITORY"
            )

        if self.version and (
            not self.base_game_version or not self.chs_version or not self.date_suffix
        ):
            parts = self.version.lstrip("v").split("-")
            if len(parts) >= 3:
                if not self.base_game_version:
                    self.base_game_version = parts[0]
                if not self.chs_version:
                    self.chs_version = parts[1]
                if not self.date_suffix:
                    self.date_suffix = parts[2]

        if self.versions_file and not self.version_info:
            self.version_info = list(VersionRegistry.load(self.versions_file))

    @property
    def release_base_url(self) -> str:
        return f"https://github.com/{self.github_owner}/{self.github_repo}/releases/download"

    def get_download_url(self, filename: str) -> str:
        """获取下载链接"""
        tag = self.version
        return f"{self.release_base_url}/{tag}/{filename}"

    def get_mirror_url(self, filename: str) -> str:
        """获取镜像下载链接"""
        tag = self.version
        return f"{self.mirror_base}/{self.github_owner}/{self.github_repo}/releases/download/{tag}/{filename}"

    def get_filename(self, mod_code: int, ext: str, is_polyfill: bool = False) -> str:
        """生成文件名。"""
        version = LyraVersion(
            self.base_game_version, self.chs_version, self.date_suffix
        )
        return package_filename(version, mod_code, ext, is_polyfill)


class DownloadPageGenerator:
    """下载页面生成器"""

    def __init__(
        self,
        config: DownloadPageConfig,
        config_dir: Path | None = None,
    ):
        self.config = config
        self.calculator = CombinationCalculator(config_dir)

    def _generate_row(
        self,
        combination: ModCombination,
        package_types: list[str],
    ) -> list[str]:
        display_name = combination.display_name

        if combination.is_recommended and not combination.is_polyfill:
            display_name = f"***{display_name}(推荐)***"

        row = [display_name]

        for package_type in package_types:
            filename = self.config.get_filename(
                combination.code, package_type, combination.is_polyfill
            )
            github_url = self.config.get_download_url(filename)
            mirror_url = self.config.get_mirror_url(filename)
            row.append(f"[Github下载]({github_url}) / [备链]({mirror_url})")

        return row

    def generate_table(self, combinations: list[ModCombination]) -> str:
        """生成 Markdown 下载表格。"""
        package_types = [
            kind for kind, enabled in (
                ("zip", self.config.include_zip), ("apk", self.config.include_apk)
            ) if enabled
        ]
        headers = ["版本选择", *(kind.upper() for kind in package_types)]
        rows = [headers, ["---"] * len(headers)]
        rows.extend(self._generate_row(combination, package_types) for combination in combinations)
        return "\n".join("|" + "|".join(row) + "|" for row in rows)

    def generate(self) -> str:
        """生成下载表格、组合说明与资源版本记录。"""
        combinations = sorted(
            self.calculator.calculate(include_polyfill=True),
            key=lambda combo: (
                not combo.is_polyfill,
                not combo.is_recommended,
                combo.display_name != "基础",
                combo.code,
            ),
        )
        current_time = datetime.now(UTC).isoformat(timespec="seconds")
        lines = [
            "+++",
            f"title = '{self.config.version}'",
            f"date = {current_time}",
            f"slug = 'downloads/{self.config.version}'",
            "+++",
            "",
            "升级前请导出并备份存档。",
            "",
            '选择版本前请阅读 [版本说明]({{< ref "docs" >}})，使用问题见 [疑难解答]({{< ref "troubleshoot" >}})。',
            "",
            "发布文件包含完整游戏和 Mod，不能作为旁加载包导入。汉化、作弊和 CSD 已内置，可在 ModLoader 中启用或禁用。",
            "",
            "## 下载",
            "",
            "基础版包含汉化、作弊和 CSD，其他组合添加对应美化、特写或模型。",
            "",
            self.generate_table(combinations),
        ]
        if self.config.version_info:
            lines.extend(self._generate_version_table())
        lines.extend(
            [
                "",
                "<details>",
                "<summary>组合对照</summary>",
                "",
                "```",
                self.calculator.to_string(),
                "```",
                "",
                "</details>",
            ]
        )
        return "\n".join(lines)

    def _generate_version_table(self) -> list[str]:
        """生成版本信息表格"""
        lines = [
            "",
            "",
            "<details>",
            "",
            "<summary>资源版本信息</summary>",
            "",
            "| 资源 | 版本 | 来源 |",
            "|------|------|------|",
        ]

        for v in self.config.version_info:
            source = v.source or "-"
            if "github.com" in source or "/" in source:
                if "gitgud.io" in source:
                    source_link = f"[{source}](https://{source})"
                elif "/" in source and "http" not in source:
                    source_link = f"[{source}](https://github.com/{source})"
                else:
                    source_link = source
            else:
                source_link = source

            lines.append(f"| {v.name} | `{v.version}` | {source_link} |")

        lines.extend(
            [
                "",
                "</details>",
            ]
        )

        return lines


def generate_download_page(
    version: str,
    output_path: Path | None = None,
    github_owner: str = "",
    github_repo: str = "",
    versions_file: Path | None = None,
) -> str:
    """便捷函数：生成下载页面。"""
    config = DownloadPageConfig(
        version=version,
        github_owner=github_owner,
        github_repo=github_repo,
        versions_file=versions_file,
    )

    generator = DownloadPageGenerator(config)
    content = generator.generate()

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")

    return content
