# 构建、部署与回退

仅针对 `sheng`。版本基线见 [HARDWARE.md](HARDWARE.md)，实际验收见 [VALIDATION.md](VALIDATION.md)。仓库无需连接作者设备、无需作者 `.work/`，也不包含预构建全量镜像或私有软件。

## 分层与依赖

```text
Linux 构建机 → build-kali.sh → boot / sparse rootfs / manifest
                                ↓ 首启并验收
Kali ARM64 / 匹配内核 → PIN 驱动+认证 / 热点 / 音频 / 电源
                                ↓ 同一 Plasma/Qt ABI
Plasma Wayland → KWin 效果+手势 / desktop-policy+隐私 / 控制中心
                                ↓ 用户会话配置
主题/面板/天气 → 可选 Burp 参数 / 实验水杉输入法
```

`build-kali.sh` 已安装基础 KDE、触屏、USB网络/串口、固件、GPU监控、swap、热点后端、基础软键盘和电源脚本。它**尚未自动集成**下面的 PIN 修复包、原生热点面板补丁、定制控制中心、KWin 效果、隐私/桌面策略和完整主题。不要把旧导出镜像当作当前实机全量备份。

## 基础镜像

1. 使用 Linux root、debootstrap、ARM64 binfmt/QEMU，依赖安装命令见根 README。若在 Windows，请使用 Linux 虚拟机；不要在 PowerShell 直接运行 chroot/mount。
2. `sudo bash scripts/build-kali.sh`。默认 `BUILD_DIR=.work/build`、`ASSET_DIR=.work/assets`、`OUT_DIR=out`、`IMAGE_SIZE=16G`，可通过环境变量覆盖。指定新的构建目录可避免覆盖；`RESUME=1` 只恢复已经确认的 Kali ARM64 构建。
3. `python3 scripts/validate-images.py out`。输出包括 boot、sparse rootfs、manifest、`packages.tsv`、`validation.txt`。固定硬件来源和 SHA 在 [sources.json](../configs/sources.json)；rolling 软件源本身不构成软件包快照。
4. 默认 kali/kali、自动登录、USB SSH。自定义密码通过环境变量传入，不写进脚本；首启修改密码。导出会清空 machine-id 和 SSH host keys，目标首启生成自己的身份。

GitHub Actions 的基础镜像和历史 postmarketOS 构建都只手动触发。普通推送只运行源码检查；Actions artifact 有保留期限，不是长期镜像发行承诺。

## 刷写与首启

先完成目标识别、独立数据备份、Bootloader 解锁和明确的 userdata 清空授权。Windows 主机需可用 adb/fastboot；Linux 脚本支持 `SERIAL`、`FASTBOOT`、`OUT_DIR` 环境变量。

```powershell
adb reboot bootloader
python scripts/validate-images.py out
.\scripts\flash-kali.ps1 -ImageDirectory .\out -EraseUserdata
```

```bash
# Linux 主机；仅在已同意清空目标设备后执行
OUT_DIR=out bash scripts/flash-kali.sh --erase-userdata
```

| 对象 | 操作 |
| --- | --- |
| `userdata` | 覆盖为 Linux ext4 根分区，Android 数据全部丢失 |
| `boot_b` | 写入 sheng 专用内核 |
| `dtbo_b` | 清除，为该主线内核使用 |
| 活跃槽位 | 切至 B，重启 |
| A 槽 boot/dtbo、recovery | 脚本不写入，但不能恢复已覆盖 userdata |

Windows 使用 256 MB 分块，部分写入可能较久。保留 `flash-record.json` 与日志，不在没有明确报错时中断写入。脚本检查设备、解锁状态、分区大小、manifest/哈希；不得跳过这些检查。

首启后检查 `uname -m` 为 aarch64、`dpkg --print-architecture` 为 arm64、`/etc/os-release` 为 Kali，确认 Plasma Wayland 与触屏。USB RNDIS 默认平板 `192.168.77.1`，主机 DHCP；SSH `ssh kali@192.168.77.1`。USB CDC ACM 串口可作备用诊断入口。`scripts/verify-device.py` 使用 Paramiko，首次应通过可信渠道核对主机指纹，报告存本地 `out/`。

## 增量组件部署

下列命令除注明外在 **ARM64 平板 Linux** 的仓库根目录执行；用户会话命令不要用 sudo。先备份 `~/.config/kwinrc`、`kglobalshortcutsrc`、`plasma-org.kde.plasma.desktop-appletsrc`、`plasmashellrc`、`kdeglobals`、`kcminputrc`、`kscreenlockerrc`。不要复制其他人的完整 HOME。

### 1. PIN 键盘与热点面板

PIN 先读 [驱动说明](../device/keyboard-driver/README.md)：

