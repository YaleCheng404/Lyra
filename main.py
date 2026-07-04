#!/usr/bin/env python3
"""
DoL-Lyra 构建系统

统一的 CI 构建入口，提供以下命令：

  prepare   - 下载并预处理游戏资源（生成基包）
  warmup    - 预热美化资源（下载并解压所有美化包）
  build     - 并行构建所有组合
  page      - 生成下载页面
  matrix    - 生成 GitHub Actions 构建矩阵
  check     - 检查是否需要更新

典型 CI 流程：
  1. lyra prepare --tag v0.5.7.9-5.0.2a-0112
  2. lyra warmup
  3. lyra build --tag v0.5.7.9-5.0.2a-0112
  4. lyra page --tag v0.5.7.9-5.0.2a-0112
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from lyra import __version__
from lyra.paths import BuildPaths
from lyra.version import LyraVersion, VersionRegistry
from lyra.utils import setup_logging

logger = logging.getLogger(__name__)


def cmd_prepare(args) -> int:
    """
    准备游戏资源命令

    下载游戏文件、额外 mod，生成 ZIP 基包和 APK 解包目录。
    """
    from lyra.downloader import Downloader, GamePreparer
    from lyra.prepare import GamePreparer as FullPreparer

    setup_logging(args.verbose)
    logger.info(f"DoL-Lyra 构建系统 v{__version__}")

    # 解析版本
    version = LyraVersion.from_tag(args.tag) if args.tag else None
    if version:
        logger.info(f"目标版本: {version}")

    # 初始化路径
    paths = BuildPaths(workspace=Path(args.workspace))
    paths.ensure_dirs()

    # 下载资源
    downloader = Downloader(paths)
    downloaded_files = downloader.download_from_chs_repo(version)
    extra_mods = downloader.download_extra_mods()

    # 下载工具
    downloader.download_apktool()
    downloader.download_apksign()

    # 处理 i18n mod (从下载的文件中)
    if "i18n" in downloaded_files:
        extra_mods["i18n"] = downloaded_files["i18n"]

    # 预处理
    preparer = FullPreparer(paths)
    preparer.prepare_all(downloaded_files, extra_mods)

    # 合并并保存版本信息
    registry = VersionRegistry()
    registry.extend(list(downloader.registry))
    registry.extend(list(preparer.registry))
    registry.save(paths.versions_file)

    logger.info("准备完成！")
    return 0


def cmd_warmup(args) -> int:
    """
    预热美化资源命令

    下载并解压所有美化资源，避免并行构建时的冲突。
    """
    from lyra.warmup import ResourceWarmer

    setup_logging(args.verbose)
    logger.info(f"DoL-Lyra 构建系统 v{__version__}")

    # 初始化路径
    paths = BuildPaths(workspace=Path(args.workspace))
    paths.ensure_dirs()

    # 预热资源
    warmer = ResourceWarmer(paths)
    registry = warmer.warmup_all()

    # 加载已有版本信息并合并
    existing_registry = VersionRegistry.load(paths.versions_file)
    existing_registry.extend(list(registry))
    existing_registry.save(paths.versions_file)

    logger.info("预热完成！")
    return 0


def cmd_build(args) -> int:
    """
    构建命令

    并行构建所有 MOD 组合。
    """
    from lyra.parallel import build_all_parallel

    setup_logging(args.verbose)
    logger.info(f"DoL-Lyra 构建系统 v{__version__}")

    # 解析版本
    version = LyraVersion.from_tag(args.tag) if args.tag else None
    if version:
        logger.info(f"构建版本: {version}")

    # 初始化路径
    paths = BuildPaths(workspace=Path(args.workspace))
    paths.ensure_dirs()

    # 确定包类型
    pack_types = [args.pack_type] if args.pack_type else ["zip", "apk"]

    # 并行构建
    success, fail = build_all_parallel(
        paths=paths,
        version=version,
        pack_types=pack_types,
        max_workers=args.jobs,
        include_polyfill=True,
        verbose=args.verbose,
    )

    return 0 if fail == 0 else 1


def cmd_page(args) -> int:
    """
    生成下载页面命令
    """
    from lyra.gen_page import generate_download_page

    setup_logging(args.verbose)

    # 解析版本
    version = args.version or (args.tag if args.tag else None)

    output_path = Path(args.output) if args.output else None
    versions_file = Path(args.versions_file) if args.versions_file else None

    content = generate_download_page(
        version=version,
        output_path=output_path,
        github_owner=args.github_owner,
        github_repo=args.github_repo,
        versions_file=versions_file,
    )

    if not output_path:
        print(content)
    else:
        logger.info(f"下载页面已生成: {output_path}")

    return 0


def cmd_matrix(args) -> int:
    """
    生成构建矩阵命令（用于 GitHub Actions）
    """
    from lyra.combo import CombinationCalculator

    calculator = CombinationCalculator()
    codes = calculator.get_build_codes(include_polyfill=True)

    codes = sorted(
        codes,
        key=lambda x: (x.startswith("polyfill-"), int(x.replace("polyfill-", "0"))),
    )

    if args.output_format == "shell":
        # Shell 数组格式
        print("CODES=(" + " ".join(f'"{c}"' for c in codes) + ")")
    else:
        # JSON 格式
        print(json.dumps(codes))

    return 0


def cmd_list(args) -> int:
    """
    列出所有 MOD 组合
    """
    from lyra.combo import CombinationCalculator

    calculator = CombinationCalculator()
    print(calculator.to_string())
    return 0


def cmd_check(args) -> int:
    """
    检查是否需要更新
    """
    import requests

    from lyra.config_loader import load_build_config

    setup_logging(args.verbose)

    build_config = load_build_config()
    source_repo = args.source_repo or build_config.chs_repo_url

    current_repo = os.environ.get("GITHUB_REPOSITORY", "")
    current_owner, _, current_name = current_repo.partition("/")
    github_owner = args.github_owner or current_owner or build_config.github_owner
    github_repo = args.github_repo or current_name or build_config.github_repo

    if not github_owner or not github_repo:
        logger.error("无法确定当前 GitHub 仓库，请传入 --github-owner 和 --github-repo")
        return 1

    # 获取汉化仓库最新 release
    url = f"https://api.github.com/repos/{source_repo}/releases/latest"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        origin_tag = response.json().get("tag_name", "")
    except Exception as e:
        logger.error(f"获取汉化仓库版本失败: {e}")
        return 1

    # 解析版本号，格式: v0.5.7.9-chs-5.1.0a
    try:
        origin_parts = origin_tag.split("-")
        game_ver = origin_parts[0].lstrip("v")
        chs_ver = origin_parts[2]
    except IndexError:
        logger.error(f"无法解析汉化仓库版本: {origin_tag}")
        return 1

    # 获取本仓库最新 tag
    lyra_tag = ""
    lyra_game_ver = ""
    lyra_chs_ver = ""
    try:
        mods_url = f"https://api.github.com/repos/{github_owner}/{github_repo}/releases/latest"
        response = requests.get(mods_url, timeout=30)
        response.raise_for_status()
        lyra_tag = response.json().get("tag_name", "")
        lyra_parts = lyra_tag.split("-")
        lyra_game_ver = lyra_parts[0].lstrip("v")
        lyra_chs_ver = lyra_parts[1]
    except Exception as e:
        logger.warning(f"获取本仓库版本失败（可能是首次发布）: {e}")

    need_update = (game_ver != lyra_game_ver) or (chs_ver != lyra_chs_ver)

    from datetime import datetime, timezone, timedelta

    # UTC+8 时间
    tz = timezone(timedelta(hours=8))
    date_str = datetime.now(tz).strftime("%m%d")

    result = {
        "need_update": need_update,
        "origin_tag": origin_tag,
        "game_ver": game_ver,
        "chs_ver": chs_ver,
        "lyra_game_ver": lyra_game_ver,
        "lyra_chs_ver": lyra_chs_ver,
        "new_tag": f"v{game_ver}-{chs_ver}-{date_str}",
    }

    if need_update:
        logger.info("需要更新！")
        logger.info(f"  汉化仓库 ({source_repo}): {origin_tag}")
        logger.info(f"  本仓库 ({github_owner}/{github_repo}): {lyra_tag or '(无发布)'}")
    else:
        logger.info("当前已是最新版本")

    if args.github_output:
        with open(args.github_output, "a") as f:
            f.write(f"need_update={'true' if need_update else 'false'}\n")
            f.write(f"origin_tag={origin_tag}\n")
            f.write(f"game_ver={game_ver}\n")
            f.write(f"chs_ver={chs_ver}\n")
            f.write(f"new_tag={result['new_tag']}\n")
    else:
        print(json.dumps(result))

    return 0


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="DoL-Lyra 构建系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # prepare 命令
    prep_parser = subparsers.add_parser(
        "prepare",
        help="下载并预处理游戏资源",
        description="下载游戏文件、额外 mod，生成 ZIP 基包和 APK 解包目录。",
    )
    prep_parser.add_argument(
        "--tag",
        help="版本 tag（格式: v0.5.7.9-5.0.2a-0112）",
    )
    prep_parser.add_argument("--workspace", default=".", help="工作目录")
    prep_parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    # warmup 命令
    warmup_parser = subparsers.add_parser(
        "warmup",
        help="预热美化资源",
        description="下载并解压所有美化资源，避免并行构建时的冲突。",
    )
    warmup_parser.add_argument("--workspace", default=".", help="工作目录")
    warmup_parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    # build 命令
    build_parser = subparsers.add_parser(
        "build",
        help="并行构建所有组合",
        description="使用进程池并行构建所有 MOD 组合。",
    )
    build_parser.add_argument(
        "pack_type",
        nargs="?",
        choices=["zip", "apk"],
        help="包类型（可选，默认构建两种）",
    )
    build_parser.add_argument(
        "--tag",
        help="版本 tag（格式: v0.5.7.9-5.0.2a-0112）",
    )
    build_parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        help="并发进程数（默认: min(CPU核心数, 4)）",
    )
    build_parser.add_argument("--workspace", default=".", help="工作目录")
    build_parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    # page 命令
    page_parser = subparsers.add_parser(
        "page",
        help="生成下载页面",
    )
    page_parser.add_argument("--version", dest="version", help="版本号")
    page_parser.add_argument("--tag", help="版本 tag（替代 --version）")
    page_parser.add_argument("--output", help="输出文件路径")
    page_parser.add_argument("--github-owner", help="GitHub 用户名")
    page_parser.add_argument("--github-repo", help="GitHub 仓库名")
    page_parser.add_argument("--versions-file", help="版本信息文件路径")
    page_parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    # matrix 命令
    matrix_parser = subparsers.add_parser(
        "matrix",
        help="生成构建矩阵",
    )
    matrix_parser.add_argument(
        "--output-format",
        choices=["json", "shell"],
        default="json",
        help="输出格式",
    )

    # list 命令
    list_parser = subparsers.add_parser(
        "list",
        help="列出所有 MOD 组合",
    )

    # check 命令
    check_parser = subparsers.add_parser(
        "check",
        help="检查是否需要更新",
    )
    check_parser.add_argument("--github-output", help="GitHub Actions 输出文件")
    check_parser.add_argument(
        "--source-repo",
        help="上游汉化仓库，格式 owner/repo（默认读取 config/build.toml）",
    )
    check_parser.add_argument(
        "--github-owner", help="GitHub 用户名（默认使用 GITHUB_REPOSITORY 或配置文件）"
    )
    check_parser.add_argument(
        "--github-repo", help="GitHub 仓库名（默认使用 GITHUB_REPOSITORY 或配置文件）"
    )
    check_parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "prepare": cmd_prepare,
        "warmup": cmd_warmup,
        "build": cmd_build,
        "page": cmd_page,
        "matrix": cmd_matrix,
        "list": cmd_list,
        "check": cmd_check,
    }

    try:
        return commands[args.command](args)
    except KeyboardInterrupt:
        logger.info("用户中断")
        return 130
    except Exception as e:
        logger.error(f"执行失败: {e}")
        if args.verbose if hasattr(args, "verbose") else False:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
