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
    """MOD组合"""

    code: int
    binary: str = ""
    display_name: str = ""
    is_recommended: bool = False
    is_polyfill: bool = False

    def __post_init__(self):
        if not self.binary:
            self.binary = format(self.code, "013b")

    def __lt__(self, other):
        return self.code < other.code

    def __eq__(self, other):
        if isinstance(other, ModCombination):
            return self.code == other.code and self.is_polyfill == other.is_polyfill
        return False

    def __hash__(self):
        return hash((self.code, self.is_polyfill))


class CombinationCalculator:
    """MOD组合计算器（配置驱动）"""

    def __init__(self, config_dir: Path | None = None):
        """初始化计算器。"""
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
        """获取所有功能"""
        return self.loader.features

    @property
    def combinations_config(self) -> CombinationsConfig:
        """获取组合配置"""
        return self.loader.combinations

    def _has_feature(self, value: int, feature_id: str) -> bool:
        """检查组合中是否包含指定功能"""
        feature = self._feature_map.get(feature_id)
        if feature is None:
            return False
        return bool(value & feature.bit)

    def _has_bit(self, value: int, bit: int) -> bool:
        """检查指定位是否为1"""
        return bool(value & bit)

    def _check_dependencies(self, value: int) -> bool:
        """检查依赖关系。"""
        for feature in self.features:
            if not self._has_bit(value, feature.bit):
                continue

            for dep_id in feature.depends_on:
                if not self._has_feature(value, dep_id):
                    return False

        return True

    def _check_conflicts(self, value: int) -> bool:
        """检查冲突关系。"""
        for feature in self.features:
            if not self._has_bit(value, feature.bit):
                continue

            for conflict_id in feature.conflicts_with:
                if self._has_feature(value, conflict_id):
                    return False

        return True

    def _should_skip(self, value: int) -> bool:
        """检查是否应该跳过此组合"""
        if value == 0 or value & ~self._known_mask:
            return True

        for feature in self.features:
            if feature.required and not self._has_bit(value, feature.bit):
                return True

        for feature in self.features:
            if feature.skip and self._has_bit(value, feature.bit):
                return True

        if not self._check_dependencies(value):
            return True

        if not self._check_conflicts(value):
            return True

        return value in self.combinations_config.blacklist

    def _get_display_name(self, code: int) -> str:
        """获取组合的显示名称"""
        cheat_feature = self._feature_map.get("cheat_csd")
        if cheat_feature and code == cheat_feature.bit:
            return "基础"

        parts = []

        # 按位值从低到高排序，使得基础功能（如 BESC）排在前面
        sorted_features = sorted(self.features, key=lambda f: f.bit)

        for feature in sorted_features:
            if self._has_bit(code, feature.bit):
                # 跳过作弊CSD的显示（它始终存在）
                if feature.required:
                    continue
                if feature.name:
                    parts.append(feature.name)

        return "+".join(parts) if parts else "基础"

    def calculate(self, include_polyfill: bool = True) -> list[ModCombination]:
        """计算所有有效的MOD组合。"""
        combinations = []
        config = self.combinations_config

        for selected in product((False, True), repeat=len(self.features)):
            i = 0
            for feature, enabled in zip(self.features, selected):
                if enabled:
                    i |= feature.bit
            if not self._should_skip(i):
                comb = ModCombination(
                    code=i,
                    display_name=self._get_display_name(i),
                    is_recommended=i in config.recommended,
                )
                combinations.append(comb)

        existing_codes = {c.code for c in combinations}
        for code in config.whitelist:
            self._validate_code(code)
            if code not in existing_codes:
                comb = ModCombination(
                    code=code,
                    display_name=self._get_display_name(code),
                    is_recommended=code in config.recommended,
                )
                combinations.append(comb)

        # 排序：推荐的放前面，然后按code排序
        combinations.sort(key=lambda x: (-x.is_recommended, x.code))

        if include_polyfill and config.polyfill_enabled:
            self._validate_code(config.polyfill_code)
            polyfill_comb = ModCombination(
                code=config.polyfill_code,
                display_name=self._get_display_name(config.polyfill_code) + "(兼容版)",
                is_recommended=False,
                is_polyfill=True,
            )
            combinations.insert(0, polyfill_comb)

        return combinations

    def get_build_codes(self, include_polyfill: bool = True) -> list[str]:
        """获取用于构建的code列表（字符串格式）。"""
        combinations = self.calculate(include_polyfill=include_polyfill)
        codes = []

        for comb in combinations:
            if comb.is_polyfill:
                codes.append(f"polyfill-{comb.code}")
            else:
                codes.append(str(comb.code))

        return codes

    def to_string(self) -> str:
        """生成组合详情字符串（用于组合对照）。"""
        combinations = self.calculate(include_polyfill=False)  # 组合对照不包含 polyfill
        lines = []

        for comb in combinations:
            display_name = comb.display_name
            if comb.is_recommended:
                display_name = f"***{display_name}(推荐)***"

            rec = 1 if comb.is_recommended else 0
            # 格式：二进制: 0b11, 十进制: 3, 功能: ***BESC(推荐)***, 推荐： 1
            lines.append(
                f"二进制: {comb.binary:>15}, 十进制: {comb.code:>5}, "
                f"功能: {display_name}, 推荐： {rec}"
            )

        sorted_combinations = sorted(combinations, key=lambda c: c.code)
        codes = [c.code for c in sorted_combinations]
        lines.append(f"{codes}")

        return "\n".join(lines)
