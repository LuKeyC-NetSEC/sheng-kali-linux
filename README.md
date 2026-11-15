# Sheng Kali Linux · 小米平板 6S Pro

[![Source checks](https://github.com/LuKeyC-NetSEC/sheng-kali-linux/actions/workflows/check.yml/badge.svg)](https://github.com/LuKeyC-NetSEC/sheng-kali-linux/actions/workflows/check.yml)

**在 Xiaomi Pad 6S Pro 12.4（`sheng` / `24018RPACC`）运行原生 Kali ARM64 + KDE Plasma Wayland。** 本仓库提供镜像构建、刷写校验、硬件修复和面向平板的桌面交互源码，便于开发者与 AI 协作部署。

基于 [alghiffaryfa19/sheng-pmos-builds](https://github.com/alghiffaryfa19/sheng-pmos-builds) 扩展，保留上游提交历史和 GPL 许可证。这是社区适配，非小米或 Kali 官方支持项目。

> 安装会覆盖 `userdata`，删除全部 Android 用户数据。仅适用于已解锁 Bootloader 的 **sheng**，不要用于其他小米平板。当前发布为源码与复现说明，未发布包含全部后续改动的完整预制镜像。

## 从哪里开始

| 目的 | 文档 |
| --- | --- |
| 让 AI 帮你部署 | [AI 部署指南与可复制提示词](docs/AI_DEPLOY.md)、[AGENTS.md](AGENTS.md) |
| 构建、刷写、分层安装与恢复 | [部署手册](docs/DEPLOYMENT.md) |
| 桌面布局、控制中心、手势、电源行为 | [桌面与交互](docs/DESKTOP_AND_INTERACTIONS.md) |
| 原桌面上滑抽屉、Linexin Dock 与防框选 | [抽屉与 Dock 部署](docs/DESKTOP_DRAWER.md) |
| 两段上滑 Dock、锁屏手势、缺字与新图标 | [触控和字体增量](docs/TOUCH_LOCKSCREEN_FONTS.md) |
| 硬件与版本兼容性 | [适配矩阵](docs/HARDWARE.md) |
| 已验证功能、未完成项、验收方法 | [验证状态](docs/VALIDATION.md) |
| 第三方来源与许可 | [THIRD_PARTY.md](THIRD_PARTY.md) |
| 修改与提交 | [CONTRIBUTING.md](CONTRIBUTING.md) |

English entry: native Kali ARM64 / KDE for Xiaomi Pad 6S Pro (`sheng`). Start with the linked deployment guide; machine identifiers and commands are included. Flashing erases Android userdata. This is a source release, not a fully integrated ready-to-flash release image.

## 当前功能

- 原生 ARM64 Kali rolling、Plasma Wayland；触屏、USB RNDIS/SSH、CDC ACM 串口。
- Adreno 740：Mesa freedreno OpenGL 与 Turnip Vulkan 共存；[GPU 监控](device/gpu-monitor/README.md) 和[实机对比](docs/gpu-efficiency-measurement.md)。
- PIN 键盘/触摸板认证和唤醒修复；扬声器、音量键；Wi-Fi 上网与并发热点。
- 6 GiB Zstd ZRAM + 8 GiB swapfile；不额外划分 swap 分区。
- 上方状态栏、底部自动隐藏 Dock、下滑控制中心、原生 Alt+Tab 三指选窗、单虚拟桌面。
- 原 Plasma 桌面全区域触屏上滑打开 Linexin 全屏抽屉；防触屏框选、长按编辑、左右分页。抽屉与桌面显示同一个 Linexin Dock，开关时保持静止。
- 摄像头/麦克风/定位的统一隐私开关，含设备访问、门户请求与既有采集进程处理；范围和限制见[隐私说明](device/privacy/README.md)。
- 电源短按锁屏；插电闲置 60 分钟锁屏息屏、后台继续；离电闲置 30 分钟锁屏息屏并挂起。
- 水杉 + Fcitx5 输入集成：PIN 中文、接入时禁止软键盘、无键盘时连续弹出，以及新界面的触屏中文、悬浮拖动和停靠切换均已用户确认。新输入法的锁屏/挂起恢复仍待独立验收；基础镜像默认使用 Plasma Keyboard。

这些是当前实机的累计适配状态。**基础构建脚本未自动安装全部增量组件。** PIN 模块编译、热点面板编译、主题第三方资产与个别用户配置仍需按部署手册处理，不能仅刷入基础镜像就宣称完整复现。

## 快速构建基础镜像

在 Linux root 环境构建，需要 ARM64 binfmt/QEMU 及至少约 30 GiB 可用磁盘；完整构建建议预留更多空间。Windows 使用 Linux 虚拟机。

```bash
git clone https://github.com/LuKeyC-NetSEC/sheng-kali-linux.git
cd sheng-kali-linux
sudo apt-get update
sudo apt-get install -y debootstrap qemu-user-static binfmt-support \
  android-sdk-libsparse-utils e2fsprogs curl ca-certificates gnupg python3
sudo update-binfmts --enable qemu-aarch64
sudo bash scripts/build-kali.sh
python3 scripts/validate-images.py out
```

也可手动运行 GitHub Actions 的 **Xiaomi Pad 6S Pro Kali ARM64 KDE**。内核、固件及下载哈希在 [configs/sources.json](configs/sources.json)。Kali rolling 的软件包会更新，固定硬件来源不等于完整可重复构建；每次保留 `packages.tsv` 和 manifest。

基础产物：`out/boot-kali-sheng.img`、`out/rootfs-kali-arm64-kde-sheng.img`、`out/manifest.json`、校验与软件包列表。`out/` 和 `.work/` 不入库；其他人的本地文件无需存在，也不应作为下载来源。

默认账户 `kali` / `kali`，开启自动登录与 USB SSH，root 密码登录锁定。首次启动请修改密码；可通过构建环境变量或 Actions secret `KALI_PASSWORD` 设置自定义密码，不要将真实密码写入仓库。

## 刷入与回退

确认机型、备份、解锁状态及清数据授权后，在 Windows 执行：

```powershell
adb reboot bootloader
python scripts/validate-images.py out
.\scripts\flash-kali.ps1 -ImageDirectory .\out -EraseUserdata
```

Linux 使用 `OUT_DIR=out bash scripts/flash-kali.sh --erase-userdata`。脚本将 rootfs 写入 `userdata`，内核写入 `boot_b`，清除 `dtbo_b`，切至 B 槽并重启。脚本通过不等于硬件启动验收；分区影响、串口/SSH检查和恢复方法见[部署手册](docs/DEPLOYMENT.md)。保留 A 槽 boot/dtbo 不会保留 Android 用户数据。

## 源码导航

| 路径 | 用途 |
| --- | --- |
| `scripts/build-kali.sh`、`fetch-assets.py`、`validate-images.py` | 基础镜像与校验 |
| `device/keyboard-driver/`、`keyboard-auth/` | PIN 驱动及认证补丁 |
| `scripts/sheng-hotspot.py`、`device/hotspot-panel/` | 并发 AP 与原生网络面板 |
| `device/control-center/` | 澎湃风格控制中心 QML/SVG、固定上游补丁 |
| `device/recents/`、`desktop-policy/` | 三指原生切窗、任务卡片、Dock、桌面下滑 |
| `device/linexin-dock/`、`desktop-touch-guard/` | Linexin Dock/抽屉补丁、KWin 防框选与全屏 Dock 叠层 |
| `device/privacy/` | 进程/设备访问隐私后端 |
| `device/theme/`、`input-method/` | 桌面配置、天气修复、实验输入法 |
| `device/gpu-bench/`、`docs/` | GPU 测试代码、部署与验证说明 |

仓库保留的 `gnome_shell_mobile.jpg`、`hyperos.jpg`、`neofetch.jpg` 是上游历史资料，**不是当前 Kali 桌面截图**。当前布局和手势见交互文档中的结构图。Miku 壁纸仅记录来源，不重新分发图片；Burp 只提供公开性能配置，不提供软件本体或许可证。

本地检查：`python3 scripts/check-project.py`。旧 postmarketOS 工作流仅手动触发，历史说明见 [postmarketos-original.md](docs/postmarketos-original.md)。