- 精确内核源码 `ianchb/sm8550-mainline@87ac0f2347eb433933841e6854950dd90e96e6b2`、运行内核配置和 Clang 21.1.8-13；在源码根应用驱动 patch，执行 `make LLVM=-21 olddefconfig prepare modules_prepare`，编译相应模块。
- 当前提供 `sudo python3 scripts/build-pin-driver.py` 自动下载验哈希、准备精确配置并在独立目录应用两个补丁，编译1.3.1模块；它检查83个既有导入、原内核导出和vermagic，不会加载或刷写。具体要求见驱动README。
- `CONFIG_MODVERSIONS=n` 仍需匹配导出符号/配置。没有完整的精确构建树与符号表时不能强行加载；本仓库目前没有一键重建该模块的完整工具链封装。
- 认证使用 `ianchb/sheng_devauth@bac03b5bcfefa1467ebad490edd910a6cef8a207`，应用 [service-fixes.patch](../device/keyboard-auth/service-fixes.patch)，遵循上游构建并链接其授权的依赖。
- `bash scripts/build-dock-fix-package.sh MODULE AUTH_BINARY "$PWD" out/packages` **仅打包已编译、已验 ABI 的产物**。安装后用 `modinfo`/服务状态及真实输入验收，不重绑整条 I²C/TEE 链路。二进制依赖许可需另行确认。
- 当前包为 `sheng-dock-fix_1.3-2_arm64.deb`。增量使用 `sudo python3 scripts/install-pin-driver.py PACKAGE --reload`，只卸载/重载PIN并检查电池提供者实例保留；不加 `--reload` 等下次正常启动。不要用 `modprobe -r` 连带卸载 `qcom_battmgr`，否则电池重建可能误报0%。

热点后端已在基础镜像安装，SSID/随机新密码位于 `/etc/sheng-hotspot/`，不会从本仓库获取作者密码。`sudo systemctl start sheng-hotspot.service` 开启，`stop` 关闭；本地查看 `/etc/sheng-hotspot/access.txt`，不要提交该文件。热点使用 `sheng-ap` 虚拟 AP、hostapd、dnsmasq 和专用 nftables 表，保留原 wlan 上网连接。默认关闭，必须用另一设备连接并确认互联网访问。

原生状态栏按钮需 [hotspot-panel](../device/hotspot-panel/README.md)。从固定 `KDE/plasma-nm@b6c03fe24b30d2a963a41dd83784e36086d7257e` 获取源码并应用 `applet.patch`；将该源码的 `applet/` 与本仓库该目录的 CMake/controller 文件组成独立源码根，安装相同版本的 Plasma/NetworkManagerQt 开发依赖，用 CMake/Ninja 编译 applet，保留系统网络管理库。打包：

```bash
bash scripts/build-hotspot-panel-package.sh /path/to/org.kde.plasma.networkmanagement.so "$PWD" out/packages
```

这个打包器不编译 applet。绑定 `plasma-nm=4:6.7.4-2+b1`，新版本需要重新移植并构建，不能禁用依赖检查直接覆盖。新会话再加载 applet；不要为发布文档强制退出当前桌面。

### 2. 任务效果、原生三指切窗

```bash
# 在匹配ARM64环境构建原生KWin，保留当前会话。
python3 scripts/prepare-kwin-native.py
sudo apt-get build-dep --no-install-recommends ./out/kwin-native-source
bash scripts/build-kwin-native.sh
bash scripts/test-kwin-native.sh
python3 scripts/build-task-cards.py --install
python3 device/recents/install-native-tabbox.py
```

任务效果构建器打印带源码散列的新插件 ID 和启用命令，按其输出以当前用户启用；升级先停用旧 ID，不能同时加载多个副本。停用原生 Overview，避免手势/Meta+W 冲突；系统设置中保留一个虚拟桌面，将其他桌面的窗口先归并后删除桌面。旧三指桥接器已删除；手势直接进入合成器现有TabBox。独立三指上下没有动作；进入 Alt+Tab 后才允许四向选择。

### 3. 桌面策略与隐私

