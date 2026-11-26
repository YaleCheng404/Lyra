"""MOD组合计算模块。"""

from dataclasses import dataclass
from itertools import product
from pathlib import Path

from .config_loader import (
    CombinationsConfig,
    Feature,
    get_config_loader,
)


@dataclass
class ModCombination:
    code: int
    display_name: str
    is_recommended: bool


class CombinationCalculator:
    """MOD组合计算器（配置驱动）"""

    def __init__(self, config_dir: Path | None = None):
        self.loader = get_config_loader(config_dir)
        self._feature_map = {feature.id: feature for feature in self.loader.features}
        self._known_mask = 0
        for feature in self.features:
            self._known_mask |= feature.bit

    def _validate_code(self, value: int):
        if value <= 0 or value & ~self._known_mask:
            raise ValueError(f"组合包含未定义的功能位: {value}")

    @property
    def features(self) -> list[Feature]:
        return self.loader.features

    @property
    def combinations_config(self) -> CombinationsConfig:
        return self.loader.combinations

    def _should_skip(self, value: int) -> bool:
        if not value or value & ~self._known_mask or value in self.combinations_config.blacklist:
            return True

        enabled = {name for name, feature in self._feature_map.items() if value & feature.bit}
        for feature in self.features:
            if not value & feature.bit:
                if feature.required:
                    return True
            elif (
                feature.skip
                or not enabled.issuperset(feature.depends_on)
                or not enabled.isdisjoint(feature.conflicts_with)
            ):
                return True
        return False

    def _get_display_name(self, code: int) -> str:
        cheat_feature = self._feature_map.get("cheat_csd")
        if cheat_feature and code == cheat_feature.bit:
            return "基础"

        names = [
            feature.name
            for feature in sorted(self.features, key=lambda feature: feature.bit)
            if code & feature.bit and not feature.required and feature.name
        ]
        return "+".join(names) or "基础"

    def calculate(self) -> list[ModCombination]:
        codes = set()
        config = self.combinations_config

        for bits in product(*((0, feature.bit) for feature in self.features)):
            code = 0
            for bit in bits:
                code |= bit
            if not self._should_skip(code):
                codes.add(code)

        for code in config.whitelist:
            self._validate_code(code)
            codes.add(code)

        return [
            ModCombination(code, self._get_display_name(code), code in config.recommended)
            for code in sorted(codes, key=lambda code: (code not in config.recommended, code))
        ]

    def get_build_codes(self) -> list[str]:
        return [str(combination.code) for combination in self.calculate()]

    def to_string(self) -> str:
        """生成组合详情字符串（用于组合对照）。"""
        combinations = self.calculate()
        lines = []

        for comb in combinations:
            display_name = comb.display_name
            if comb.is_recommended:
                display_name = f"***{display_name}(推荐)***"

            binary = format(comb.code, "013b")
            lines.append(
                f"二进制: {binary:>15}, 十进制: {comb.code:>5}, "
                f"功能: {display_name}, 推荐： {int(comb.is_recommended)}"
            )

        lines.append(str(sorted(combination.code for combination in combinations)))
        return "\n".join(lines)
