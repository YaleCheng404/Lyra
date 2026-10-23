"""配置管理模块。"""

from enum import IntFlag


class ModCode(IntFlag):
    """MOD代码位标志定义"""

    BESC = 1  # BEEESSS社区精灵合集
    CHEAT = 2  # 作弊功能
    CSD = 4  # CSD
    SIDEVIEW_BJ = 8  # BJ特写
    SIDEVIEW_KR = 16  # KR特写
    SIDEVIEW_HIKARI = 32  # Hikari特写
    WAX = 64  # WAX美化
    SUSATO = 128  # Susato模型
    UCB = 256  # 通用战斗美化
    SIDEVIEW_GOOSE = 512  # Goose特写
    AU_FEMALE = 1024  # AU女性
    AU_MALE = 2048  # AU男性
    AU_ANDROGYNOUS = 4096  # AU双性

    def get_suffix(self) -> str:
        """获取基于MOD代码的文件名后缀"""
        suffix_parts = []

        if self & ModCode.BESC:
            suffix_parts.append("besc")
        if self & ModCode.SUSATO:
            suffix_parts.append("susato")
        if self & ModCode.SIDEVIEW_BJ:
            suffix_parts.append("sideviewbj")
        if self & ModCode.SIDEVIEW_KR:
            suffix_parts.append("sideviewkr")
        if self & ModCode.SIDEVIEW_HIKARI:
            suffix_parts.append("hikari")
        if self & ModCode.SIDEVIEW_GOOSE:
            suffix_parts.append("goose")
        if self & ModCode.AU_FEMALE:
            suffix_parts.append("au-f")
        if self & ModCode.AU_MALE:
            suffix_parts.append("au-m")
        if self & ModCode.AU_ANDROGYNOUS:
            suffix_parts.append("au-a")
        if self & ModCode.UCB:
            suffix_parts.append("ucb")

        return "-".join(suffix_parts) if suffix_parts else ""
