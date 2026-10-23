"""在真实浏览器中验证发布 ZIP 的初始化和内容 Mod。"""

import argparse
import functools
import http.server
import json
import tempfile
import threading
import zipfile
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

REQUIRED_MODS = [
    "maplebirch",
    "deadwood-reblooms",
    "deadwood-reblooms-audio",
    "revelation-the-book-of-return",
    "Dynamicest",
]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument(
        "--channel", help="本地可指定 msedge；CI 使用 Playwright Chromium"
    )
    parser.add_argument("--output", type=Path, default=Path("output/browser-smoke"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lyra-browser-") as directory:
        root = Path(directory)
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(root))
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                options = {"headless": True}
                if args.channel:
                    options["channel"] = args.channel
                browser = playwright.chromium.launch(**options)
                try:
                    for index, package in enumerate(args.archives):
                        dest = root / str(index)
                        with zipfile.ZipFile(package) as archive:
                            archive.extractall(dest)
                        html = next(dest.glob("*.html"))
                        page = browser.new_page()
                        errors, missing_modlist, mod_errors = [], [], []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.on(
                            "response",
                            lambda response: (
                                missing_modlist.append(response.url)
                                if response.status == 404
                                and response.url.endswith("/modList.json")
                                else None
                            ),
                        )

                        def check_console(message):
                            if message.type != "error":
                                return
                            owners = [
                                arg.evaluate("v => v?.name || v?.[0]?.name || ''")
                                for arg in message.args
                            ]
                            if any(
                                name in message.text or name in owners
                                for name in REQUIRED_MODS
                            ):
                                mod_errors.append(message.text[:1000])

                        page.on("console", check_console)
                        url = f"http://127.0.0.1:{server.server_port}/{index}/{quote(html.name)}"
                        page.goto(url, wait_until="load", timeout=90000)
                        page.wait_for_function(
                            "document.querySelector('#passages .passage') !== null",
                            timeout=120000,
                        )
                        loaded = page.evaluate(
                            "window.modUtils.getModListNameNoAlias()"
                        )
                        missing = sorted(set(REQUIRED_MODS) - set(loaded))
                        content = page.evaluate("""['deadwood-reblooms','revelation-the-book-of-return'].map(name => {
                            const mod = modUtils.getMod(name);
                            return {name, passages: mod?.cache?.passageDataItems?.items?.length || 0};
                        })""")
                        unexpected = [
                            error
                            for error in errors
                            if not (missing_modlist and "Unexpected token '<'" in error)
                        ]
                        report = {
                            "package": package.name,
                            "loaded_mods": loaded,
                            "content": content,
                            "missing_mods": missing,
                            "page_errors": errors,
                            "mod_errors": mod_errors,
                        }
                        (args.output / (package.stem + ".json")).write_text(
                            json.dumps(report, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        page.screenshot(path=str(args.output / (package.stem + ".png")))
                        if (
                            missing
                            or unexpected
                            or mod_errors
                            or any(not mod["passages"] for mod in content)
                        ):
                            raise RuntimeError(
                                f"{package.name}: 浏览器运行检查失败: {report}"
                            )
                        print(
                            f"浏览器检查通过: {package.name}; 必需 Mod 全部加载，内容 passage 已注册",
                            flush=True,
                        )
                        page.close()
                finally:
                    browser.close()
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
