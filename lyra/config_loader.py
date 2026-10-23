"""配置加载模块。"""

import logging
import tomllib
from dataclasses import dataclass, field
from functools import cache, cached_property
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = Path(__file__).parent.parent / "config"


@dataclass
class Feature:
    """功能定义"""

    id: str
    name: str
    bit: int
    required: bool = False
    skip: bool = False
    depends_on: list[str] = field(default_factory=list)
    conflicts_with: list[str] = field(default_factory=list)


@dataclass
class CombinationsConfig:
    """组合配置"""

    recommended: list[int] = field(default_factory=list)
    whitelist: list[int] = field(default_factory=list)
    blacklist: list[int] = field(default_factory=list)
    polyfill_enabled: bool = True
    polyfill_code: int = 3

    @classmethod
    def from_dict(cls, data: dict) -> "CombinationsConfig":
        polyfill = data.get("polyfill", {})
        return cls(
            recommended=data.get("recommended", []),
            whitelist=data.get("whitelist", []),
            blacklist=data.get("blacklist", []),
            polyfill_enabled=polyfill.get("enabled", True),
            polyfill_code=polyfill.get("code", 3),
        )


@dataclass
class Replacement:
    """替换规则"""

    file: str
    pattern: str
    replacement: str


@dataclass
class ImagePackConfig:
    """图片包配置"""

    name: str
    urls: list[str] = field(default_factory=list)
    case_fixes: dict[str, str] = field(default_factory=dict)
    files_to_remove: list[str] = field(default_factory=list)


@dataclass
class ModloaderModConfig:
    """Modloader mod 配置"""

    feature_id: str
    github_repo: str
    asset_pattern: str
    release_tag: str = "latest"


@dataclass
class BaseModConfig:
    """基础 mod 注入配置"""

    key: str  # mod 标识，对应 extra_mods 字典中的键
    github_repo: str = ""  # GitHub 仓库，自动下载最新 .mod.zip（可选）
    inject: str = "add"  # 注入方式: "add" 追加 / "replace" 替换指定 slot
    replace_slot: int = 0  # 替换的 slot 索引（仅 inject="replace" 时有效）
    name: str = ""
    asset_pattern: str = "*.mod.zip"
    required: bool = False


@dataclass
class BuildConfiguration:
    """完整构建配置"""

    apktool_url: str
    apktool_sha256: str
    uber_apk_signer_url: str
    uber_apk_signer_sha256: str
    chs_repo_url: str

    workspace_dir: str
    output_dir: str
    extract_dir: str
    temp_dir: str
    signed_dir: str
    base_dir: str
    prepare_package_dir: str

    github_owner: str
    github_repo: str

    apk_replacements: list[Replacement] = field(default_factory=list)

    imagepacks: dict[str, ImagePackConfig] = field(default_factory=dict)

    modloader_mods: list[ModloaderModConfig] = field(default_factory=list)

    base_mods: list[BaseModConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "BuildConfiguration":
        urls = data.get("urls", {})
        paths = data.get("paths", {})
        github = data["github"]
        apk = data.get("apk", {})

        replacements = [Replacement(**r) for r in apk.get("replacements", [])]

        dolp_base = urls["dolp_base"]
        imagepacks = {}
        for name, pack_data in data.get("imagepacks", {}).items():
            imagepacks[name] = ImagePackConfig(
                **{
                    **pack_data,
                    "name": name,
                    "urls": [
                        url.replace("{dolp_base}", dolp_base)
                        for url in pack_data.get("urls", [])
                    ],
                }
            )

        modloader_mods = [
            ModloaderModConfig(**m) for m in data.get("modloader_mods", [])
        ]

        base_mods = [
            BaseModConfig(**{"name": m["key"], **m}) for m in data.get("base_mods", [])
        ]

        chs_repo = urls.get(
            "chs_repo", "Eltirosto/Degrees-of-Lewdity-Chinese-Localization"
        )

        return cls(
            apktool_url=urls["apktool"],
            apktool_sha256=urls["apktool_sha256"],
            uber_apk_signer_url=urls["uber_apk_signer"],
            uber_apk_signer_sha256=urls["uber_apk_signer_sha256"],
            chs_repo_url=chs_repo,
            workspace_dir=paths["workspace"],
            output_dir=paths["output"],
            extract_dir=paths["extract"],
            temp_dir=paths["temp"],
            signed_dir=paths["signed"],
            base_dir=paths["base"],
            prepare_package_dir=paths["prepare_package"],
            github_owner=github["owner"],
            github_repo=github["repo"],
            apk_replacements=replacements,
            imagepacks=imagepacks,
            modloader_mods=modloader_mods,
            base_mods=base_mods,
        )


class ConfigLoader:
    """同一配置目录只解析一次；不同目录互不影响。"""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir

    def _load_toml(self, filename: str) -> dict:
        filepath = self.config_dir / filename
        if not filepath.exists():
            logger.warning("配置文件不存在: %s", filepath)
            return {}
        with filepath.open("rb") as stream:
            return tomllib.load(stream)

    @cached_property
    def features(self) -> list[Feature]:
        return [
            Feature(**{"name": "", **item})
            for item in self._load_toml("features.toml").get("features", [])
        ]

    @cached_property
    def combinations(self) -> CombinationsConfig:
        return CombinationsConfig.from_dict(self._load_toml("combinations.toml"))

    @cached_property
    def build(self) -> BuildConfiguration:
        return BuildConfiguration.from_dict(self._load_toml("build.toml"))

    def get_feature_by_id(self, feature_id: str) -> Feature | None:
        return next(
            (feature for feature in self.features if feature.id == feature_id), None
        )


@cache
def _get_config_loader(config_dir: Path) -> ConfigLoader:
    return ConfigLoader(config_dir)


def get_config_loader(config_dir: Path | None = None) -> ConfigLoader:
    return _get_config_loader(Path(config_dir or DEFAULT_CONFIG_DIR).resolve())


def load_build_config(config_dir: Path | None = None) -> BuildConfiguration:
    return get_config_loader(config_dir).build
