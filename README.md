# DoL-Lyra

基于[汉化仓库][github-chs]的自动化整合包构建工具，提供不同 Mod 与美化组合的 ZIP、Android APK 和 polyfill 兼容版。

本仓库是第三方整合发布渠道。升级前请导出并备份存档。

## 下载与使用

在本仓库 [Releases](https://github.com/YaleCheng404/Lyra/releases) 下载 ZIP 或 APK；启用 GitHub Pages 后，也可在下载站查看版本说明和下载列表。

- ZIP 解压后用现代浏览器打开游戏 HTML。
- Android 安装 APK。应用名为 `DoL Lyra`，可与原版和汉化版共存；存档通过导出、导入转移。
- polyfill 兼容版面向部分旧设备或浏览器。APK 无法加载 ModLoader 时，先更新系统 WebView，再尝试兼容版。
- 发布文件包含完整游戏和 Mod，请勿将整合包 ZIP 作为 ModLoader 旁加载包导入。
- 汉化、作弊和 CSD 已内置，可在 ModLoader 中启用或禁用。旁加载其他汉化或图片包可能覆盖内置内容。

文件名格式为 `DoL-{游戏版本}-Lyra-{汉化版本}[-polyfill][-组合后缀]-{日期}.{zip,apk}`。各组合由配置文件定义，下载页显示对应资源版本和来源。

在线版由 **Deploy Online** workflow 部署到本仓库 `online` 分支，使用 BESC、作弊和 CSD 组合，包含普通与兼容模式。

## 自动构建

- **Trigger** 定时检查上游汉化 Release，发现新版本后触发 **Build**。
- **Build** 下载资源、构建 ZIP/APK；指定发布 tag 时创建 Release 并部署下载站。
- 首次使用下载站时，在仓库 **Settings → Pages** 中选择 **GitHub Actions**。
- `SIGNING_KEY` secret 可配置 Base64 编码的 APK keystore；未配置时 CI 生成临时密钥。需要覆盖安装时应使用固定签名密钥。
- 上游仓库、资源和组合规则在 `config/` 中配置。

本地环境、构建命令与 Mod 编辑工具用法见 [BUILD.md](BUILD.md)。

## 问题反馈

游戏问题请先使用[上游汉化版本][github-chs]复现。上游同样出现的问题向汉化仓库反馈；仅本整合包出现的问题提交到本仓库 Issues，并附版本、组合和错误信息。

美化错位、黑边或缺失通常需要对应资源作者适配。美化未生效时，检查是否旁加载了优先级更高的 `GameOriginalImagePack-*.mod.zip`；中英文混杂时检查是否重复加载汉化 Mod。

许可文本见 [LICENSE](LICENSE) 与 [LICENSE2](LICENSE2)。游戏、汉化和各 Mod 的许可及使用条件以相应来源为准。

## Credits

- <img decoding="async" src="https://gitgud.io/uploads/-/system/user/avatar/9096/avatar.png" width="24"> $\color{purple} {Vrelnir}$
  - [Vrelnir 的博客][blog]
  - [英文游戏维基][wiki-en]
  - [中文游戏维基][wiki-cn]
  - [官方 Discord][discord]
  - [游戏源码仓库][gitgud]
- [原版汉化仓库][github-chs]
  - [为汉化仓库做出过贡献的诸位][github-chs-credits]
- [DoL-Lyra][github-lyra]
- Mod
  - [Lyra-CombatStatusDisplay][lyra-csd]
  - [Lyra-Cheat][lyra-cheat]
- 美化
  - [Degrees of Lewdity Plus][dolp]
  - [Degrees of Lewdity Graphics Mod][beeesss]
    - BEEESSS
  - [BEEESSS Community Sprite Compilation][beeesss-ext]
    - BEEESSS, ethanatortx, MatchaCrepeCakes, LedhaKuromi, Tommohas, Jessplayin690, SkyFall669/SomethingIsHuntingYou, AvinsXD, okbd321, cloversnipe, Elegant_Dress_5771, doseonseng, G259M, VanityDecay, Hikari, luoyin mengling, Tieba user_5CU79bt, Xiaochien, cheese shredded cake, artiste (the gayest man alive), Suqi eggplant stew, Paril, La Maritza, AD calcium, Isari, 森谷華子, aqua, superhydroxide, 再3棘, 567600, ToumanLin, Isopod, ◌/あきやま, Poop, SydNekoKawaii, Bunnyberry<3, Mizzy, 長門有栖☆, 七玳, 墮天使
  - [BEEESSS Wax][beeesss-wax]
    - Paril, b333sss
  - [Susato Model][susato-model]
    - susato, miyako2428
  - [通用战斗美化 UCB][ucb-github]
    - 贴吧用户\_GaC5V7E
- 特写
  - [Hikari][hikari]
  - [Goose][goose]
  - [Paril Double Cheeseburger][sideview-dc]
    - Paril, b333sss, Zubonko, Blaine
  - [DOL BJ hair extend][sideview-bj-extend]
    - Zubonko
  - [韩站特写][sideview-kr]
    - G259M
  - [KR特写刘海补充][sideview-kr-extend]
    - 贴吧用户\_GaC5V7E

[blog]: https://vrelnir.blogspot.com
[wiki-en]: https://degreesoflewdity.miraheze.org/wiki
[wiki-cn]: https://degreesoflewditycn.miraheze.org/wiki
[gitgud]: https://gitgud.io/Vrelnir/degrees-of-lewdity/-/tree/master
[discord]: https://discord.gg/VznUtEh
[github-chs]: https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization
[github-chs-credits]: https://github.com/Eltirosto/Degrees-of-Lewdity-Chinese-Localization/blob/main/CREDITS.md
[github-chs-pages]: https://eltirosto.github.io/Degrees-of-Lewdity-Chinese-Localization/
[beeesss]: https://gitgud.io/BEEESSS/degrees-of-lewdity-graphics-mod
[beeesss-ext]: https://gitgud.io/Kaervek/kaervek-beeesss-community-sprite-compilation
[beeesss-wax]: https://gitgud.io/GTXMEGADUDE/beeesss-wax
[sideview-dc]: https://gitgud.io/GTXMEGADUDE/double-cheeseburger
[sideview-bj-extend]: https://github.com/zubonko/DOL_BJ_hair_extend
[sideview-kr]: https://arca.live/b/textgame/83875947
[sideview-kr-extend]: https://tieba.baidu.com/p/9055647926
[github-lyra]: https://github.com/DoL-Lyra
[lyra-csd]: https://github.com/DoL-Lyra/CombatStatusDisplay
[lyra-cheat]: https://github.com/DoL-Lyra/Cheat
[susato-model]: https://discord.com/channels/675158131688603721/1216104862870147303
[ucb-github]: https://github.com/site098/mysterious
[dolp]: https://gitgud.io/Frostberg/degrees-of-lewdity-plus
[hikari]: https://gitgud.io/HikariT/hikari-mods
[goose]: https://gitgud.io/goose/createshit