```bash
python3 scripts/prepare-plasma-native.py
sudo apt-get build-dep --no-install-recommends ./out/plasma-native-source
bash scripts/build-plasma-native.sh
# 使用刚构建的KWin SDK，不替换当前运行中的合成器。
mkdir -p out/kwin-sdk out/bin out/packages
dpkg-deb -x out/kwin-dev_6.7.4-2+sheng1_arm64.deb out/kwin-sdk
dpkg-deb -x out/libkwin6_6.7.4-2+sheng1_arm64.deb out/kwin-sdk
CMAKE_PREFIX_PATH="$PWD/out/kwin-sdk/usr" bash scripts/build-desktop-touch-guard.sh
gcc -std=gnu11 -O2 -Wall -Wextra -Werror device/privacy/device-guard.c -o out/bin/sheng-privacy-bpf
sudo out/bin/sheng-privacy-bpf probe
python3 device/desktop-policy/build-device-package.py out/bin/sheng-privacy-bpf out/packages/sheng-tablet-controls_1.0-8+native1_arm64.deb --touch-guard-build out/build-desktop-touch-guard
# 新包依赖原生KWin/Plasma；先准备全部匹配包及回退，再安排正常重新登录。
```

包安装隐私过滤器、一次性布局工具及指向原生plasmashell的激活入口。Dock显隐直接运行在 [Plasma Shell C++](../device/plasma-integration/README.md)，桌面上滑由原生guard负责；旧Python服务、QML手势部件及任务效果中的Dock发布器已移除。Dock按 `ShengThemeRole=dock` 识别，不依赖作者面板ID。

使用当前 Linexin Dock/抽屉时，先完成下面的主题面板，再按[抽屉专用说明](DESKTOP_DRAWER.md)构建启动器、运行迁移助手和编译原生桌面触控插件；助手删除旧手势部件实例、备份和迁移固定项。原生插件必须与当前 KWin/Qt ABI 匹配，它同时负责防框选和真正全屏抽屉上的 Dock 叠层；仅安装 QML 不够。

隐私开关默认为允许访问；先读 [拦截范围](../device/privacy/README.md)。root 运行 `/usr/libexec/sheng-privacyctl off` 可恢复；本地活跃用户通过 `sheng-privacy on/off` 请求有限权限。冻结既有采集进程可能暂停整个相关应用，验收使用测试进程。

触屏防误入编辑使用[桌面原生策略](../device/desktop-edit-policy/README.md)，同时覆盖布局触摸与部件的合成鼠标长按入口。编译并打包 `sheng-desktop-edit-policy 1.0-1` 后安装，可在当前Plasma中加载，无须为此退出用户会话。

### 4. 控制中心

构建主机或平板需 Python 3 和 Git，无需本地秘密缓存：

```bash
python3 scripts/build-control-center.py
# 以下以平板桌面用户执行
kpackagetool6 --type Plasma/Applet --install out/packages/sheng-control-center.plasmoid
# 已安装时使用 --upgrade
```

构建器按固定提交下载上游，校验 archive 和 patch 哈希，应用 patch、复制 QML/SVG，保留许可证，生成本地 manifest。添加 `org.kontrol.center` 到**顶部状态栏**，以便找到同一窗口中的时钟/托盘；即使点击入口隐藏，部件仍须存在。加载后验证右侧下滑、普通区域上滑与滑条/列表例外。隐私按钮依赖上一包，热点依赖基础服务。

### 5. 主题、布局与天气

[theme/README.md](../device/theme/README.md) 记录组件版本、壁纸来源及天气补丁。安装相应 Panel Colorizer（含匹配 Qt/Plasma 的 C++ 插件）、Colloid-Light、Redmi Clock 后，在用户会话通过 Plasma 脚本接口执行 `device/theme/layout.js` 作为布局种子，或手动建立等价面板。

当前配置、插件角色、显示模式和有效全局样式见[桌面配置同步](DESKTOP_PROFILE.md)及其 JSON 快照；按本机部件重新映射，不复制作者的实例 ID。导出脚本只读，校验器无需连接设备。

该脚本会迁移现有任务面板并创建顶栏，**不是可重复执行的配置管理器**；先备份并读取脚本，已存在 Sheng 顶栏时它会停止。默认壁纸路径需先放置你有权使用的图片，或改成自己的路径。不要从作者设备导出整份配置。

在系统设置选择 BreezeLight、Breeze 样式、Colloid-Light、Breeze_Light 24px；关闭壁纸强调色，设置内屏 200% 缩放。Panel Colorizer：顶栏 ChromeOS 预设关闭背景，普通部件和托盘前景白色；Dock 使用 Translucent；按新 widget ID 将电池图标设为白色符号遮罩。配置未全部自动化，须人工/AI检查。`WeatherData.qml` 替换 Redmi Clock 对应组件，再在其根目录应用 `weather-ui.patch`。

当前两段底边唤出、独立电池图形、圆角 Burp 图标、锁屏上滑和缺字修复，按[触控/字体增量说明](TOUCH_LOCKSCREEN_FONTS.md)部署。基础构建已补 Noto/Liberation 正文字体与 MDI ASCII 过滤配置，但完整 rootfs 未在本轮重新构建；锁屏 patch 和桌面部件仍为单独增量。

### 6. 可选应用与实验输入法

