"""配置管理模块。"""

from enum import IntFlag


class ModCode(IntFlag):
    """MOD代码位标志定义"""

    BESC = 1  # BEEESSS社区精灵合集
    CHEAT = 2  # 作弊功能
    SIDEVIEW_HIKARI = 32  # Hikari特写
    UCB = 256  # 通用战斗美化
    AU_FEMALE = 1024  # AU女性

    def get_suffix(self) -> str:
        """获取基于MOD代码的文件名后缀"""
        suffix_parts = []

        if self & ModCode.BESC:
            suffix_parts.append("besc")
        if self & ModCode.SIDEVIEW_HIKARI:
            suffix_parts.append("hikari")
        if self & ModCode.AU_FEMALE:
            suffix_parts.append("au-f")
        if self & ModCode.UCB:
            suffix_parts.append("ucb")

        return "-".join(suffix_parts) if suffix_parts else ""
