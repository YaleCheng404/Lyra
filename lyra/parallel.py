"""使用进程池构建 MOD 组合。"""

import logging
import os
from concurrent.futures import ProcessPoolExecutor, as_completed

from .build import BuildTask, PackageBuilder
from .combo import CombinationCalculator
from .paths import BuildPaths
from .utils import setup_logging
from .version import LyraVersion

logger = logging.getLogger(__name__)


def _build_task_worker(task: BuildTask, verbose: bool) -> tuple[bool, str | None]:
    # Windows 的 spawn 子进程需要单独初始化日志。
    setup_logging(verbose)
    result = PackageBuilder(task).build()
    return result.success, result.error


def build_all_parallel(
    paths: BuildPaths,
    version: LyraVersion | None = None,
    pack_types: list[str] | None = None,
    max_workers: int | None = None,
    include_polyfill: bool = True,
    verbose: bool = False,
) -> tuple[int, int]:
    """按包类型分批构建，返回成功数和失败数。"""
    codes = sorted(
        CombinationCalculator().get_build_codes(include_polyfill=include_polyfill),
        key=lambda code: (
            code.startswith("polyfill-"),
            int(code.removeprefix("polyfill-")),
        ),
    )
    pack_types = pack_types or ["zip", "apk"]
    if max_workers is None:
        max_workers = min(os.cpu_count() or 4, 4)
    if max_workers < 1:
        raise ValueError("并发进程数必须大于 0")

    success_count = fail_count = 0
    logger.info("开始构建: %s 个任务", len(codes) * len(pack_types))
    for pack_type in pack_types:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _build_task_worker,
                    BuildTask.from_code_str(code, pack_type, version, paths),
                    verbose,
                ): code
                for code in codes
            }
            for future in as_completed(futures):
                code = futures[future]
                try:
                    success, error = future.result()
                except Exception as exc:
                    success, error = False, str(exc)
                if success:
                    success_count += 1
                else:
                    fail_count += 1
                    logger.error("失败 [%s] %s: %s", pack_type, code, error)

    logger.info("构建完成: 成功 %s, 失败 %s", success_count, fail_count)
    return success_count, fail_count
