# 构建与维护

## 环境

CI 使用 Python 3.15.1、Temurin Java 25 LTS 和 Hugo 0.168.0。Java 用于 APK 解包、重建与签名；Hugo 仅用于生成下载站。完整构建建议使用 Linux 或 WSL，避免 Windows 文件名大小写冲突。

```sh
python -m venv .venv
# Linux / WSL
. .venv/bin/activate
# Windows PowerShell 使用 .venv/Scripts/Activate.ps1
python -m pip install -r requirements.txt
python main.py --help
java -version
```

APK 构建需要仓库根目录中的 `dol.jks`，alias 为 `dol`，当前签名工具使用密码 `dolchs`。CI 从 `SIGNING_KEY` secret 还原密钥，未配置时生成临时密钥。固定密钥用于保持 APK 更新签名一致；密钥文件不应提交到 Git。

## 构建

在仓库根目录执行以下四阶段流程。`--tag` 指定整合包版本，省略时准备阶段使用最新上游 Release，构建产物版本字段为 `unknown`。

```sh
python main.py prepare --tag v0.5.12.13-1.0.1a-1023
python main.py warmup
python main.py build --tag v0.5.12.13-1.0.1a-1023 --jobs 4
python main.py page --tag v0.5.12.13-1.0.1a-1023 --github-owner OWNER --github-repo REPO --versions-file base/versions.json --output output/downloads.md
```

`python -m lyra` 与 `python main.py` 使用相同命令和参数。`prepare` 下载游戏、汉化、基础 Mod 和已固定摘要的 APK 工具，生成 ZIP 基包及 APK 解包目录；`warmup` 下载并合并美化资源与模型；`build` 从预热资源构建各组合；`page` 生成 Hugo 可读取的 Markdown 下载页。

```sh
python main.py build zip --tag v0.5.12.13-1.0.1a-1023 --jobs 4
python main.py build apk --tag v0.5.12.13-1.0.1a-1023 --jobs 4
python main.py list
python main.py matrix
python main.py matrix --output-format shell
python main.py check --github-owner OWNER --github-repo REPO
```

`build` 默认构建 ZIP 和 APK，包含配置启用的 polyfill 组合。当前配置共 8 个构建代码，对应 16 个 ZIP/APK 目标。修改组合应编辑配置文件。

`prepare`、`warmup` 和 `build` 支持 `--workspace PATH`，默认当前目录。输出位于该目录下的 `output/`，基包和版本记录位于 `base/`，中间文件位于 `workspace/`。`page` 的输入和输出路径通过参数独立指定。APK 签名密钥始终从运行目录的 `dol.jks` 读取。

`page` 支持 `--version` 或 `--tag`；仓库信息优先采用命令参数，其次采用 `GITHUB_REPOSITORY` 和配置。`check` 使用相同的仓库选择方式，另支持 `--source-repo OWNER/REPO` 与 `--github-output PATH`。

## 配置与输出

| 文件 | 内容 |
| --- | --- |
| `config/build.toml` | 上游地址、工具 URL 与 SHA-256、目录、APK 替换规则、图片包及基础 Mod |
| `config/features.toml` | 功能位、显示名称、依赖与冲突关系 |
| `config/combinations.toml` | 推荐组合、白名单、黑名单与 polyfill 组合 |

产物格式为 `DoL-{游戏版本}-Lyra-{汉化版本}[-polyfill][-组合后缀]-{日期}.{zip,apk}`。整合包 tag 格式为 `v{游戏版本}-{汉化版本}-{四位日期}`，例如 `v0.5.12.13-1.0.1a-1023`。

图片包按 `build.toml` 中的 URL 顺序合并，并应用 `case_fixes` 与 `files_to_remove`。构建时美化按 BESC、Hikari、UCB 顺序覆盖；基础 Mod 按配置顺序注入。`base/versions.json` 记录已解析的资源版本，下载页和包内 Lyra 信息 Mod 使用该记录。并行任务按包类型、组合和兼容模式隔离工作目录。

## 手工编辑 Mod

工具直接修改指定 HTML，编辑前请自行保留原文件。

```sh
python scripts/modmagic.py list game.html
python scripts/modmagic.py add game.html first.mod.zip second.mod.zip --end
python scripts/modmagic.py add game.html first.mod.zip --start
python scripts/modmagic.py replace game.html 0 replacement.mod.zip
python scripts/modmagic.py reorder game.html 2 0 1
python scripts/modmagic.py remove game.html 0 2
```

索引从 0 开始。`reorder` 按提供的索引生成列表，可只选择部分 Mod；`remove` 删除所选索引。缺失文件、无效索引、缺少 Mod 数组或 JSON 损坏时返回非零状态，并在校验失败时保留原文件内容。主构建流程使用相同的 Mod 数组读写实现。

## 依赖与检查

运行环境以 `.python-version` 为准。`requirements.in` 声明直接依赖，`requirements.txt` 固定完整依赖；使用 uv 更新后，在干净环境中安装并检查。

```sh
uv pip compile requirements.in --universal --python-version 3.15.1 --upgrade --output-file requirements.txt
python -m pip install -r requirements.txt
python -m pip check
python -m unittest discover -v
python -m compileall -q main.py lyra scripts
```

GitHub Actions 固定完整提交 SHA，Dependabot 每周检查 Python 和 Action 更新。Apktool 或签名工具升级时，需要同时更新 `config/build.toml` 中的官方下载 URL 和 SHA-256，并实际检查 APK 解包、重建及签名。下载站的 Hugo 版本在 Build workflow 中指定。

```sh
hugo --source hub --destination public --baseURL https://example.github.io/Lyra/
```

## 排错

- 命令后加 `-v` 查看主构建工具的详细日志。
- 基包或美化资源缺失时，依次运行 `prepare`、`warmup`，再运行 `build`。
- 工具摘要校验失败时，核对官方资源及配置中的摘要；不要绕过校验。
- APK 重建失败时检查 Java、Apktool 输出和 AndroidManifest 替换规则；签名失败时检查 `dol.jks` 与 alias。签名工具无法定位 zipalign 时，检查 PATH 目录是否可列举，并把可用的 zipalign 目录放到 PATH 前部；手工调用也可使用上游的 `--zipAlignPath` 参数。
- 下载失败时检查 GitHub/GitGud 连接与 API 限额。基础 Mod 每次准备时查询最新正式 Release，同一仓库共用一次查询结果；缓存通过附件 SHA-256 或完整来源身份校验，同名附件被替换后重新下载。
- 本地虚拟环境解释器路径失效时，重新创建环境并安装锁文件。

许可文本见 [LICENSE](LICENSE) 与 [LICENSE2](LICENSE2)，各上游资源遵循其来源许可。

## 基础 Mod 与发布校验

所有组合包含秋枫白桦框架、枯木逢春本体与音频、默示录：归途之书及极致动态 Dynamicest。按配置顺序原样内嵌 `.mod.zip` 和 `.modpack`；asset_pattern 使用 glob 且必须唯一匹配，required = true 的资源获取失败会终止准备。

完成构建后运行 `python main.py verify --tag v0.5.12.13-1.0.1a-1023`，校验完整产物集合、压缩包 CRC、HTML 内必需 Mod 的字节和顺序，并生成 output/release-notes.md。CI 在上传附件和发布前执行相同检查。Trigger 每天香港时间 04:17 检查新汉化；手动发布使用 Build 的 release_tag 输入。
