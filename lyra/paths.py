"""路径管理模块。"""

from dataclasses import dataclass, field
from pathlib import Path

from .config_loader import BuildConfiguration, load_build_config


@dataclass
class BuildPaths:
    """构建路径管理器。"""

    workspace: Path = Path(".")
    _config: BuildConfiguration | None = field(default=None, repr=False)

    def __post_init__(self):
        if self._config is None:
            self._config = load_build_config()
        self.workspace = Path(self.workspace)

    @property
    def base_dir(self) -> Path:
        return self.workspace / self._config.base_dir

    @property
    def output_dir(self) -> Path:
        return self.workspace / self._config.output_dir

    @property
    def workspace_inner(self) -> Path:
        return self.workspace / self._config.workspace_dir

    @property
    def prepare_dir(self) -> Path:
        return self.workspace_inner / self._config.prepare_package_dir

    @property
    def temp_dir(self) -> Path:
        return self.workspace_inner / self._config.temp_dir

    @property
    def extract_dir(self) -> Path:
        return self.workspace_inner / self._config.extract_dir

    @property
    def signed_dir(self) -> Path:
        return self.workspace_inner / self._config.signed_dir

    def get_base_zip(self) -> Path:
        return self.base_dir / "base.zip"

    def get_apk_dir(self) -> Path:
        return self.prepare_dir / "apk"

    @property
    def apktool_path(self) -> Path:
        return self.workspace / "apktool.jar"

    @property
    def apksign_path(self) -> Path:
        return self.workspace / "uber-apk-signer.jar"

    @property
    def versions_file(self) -> Path:
        return self.base_dir / "versions.json"

    def get_beautify_cache_dir(self, name: str) -> Path:
        return self.temp_dir / ("sideview_hikari" if name == "hikari" else name)

    def get_mod_cache_path(self, name: str) -> Path:
        return self.temp_dir / f"{name}.mod.zip"

    def get_build_work_dir(self, pack_type: str, mod_code: int) -> Path:
        return self.extract_dir / pack_type / str(mod_code)

    def get_temp_apk(self, mod_code: int) -> Path:
        return self.workspace_inner / f"tmp_{mod_code}.apk"

    def get_signed_dir(self, mod_code: int) -> Path:
        return self.signed_dir / str(mod_code)

    def ensure_dirs(self) -> None:
        for directory in (
            self.base_dir,
            self.output_dir,
            self.prepare_dir,
            self.temp_dir,
            self.extract_dir,
            self.signed_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
