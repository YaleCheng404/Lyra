"""版本信息管理模块。"""

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import ModCode

logger = logging.getLogger(__name__)


@dataclass
class LyraVersion:
    """Lyra版本信息。"""

    dol_ver: str  # DoL版本号，如 0.5.7.9
    chs_ver: str  # 汉化版本号，如 5.0.2a
    date: str  # 日期，如 0112

    @classmethod
    def from_tag(cls, tag: str) -> "LyraVersion":
        """从tag字符串解析版本信息。"""
        match = re.fullmatch(
            r"v?(?P<dol>\d+(?:\.\d+){3})-(?P<chs>\d+(?:\.\d+){2}[0-9A-Za-z]*)-(?P<date>\d{4})",
            tag,
        )
        if not match:
            raise ValueError(f"无法从版本字符串中提取版本信息: {tag}")
        return cls(dol_ver=match["dol"], chs_ver=match["chs"], date=match["date"])

    @property
    def tag(self) -> str:
        """返回完整的tag字符串"""
        return f"v{self.dol_ver}-{self.chs_ver}-{self.date}"

    def __str__(self) -> str:
        return self.tag


@dataclass
class VersionInfo:
    """资源版本信息记录。"""

    name: str  # 资源名称
    version: str  # 版本号
    source: str = ""  # 来源（如 GitHub repo）
    filename: str = ""  # 文件名

    def __str__(self) -> str:
        if self.version and self.version != "unknown":
            return f"{self.name}: {self.version}"
        return f"{self.name}: (no version)"


@dataclass
class VersionRegistry:
    """版本信息注册表。"""

    versions: list[VersionInfo] = field(default_factory=list)

    def add(self, info: VersionInfo):
        """添加版本信息"""
        for index, v in enumerate(self.versions):
            if v.name == info.name:
                self.versions[index] = info
                return
        self.versions.append(info)

    def extend(self, infos: list[VersionInfo]):
        """批量添加版本信息"""
        for info in infos:
            self.add(info)

    def save(self, path: Path):
        """保存版本信息到JSON文件。"""
        data = [asdict(v) for v in self.versions]
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"版本信息已保存: {path}")

    @classmethod
    def load(cls, path: Path) -> "VersionRegistry":
        """从JSON文件加载版本信息。"""
        if not path.exists():
            logger.warning(f"版本信息文件不存在: {path}")
            return cls()

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        versions = [VersionInfo(**item) for item in data]
        return cls(versions=versions)

    def print_summary(self):
        """打印版本信息摘要"""
        if not self.versions:
            return
        logger.info("=== 版本信息汇总 ===")
        for v in self.versions:
            logger.info(f"  {v}")

    def __len__(self) -> int:
        return len(self.versions)

    def __iter__(self):
        return iter(self.versions)


def package_filename(
    version: LyraVersion | None,
    mod_code: int,
    pack_type: str,
    is_polyfill: bool = False,
) -> str:
    """构建、下载页和发布校验使用相同的产物命名规则。"""
    if version is None:
        date = datetime.now(timezone(timedelta(hours=8))).strftime("%m%d")
        version = LyraVersion("unknown", "unknown", date)
    parts = [f"DoL-{version.dol_ver}-Lyra-{version.chs_ver}"]
    if is_polyfill:
        parts.append("polyfill")
    suffix = ModCode(mod_code).get_suffix()
    if suffix:
        parts.append(suffix)
    parts.append(version.date)
    return f"{'-'.join(parts)}.{pack_type}"
