"""上游汉化版本检查模块。"""

import logging
import re
from datetime import datetime, timedelta, timezone

import requests

from lyra.version import LyraVersion

logger = logging.getLogger(__name__)

# 上游 tag 格式: v{game}-chs-{chs}，例如 v0.5.10.12-chs-1.0.8a
_ORIGIN_TAG_RE = re.compile(r"v(?P<game>\d+(?:\.\d+){3})-chs-(?P<chs>\d+(?:\.\d+){2}[0-9A-Za-z]*)")

def check_chs_update(source_repo, github_owner, github_repo, get=None):
    """检查汉化仓库是否有新版本。

    Args:
        source_repo: 上游汉化仓库，格式 owner/repo
        github_owner: 本仓库 owner
        github_repo: 本仓库名
        get: 可调用对象，默认 requests.get，便于测试注入

    Returns:
        检查结果字典，包含 need_update/origin_tag/game_ver/chs_ver/lyra_*/new_tag
    """
    get = get or requests.get

    # 获取汉化仓库最新 release
    url = f"https://api.github.com/repos/{source_repo}/releases/latest"
    response = get(url, timeout=30)
    response.raise_for_status()
    origin_tag = response.json().get("tag_name", "")

    # 解析并限制版本号，避免外部 tag 成为工作流脚本内容。
    match = _ORIGIN_TAG_RE.fullmatch(origin_tag)
    if not match:
        raise ValueError(f"无法解析汉化仓库版本: {origin_tag}")
    game_ver, chs_ver = match["game"], match["chs"]

    # 获取本仓库最新 tag（首次发布时无 release，视为需要更新）
    lyra_tag = ""
    lyra_game_ver = ""
    lyra_chs_ver = ""
    try:
        mods_url = f"https://api.github.com/repos/{github_owner}/{github_repo}/releases/latest"
        response = get(mods_url, timeout=30)
        response.raise_for_status()
        lyra_tag = response.json().get("tag_name", "")
        lyra_version = LyraVersion.from_tag(lyra_tag)
        lyra_game_ver = lyra_version.dol_ver
        lyra_chs_ver = lyra_version.chs_ver
    except Exception as e:
        logger.warning(f"获取本仓库版本失败（可能是首次发布）: {e}")

    need_update = (game_ver != lyra_game_ver) or (chs_ver != lyra_chs_ver)

    # UTC+8 时间
    tz = timezone(timedelta(hours=8))
    date_str = datetime.now(tz).strftime("%m%d")

    return {
        "need_update": need_update,
        "origin_tag": origin_tag,
        "game_ver": game_ver,
        "chs_ver": chs_ver,
        "lyra_tag": lyra_tag,
        "lyra_game_ver": lyra_game_ver,
        "lyra_chs_ver": lyra_chs_ver,
        "new_tag": f"v{game_ver}-{chs_ver}-{date_str}",
    }
