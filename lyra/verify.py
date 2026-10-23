"""发布前独立检查产物集合与原始 Mod 载荷。"""

import base64
import hashlib
import json
import logging
import zipfile
from dataclasses import asdict
from pathlib import Path

from scripts.modmagic import extract_mod_list

from .combo import CombinationCalculator
from .config_loader import load_build_config
from .paths import BuildPaths
from .version import LyraVersion, VersionRegistry, package_filename

logger = logging.getLogger(__name__)


def verify_packages(
    paths: BuildPaths, version: LyraVersion | None = None
) -> list[dict]:
    """校验所有目标；任何缺包、额外包或 Mod 载荷差异均阻止发布。"""
    expected = {}
    for code in CombinationCalculator().get_build_codes():
        for kind in ("zip", "apk"):
            name = package_filename(
                version,
                int(code.removeprefix("polyfill-")),
                kind,
                code.startswith("polyfill-"),
            )
            expected[name] = kind
    actual = {
        p.name for p in paths.output_dir.iterdir() if p.suffix in {".zip", ".apk"}
    }
    if actual != set(expected):
        raise ValueError(
            f"产物集合不符: missing={sorted(set(expected) - actual)}, "
            f"unexpected={sorted(actual - set(expected))}"
        )

    registry = list(VersionRegistry.load(paths.versions_file))
    required = []
    for mod in load_build_config().base_mods:
        if not mod.required:
            continue
        records = [
            v
            for v in registry
            if v.name == (mod.name or mod.key) and v.source == mod.github_repo
        ]
        if len(records) != 1 or not records[0].filename:
            raise ValueError(f"缺少必需 Mod 版本记录: {mod.key}")
        record = records[0]
        if Path(record.filename).name != record.filename:
            raise ValueError(f"无效 Mod 文件名: {record.filename}")
        source = paths.base_dir / "mods" / record.filename
        payload = source.read_bytes()
        if source.name.endswith(".mod.zip"):
            with zipfile.ZipFile(source) as archive:
                if (
                    archive.testzip() is not None
                    or "boot.json" not in archive.namelist()
                ):
                    raise ValueError(f"无效 Mod ZIP: {source}")
        elif not payload.startswith(b"JeremieModLoader") or len(payload) < 128:
            raise ValueError(f"无效 ModPack: {source}")
        required.append((record, hashlib.sha256(payload).hexdigest()))

    report = []
    for name, kind in sorted(expected.items()):
        package = paths.output_dir / name
        with zipfile.ZipFile(package) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError(f"{name}: CRC 校验失败: {bad}")
            html_name = (
                "assets/www/index.html"
                if kind == "apk"
                else next(
                    (
                        n
                        for n in archive.namelist()
                        if n.endswith(".html") and "/" not in n
                    ),
                    "",
                )
            )
            html = archive.read(html_name).decode("utf-8")
        hashes = [
            hashlib.sha256(base64.b64decode(item, validate=True)).hexdigest()
            for item in extract_mod_list(html)
        ]
        indices = []
        for record, digest in required:
            if hashes.count(digest) != 1:
                raise ValueError(
                    f"{name}: 必需 Mod 缺失、重复或字节不符: {record.name}"
                )
            indices.append(hashes.index(digest))
        if indices != sorted(indices):
            raise ValueError(f"{name}: 必需 Mod 注入顺序不符")
        report.append(
            {
                "filename": name,
                "size": package.stat().st_size,
                "required_mods": [asdict(v) for v, _ in required],
            }
        )
        logger.info("校验通过: %s", name)

    (paths.output_dir / "build-manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    notes = [
        f"# Lyra {version.tag if version else 'development'}",
        "",
        "所有组合包含秋枫白桦框架、枯木逢春本体与音频、默示录：归途之书及极致动态 Dynamicest。",
        "",
        "| 资源 | 实际版本 | 来源 |",
        "|---|---|---|",
    ]
    notes.extend(
        f"| {v.name} | {v.version} | [{v.source}](https://github.com/{v.source}) |"
        for v, _ in required
    )
    notes.extend(
        [
            "",
            "提供 BESC、Hikari、UCB 和 AU-F，共八种组合、16 个 ZIP/APK 文件。",
            "每天香港时间 04:17 检查上游汉化，发现新汉化后同步最新正式版 Mod 并发布。",
            "",
            "升级前请导出并备份存档。音频包随整合提供，可在模组设置中启用。",
            "",
        ]
    )
    (paths.output_dir / "release-notes.md").write_text(
        "\n".join(notes), encoding="utf-8"
    )
    return report