Burp 官方安装及 6 GiB/170%/OpenGL 参数见 [burp-tablet.md](burp-tablet.md)。水杉/Fcitx5 OSK 的固定来源与未完成验收见 [input-method](../device/input-method/README.md)，不能作为默认稳定安装步骤。安装新输入法前保留可用的 Plasma Keyboard 回退入口。

实验 [FUTO Linux 移植](../device/futo-keyboard/README.md)需要用 `--futo-ui` 构建并安装 `sheng-msime-integration 0.2.1-8`，再编译原生英文词典/候选模块、准备原版图标/字体/布局并执行用户级 setup。核心 UI/UX 通过 Rust 原生渲染；FUTO 的非商业 Source First 许可、实际范围与回退单独记录。未移植完整 Android 应用、滑行或语音，不替换水杉中文引擎。不要将仅打包 `.deb` 等同于已完成 C++ 构建。

### 7. 小米 MiPPS 充电认证

基础镜像没有自动安装该服务，按 [MiPPS 部署说明](../device/charging/README.md)准备固定源码、测试、打包并增量安装 `xiaomi-mipps-auth 0.21+sheng1`。先核对匹配的内核私有接口、备份旧服务/规则，并验证 Wi-Fi SSH；认证过程可能切换 USB 数据角色。实际启用应已取得部署授权，不直接写认证成功标志或放宽温控/限流。

本机原装适配器初次认证及重新拔插后的自动认证均通过；固件120W上限不等于实测持续功率。服务由udev触发、执行后退出，`inactive/dead` 配合 `Result=success` 属正常；回退停止并卸载增量包，不重绑PMIC。原始认证材料与完整用户日志不导出。

### 8. 原生PowerDevil电源适配

按[原生电源说明](../device/power-management/README.md)从固定Debian/KDE 6.7.4-2源码构建 `4:6.7.4-2+sheng5`，保留发行版补丁并回移KDE亮度恢复修复；运行6组原生CTest及1组隔离亮度回归测试。用 `scripts/install-power-management.py` 安装匹配的核心库、PowerDevil和data包；只重启PowerDevil，不退出会话。安装器备份原deb及电源/锁屏/kwinrc配置，停用已知旧桌面恢复钩子，并检查电池提供者未被卸载。原生组件关闭DPMS渐黑特效，将关屏和锁屏激活等待减至1ms调度最小值；受保护的短按动作经原生DPMS直接关屏并锁定，亮度恢复保留用户设定值，其他动画及后台策略保留。

运行时低电量策略、档位锁屏时间同步及显示恢复在PowerDevil C++进程内执行。普通插电/离电不自动挂起；只有10%低电量档闲置5分钟挂起，保留5%临界保护。挂起模式需实机恢复验收后选择，不把内核列出deep当作通过；基础镜像的配置兼容工具不能代替这个原生增量。

### 9. Mesa 用户态 GPU 驱动

按 [GPU 驱动说明](../device/gpu-driver/README.md)准备固定 Mesa 26.3.1 和 Kali 打包规则，
在 ARM64 Linux 构建、运行上游测试。先解包整套新库做 Freedreno/Turnip/Zink 离屏读回测试，
再由安装器备份原包并通过一次 APT 事务安装。保留主线内核和匹配 PIN 模块，
不全局改用 Zink，不重启用户会话；正常重新登录后桌面合成器才加载新版。
基础镜像的软件源安装不等同于此源码增量。

## 回退与故障定位

| 层 | 诊断/回退 |
| --- | --- |
| 无法启动 | fastboot 检查槽位；必要时 `fastboot set_active a`、`fastboot reboot recovery`。恢复 Android 需本机型原厂固件/recovery 重建 userdata，会删除 Kali；A 槽不是用户数据备份 |
| PIN | 查看 `modinfo`、`journalctl -u sheng-devauth`、只读握手计数；卸载修复包后重装匹配原内核包，不能只删除唯一模块 |
| 热点 | `journalctl -u sheng-hotspot`、`iw dev`、专用 nft 表；停服务后重新测试原 wlan 上网，勿 flush 全局防火墙 |
| 网络 applet | 卸载补丁并重装匹配 plasma-nm，下一次会话加载原版 |
| 三指 | 新版在原生KWin中处理；回退匹配deb和自己的配置，下次正常登录加载 |
| 隐私 | `sudo /usr/libexec/sheng-privacyctl off`，核对冻结进程恢复后再卸载 |
| 桌面 | 使用自己部署前的备份恢复；作者 `restore.py` 的备份路径不适用于新设备 |

部署完成按 [验证清单](VALIDATION.md) 逐项验收。保留新设备日志于本地，公开 issue 使用去敏摘要。
