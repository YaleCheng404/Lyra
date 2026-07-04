+++
title = '疑难解答'
slug = 'troubleshoot'
+++

# 疑难解答

## APK 打开后是英文或没有 ModLoader

先更新系统 WebView。仍无法使用时，尝试 polyfill 兼容版，或使用现代浏览器打开 ZIP/HTML 版本。

## ModLoader 加载 zip 提示 boot.json 无效

本仓库发布的是完整游戏本体加 Mod 的整合包，不是单独 Mod。不要把发布的 zip 当作 ModLoader 旁加载包使用。

## 中英文混杂

请卸载旁加载的汉化 Mod。整合包已内置对应游戏版本的汉化内容。

## 美化没有生效

检查是否旁加载了 `GameOriginalImagePack-*.mod.zip`。图片包 Mod 的优先级可能覆盖整合包内置图片资源。
