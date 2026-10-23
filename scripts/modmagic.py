"""编辑 HTML 中的 ModLoader 内置 Mod 列表。"""

import argparse
import base64
import json
import logging
import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)
MOD_LIST_PATTERN = re.compile(
    r"window\.modDataValueZipList\s*=\s*(\[.*?\]);", re.DOTALL
)


def load_file_as_base64(file_path: str | Path) -> str:
    return base64.b64encode(Path(file_path).read_bytes()).decode("ascii")


def extract_boot_json_from_base64_zip(base64_data: str) -> dict:
    try:
        with zipfile.ZipFile(BytesIO(base64.b64decode(base64_data))) as archive:
            name = next(
                name for name in archive.namelist() if name.endswith("boot.json")
            )
            info = json.loads(archive.read(name))
            if not isinstance(info, dict):
                raise ValueError("boot.json 必须是对象")
            return info
    except (
        ValueError,
        OSError,
        RuntimeError,
        StopIteration,
        zipfile.BadZipFile,
    ) as exc:
        return {"name": "Unknown", "version": "Unknown", "error": str(exc)}


def extract_mod_list(html_content: str) -> list[str]:
    match = MOD_LIST_PATTERN.search(html_content)
    if match is None:
        raise ValueError("HTML 中未找到 modDataValueZipList")
    mods = json.loads(match.group(1))
    if not isinstance(mods, list) or not all(isinstance(mod, str) for mod in mods):
        raise ValueError("modDataValueZipList 必须是字符串数组")
    return mods


def _write_mod_list(path: Path, content: str, mods: list[str]):
    # 使用函数替换，避免 JSON 内容被当作正则替换转义。
    content = MOD_LIST_PATTERN.sub(
        lambda match: f"window.modDataValueZipList = {json.dumps(mods)};", content
    )
    path.write_text(content, encoding="utf-8")


def _validate_indices(indices: list[int], count: int):
    if any(index < 0 or index >= count for index in indices):
        raise ValueError(f"Mod 索引越界，有效范围为 0 至 {count - 1}")


def add_mods_to_html(
    html_mod_path: str | Path, mod_paths: list[str | Path], position: str = "end"
):
    if position not in {"start", "end"}:
        raise ValueError("position 必须为 start 或 end")
    path = Path(html_mod_path)
    content = path.read_text(encoding="utf-8")
    mods = extract_mod_list(content)
    new_mods = [load_file_as_base64(mod_path) for mod_path in mod_paths]
    mods = new_mods + mods if position == "start" else mods + new_mods
    _write_mod_list(path, content, mods)
    logger.info("已添加 %s 个 Mod: %s", len(new_mods), path)


def reorder_mods(html_mod_path: str | Path, new_order: list[int]):
    path = Path(html_mod_path)
    content = path.read_text(encoding="utf-8")
    mods = extract_mod_list(content)
    _validate_indices(new_order, len(mods))
    _write_mod_list(path, content, [mods[index] for index in new_order])
    logger.info("已调整 Mod 顺序: %s", path)


def remove_mods(html_mod_path: str | Path, indices: list[int]):
    path = Path(html_mod_path)
    content = path.read_text(encoding="utf-8")
    mods = extract_mod_list(content)
    _validate_indices(indices, len(mods))
    _write_mod_list(
        path, content, [mod for index, mod in enumerate(mods) if index not in indices]
    )
    logger.info("已移除 Mod: %s", path)


def replace_mod_by_id(html_mod_path: str | Path, mod_id: int, mod_path: str | Path):
    path = Path(html_mod_path)
    content = path.read_text(encoding="utf-8")
    mods = extract_mod_list(content)
    _validate_indices([mod_id], len(mods))
    mods[mod_id] = load_file_as_base64(mod_path)
    _write_mod_list(path, content, mods)
    logger.info("已替换 Mod %s: %s", mod_id, path)


def list_mods(html_mod_path: str | Path):
    mods = extract_mod_list(Path(html_mod_path).read_text(encoding="utf-8"))
    print(f"Total mods: {len(mods)}")
    for index, mod in enumerate(mods):
        info = extract_boot_json_from_base64_zip(mod)
        print(
            f"[{index}] {info.get('name', 'Unknown')} v{info.get('version', 'Unknown')}"
        )
        print(f"    Size: {len(mod) / 1024:.2f} KB (Base64)")
        for key in ("author", "description", "error"):
            if info.get(key):
                print(f"    {key}: {info[key]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("add", "replace", "reorder", "remove", "list"):
        command = commands.add_parser(name)
        command.add_argument("html", type=Path, help="包含 ModLoader 的 HTML 文件")
        if name == "add":
            command.add_argument("mods", nargs="+", type=Path)
            position = command.add_mutually_exclusive_group()
            position.add_argument(
                "--start", action="store_const", const="start", dest="position"
            )
            position.add_argument(
                "--end", action="store_const", const="end", dest="position"
            )
            command.set_defaults(position="end")
        elif name == "replace":
            command.add_argument("index", type=int)
            command.add_argument("mod", type=Path)
        elif name in {"remove", "reorder"}:
            command.add_argument("indices", nargs="+", type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.command == "add":
            add_mods_to_html(args.html, args.mods, args.position)
        elif args.command == "replace":
            replace_mod_by_id(args.html, args.index, args.mod)
        elif args.command == "reorder":
            reorder_mods(args.html, args.indices)
        elif args.command == "remove":
            remove_mods(args.html, args.indices)
        else:
            list_mods(args.html)
    except (OSError, ValueError) as exc:
        logger.error("编辑失败: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
