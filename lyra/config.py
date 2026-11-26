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
        suffixes = (
            (ModCode.BESC, "besc"),
            (ModCode.SIDEVIEW_HIKARI, "hikari"),
            (ModCode.AU_FEMALE, "au-f"),
            (ModCode.UCB, "ucb"),
        )
        return "-".join(name for flag, name in suffixes if self & flag)
