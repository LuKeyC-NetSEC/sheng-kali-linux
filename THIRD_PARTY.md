# 第三方来源与许可

保留上游 [sheng-pmos-builds](https://github.com/alghiffaryfa19/sheng-pmos-builds) Git 历史和根 [GPL-3.0 许可证](LICENSE)。不同组件按各自文件头/上游许可证处理；以下列出源码和资产来源，不把单一许可证套用所有外部产物。本项目的适配修改记录于 Git 提交与 patch。

| 组件 | 固定来源/入口 | 许可与分发说明 |
| --- | --- | --- |
| Linux sheng | [ianchb/sm8550-mainline](https://github.com/ianchb/sm8550-mainline)，commit `87ac0f2347eb433933841e6854950dd90e96e6b2` | 驱动补丁遵循 GPL-2.0-only；不随仓库提交内核二进制 |
| 固件/触屏/硬件库 | [sources.json](configs/sources.json) 内固定提交、下载和哈希 | 各上游许可；构建时获取，不把缓存打包入源仓库 |
| Debian sheng 音频适配 | [alghiffaryfa19/debian-sheng](https://github.com/alghiffaryfa19/debian-sheng) | 固定来源见 sources.json，保留上游声明 |
| PIN 认证 | [ianchb/sheng_devauth](https://github.com/ianchb/sheng_devauth)，`bac03b5bcfefa1467ebad490edd910a6cef8a207` | patch与上游依赖分开；静态依赖含各自 libs/LICENSE，重新分发前核查 |
| Plasma NM | [KDE/plasma-nm](https://github.com/KDE/plasma-nm)，`b6c03fe24b30d2a963a41dd83784e36086d7257e` | applet与库按原文件 SPDX；打包保留 GPL/LGPL 文本 |
| 控制中心 | [Kontrol Center](https://github.com/ItsNotMeBro87/plasma6-kontrol-center)，`137ba6c3b441c69dd3e59052ac9e8124367f40b4` | GPL-3.0-or-later；构建器保留 LICENSE、图标说明和新增 NOTICE |
| 自定义任务效果/手势 | [device/recents/LICENSE](device/recents/LICENSE) | MIT，保留文件头与许可证 |
| 原生 Alt+Tab 布局 | 系统安装的 KWin thumbnail_grid | 复制时保留作者/许可，仅改导航边界 |
| Panel Colorizer | [luisbocanegra/plasma-panel-colorizer](https://github.com/luisbocanegra/plasma-panel-colorizer)，`a8f8b1cee7bbc670cf2a5f5d194c24c314073b82` | 外部安装；插件需匹配 Qt/Plasma |
| Colloid | [vinceliuice/Colloid-icon-theme](https://github.com/vinceliuice/Colloid-icon-theme)，`ceac6608ecd0e40025cbc2ebbd32bf0e0f4ebc6a` | 外部主题，保留其许可 |
| Redmi Clock / Lagtrain | KDE Store 2175475 / 2124802 | 仓库仅提供天气/布局修改，不包含原包 |
| 水杉输入法 | [metasequoiaime/msime](https://github.com/metasequoiaime/msime/releases/tag/linux-v0.16.1) | 官方 ARM64 包外部安装；不分发运行数据/账户/模型缓存 |
| Fcitx5 OSK | [fortime/fcitx5-osk](https://github.com/fortime/fcitx5-osk)，tag `0.2.1` → commit `76a33b65b1c72519788c09cfb9f94c1df0f61949` | 上游源码与许可证，集成打包保持原始版权 |
| Burp Suite | [PortSwigger 官方下载](https://portswigger.net/burp/releases) | 商业软件，仅提供性能参数；不分发安装包/许可证/激活工具 |
| Miku 壁纸 | [桌面来源](device/theme/wallpaper.json)、[锁屏来源](device/theme/lockscreen-wallpaper.json) | 仅来源、作者与哈希；图片不随仓库分发，下载/使用自行核查原作者条件 |

根目录三张 JPEG 和 `parted` 为继承自上游的历史文件，不是本次桌面资产或新部署必要工具。新流程使用发行版工具，不执行旧 `parted`。历史 postmarketOS 文档/工作流仅供参考。

本仓库不授予小米、Kali、澎湃、Miku 等名称/角色的商标或图像权利。发行可安装二进制前应随包附对应许可证与可获取源码，并检查第三方依赖的再分发条件。
