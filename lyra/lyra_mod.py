"""Lyra 信息 mod 构建模块。"""

import json
import logging
import zipfile
from pathlib import Path

from .version import LyraVersion, VersionInfo

logger = logging.getLogger(__name__)


def build_lyra_mod(
    output_path: Path,
    version: LyraVersion | None = None,
    version_info: list[VersionInfo] | None = None,
    mod_suffix: str = "",
) -> Path:
    """构建 Lyra 信息 mod。"""
    version_str = str(version).lstrip("v") if version else "unknown"
    if mod_suffix:
        version_str = f"{version_str}-{mod_suffix}"

    # 构建 boot.json
    boot_json = {
        "name": "Lyra",
        "version": version_str,
        "scriptFileList_inject_early": [],
        "scriptFileList_earlyload": [],
        "scriptFileList_preload": [],
        "styleFileList": [],
        "scriptFileList": [],
        "tweeFileList": [],
        "imgFileList": [],
        "additionFile": ["README.md"],
    }

    # 构建 README.md
    readme = _generate_readme(version_str, version_info or [])

    # 创建 mod.zip
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("boot.json", json.dumps(boot_json, indent=2, ensure_ascii=False))
        zf.writestr("README.md", readme)

    logger.info(f"Lyra mod 已生成: {output_path}")
    return output_path


def _generate_readme(
    version_str: str,
    version_info: list[VersionInfo],
) -> str:
    """生成 README.md 内容。"""
    lines = [
        f"# Lyra {version_str}",
        "",
        "此 mod 为 Lyra 整合包的信息标识，不包含实质功能。",
        "",
    ]

    if version_info:
        lines.extend(
            [
                "## 资源版本信息",
                "",
                "| 资源 | 版本 |",
                "|------|------|",
            ]
        )

        lines.extend(f"| {v.name} | `{v.version}` |" for v in version_info)

    return "\n".join(lines)
