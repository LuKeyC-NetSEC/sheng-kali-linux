# 实验：水杉输入法与触屏键盘

用户目标为实体键盘和触屏都使用水杉。当前实现：**水杉 Fcitx5 引擎 + Fcitx5 OSK 屏幕键盘 + KWin Wayland 输入面板**，不是水杉内置独立软键盘。用户已确认 PIN 中文、接入时抑制软键盘、连续自动弹出，以及新界面的触屏中文、长按悬浮拖动和停靠切换正常。2026-11-21 另确认锁屏两页和正常解锁；挂起恢复仍需独立验收，暂不属于默认基础镜像。

## 固定来源

- 官方 [msime-linux 0.16.1 ARM64](https://github.com/metasequoiaime/msime/releases/tag/linux-v0.16.1)，deb SHA-256：`1f2542ed775e9bbf74b86aa0a901ce02af8f3f3652ef8aee54392b2b62fa853c`。
- 本机 Fcitx5 5.1.23，安装 Qt5/Qt6/GTK3/GTK4 前端。
- [fortime/fcitx5-osk](https://github.com/fortime/fcitx5-osk) 0.2.1，annotated tag 对象 `b9827484569af50ffb2b33fbc859492b3b0db0f1` 指向源码 commit `76a33b65b1c72519788c09cfb9f94c1df0f61949`；按上游原生 ARM64 构建，不编译实验 KWin 插件。
- 依赖 `xdg-desktop-portal` 与 `xdg-desktop-portal-kde`，缺失时 OSK 无法正常完成部分启动流程。

## 复现与策略

`build-device-package.py STAGING OUTPUT.deb` 只打包已完成上游安装的ARM64 staging，并要求启动器的 `--sheng-native-version` 返回匹配接口版本。当前源码只生成 `0.2.1-10+native1` 原生版，依赖KWin输入API v1、上下文v2及匹配的原生桌面包。旧Python策略、服务和兼容分支已删除；安装不再启用它们。实机当前运行的0.2.1-9仍是此前已验证基线，新版尚待成组维护和实机验收。

KWin 的 `Wayland/InputMethod` 指向 `/usr/share/applications/sheng-msime-fcitx5.desktop`，其 wrapper 进入 `sheng-msime-launcher`。热切换用 `kwriteconfig6 ... --notify`；只调用 reconfigure 不足以替换输入面板。

Fcitx 默认引擎为 msime，保留 keyboard-us；全拼 `quanpin`。本机关闭云候选与翻译，停用语音/在线 socket 和剪贴板服务。每个开发者从官方设置初始化自己的资源和账户，**不能复制作者 preferences、匿名凭据、学习库或运行缓存**。

[fcitx5-1.23.patch](fcitx5-1.23.patch) 修复固定 OSK 上游与本机 Fcitx 5.1.23 的翻页接口不兼容：实际 `NextPage()` / `PrevPage()` 不接收页码，旧代理发送整型参数会被 D-Bus 拒绝。准备器校验补丁哈希并应用；内部候选游标仍由 OSK 管理，传输层只发送无参数调用。不同 Fcitx 版本须核对实际接口，不能只凭候选显示出来就登记翻页通过。

Plasma 会话只设置 `XMODIFIERS=@im=fcitx`，不全局强制 `QT_IM_MODULE`/`GTK_IM_MODULE`，避免干扰 Wayland text-input。禁用重复的 Fcitx autostart，由 KWin launcher 管理。

实体键盘连接时通过 OSK `ManualMode`/`ForceHide` 阻止触屏自动弹出；候选窗口同属 input-panel，不能强制清除 KWin active 来抑制，否则可能取消中文组合。策略通过原生桌面 guard 的 `GetKeyboardContext()` 区分桌面、应用、抽屉和锁屏，只输出窗口角色、锁屏状态和变化序号，不读取输入内容。桌面残留文本上下文被隐藏；回到应用后等待 ManualMode 实际确认，再按输入焦点变化调用 Fcitx 正式接口。可选 guard 暂不可用时保留原来的应用输入能力，不能因此禁用全部软键盘。新 guard 以包内 drop-in 覆盖服务 ExecStart，保留基础脚本可回退。helper 为受限修饰键用途，udev 和路径当前针对 kali/UID1000。

锁屏期间仍根据实体键盘热插拔更新 KWin `mode`，并为安全面板恢复正确的 ManualMode；策略不直接显示安全面板，由原生 greeter 在密码页管理。Plasma 6.7 的接口是 `mode`，不是已移除的 `enabled`，锁屏表现层需一起按[锁屏说明](../../docs/TOUCH_LOCKSCREEN_FONTS.md)更新。

2026-11-21 首轮限制策略验收失败；恢复连接时发现 KWin `Wayland/InputMethod` 为空，OSK 窗口仍在但输入引擎没有正常连接。恢复原策略和正确的 InputMethod 后，用户确认 PIN 键盘/触摸板与应用软键盘恢复；没有重新绑定 I²C/TEE 或修改 PIN 驱动。修正版安装后，用户确认时钟页不弹、密码页自动弹出并能正常解锁，桌面等待不弹且应用输入框仍能弹出/输入。11 项策略单元测试通过；锁屏期间键盘热插拔仅有逻辑测试，休眠恢复和长期稳定性仍需独立验收。

## 待验收与恢复

初次检查遇到锁屏，OSK 进入独立锁屏模式并正常停止普通会话 Fcitx；此状态不能当作输入失败证据。随后解锁，用户确认 PIN 的“nihao → 你好”成功及接入时抑制软键盘正确，但报告拔下后不能弹出。

固定上游 launcher 的普通会话自动 Show 路径依赖 KWin tabletMode。guard 增补输入上下文激活/文本支持变化监听：无实体键盘、普通会话模式下按状态转换调用 Fcitx `/virtualkeyboard` 的 `ShowVirtualKeyboard`，同时恢复引擎的 OnScreenKeyboard 模式，避免只显示 OSK 窗口却保留 PhysicalKeyboard 模式。无实体键盘时 KWin 使用 AnyInput，接入后仍用 Never。不会每秒强制弹出或清除中文组合上下文；锁屏由上游独立处理。

用户已确认第一版兼容逻辑可弹出，但并非每次成功；随后通过正式 Fcitx 接口恢复模式，用户确认连续点击每次弹出。功能键缺字与上游默认请求不存在的 NotoSerif NF 有关：补充 Noto CJK 和 Material Design 图标字体，并在新界面使用常见 Unicode 功能键图标。新版安装后用户确认触屏中文正常。

## 澎湃风格触屏界面

[hyperos-ui.patch](hyperos-ui.patch) 在固定上游源码上重写键帽、工具栏与面板外观，不更换水杉引擎。触屏布局移除桌面键盘的 Ctrl/Alt/Super 长行，保留数字行、QWERTY、Shift、Tab、标点、空格和回车；字母不重复显示大小写标记。圆角键帽、蓝色回车、浅/深色面板与可见拖动手柄位于 [ui/](ui/)，字体来源为系统包，不复制小米字体或图像。

工具栏提供中英切换、停靠/悬浮、设置与收起。悬浮模式保持原有长按约 1 秒拖动规则；横屏宽 640、竖屏宽 480 逻辑像素。拖动位置在该 OSK 进程中保留，进程重启后不承诺恢复原位置。没有移植小米商业输入引擎、云服务或系统玻璃材质。

2026-11-15 已在 ARM64 实机完成优化构建，安装 `sheng-msime-integration 0.2.1-3`，截图检查键帽、功能键、主题和浮窗显示；用户确认“中文、拖动和切换都正常”。原始截图包含私人桌面/浏览器内容，不随源码公开。构建时的内存峰值与运行时占用不同，本次 release 优化阶段峰值约 5.3 GiB，建议限制并发并预留 swap。

### 从公开源码构建

在 ARM64 Linux 上安装 Rust/Cargo、CMake >=4.1、pkg-config、Wayland/EGL/XKB/OpenSSL/Fontconfig 等开发依赖，按上游 README 补齐具体发行版包名。来源、archive/patch SHA-256 与基础文件哈希见 [provenance.json](provenance.json)。

```bash
python3 scripts/prepare-osk-ui.py
cmake -S out/osk-source -B out/osk-cmake -DCMAKE_INSTALL_PREFIX=/usr -DCMAKE_INSTALL_LIBDIR=lib/aarch64-linux-gnu
CARGO_BUILD_JOBS=2 cmake --build out/osk-cmake --parallel 2
DESTDIR="$PWD/out/osk-stage" cmake --install out/osk-cmake --component Fcitx5Osk
DESTDIR="$PWD/out/osk-stage" cmake --install out/osk-cmake --component Fcitx5OskKwinLauncher
python3 device/input-method/build-device-package.py out/osk-stage out/packages/sheng-msime-integration_0.2.1-10+native1_arm64.deb
# 保存应用并准备正常重新登录后，成组安装匹配的原生组件；此处不立即安装。
# 桌面用户、解锁状态下，启用布局和字体；只重新加载输入面板
sheng-osk-mode float --font-defaults --sheng-ui
# 切回底部停靠
sheng-osk-mode dock
```

先安装固定版本 msime-linux，并按前文设置 Fcitx profile 与 KWin InputMethod；集成包不复制用户词库或账户。构建器不会自动编译实验 KWin 插件。此处路径从仓库根开始；干净源码构建可能需要较长时间和大量缓存空间。

已完成：实体中文组合/上屏、触屏中文、PIN接入不弹软键盘、拔下后连续弹出，以及新界面的拖动和模式切换。锁屏时钟页/密码页与正常解锁本轮已确认；锁屏内热插拔、挂起恢复仍需独立记录。保留 `/usr/share/applications/org.kde.plasma.keyboard.desktop` 回退入口，卸载集成包后确认 KWin InputMethod 与用户服务回到基础实现。不要为验收绕过锁屏或关闭已有应用。

可选 [FUTO 原生移植](../futo-keyboard/README.md)在本输入面板上接入 FUTO/LatinIME 的英文 C++ 候选核心、QWERTY 布局和默认调色板；中文引擎仍为水杉。两者来源和许可证分开记录，不把 Linux 适配器称为完整 Android FUTO 应用。

## 原生策略迁移（待统一加载）

[native-policy.rs](native-policy.rs)把独立Python显示策略移入OSK的Rust启动器。监听KWin文本上下文、窗口角色、原生输入设备事实、OSK模式/ManualMode确认及服务owner变化；没有每秒轮询。实体键盘连接时隐藏面板但保留Fcitx中文组合上下文，无键盘时通过Fcitx正式接口进入屏幕键盘模式。桌面禁止残留输入焦点误弹；锁屏仅由greeter控制安全面板，不强制显示。

[native-launcher.patch](native-launcher.patch)调用KWin原生重载API，移除临时删除再写回 `Wayland/InputMethod` 的做法；重载不改持久启动项，退出等待限制为1秒。新策略要求[KWin输入API v1](../kwin-integration/README.md)与[原生上下文v2](../desktop-touch-guard/README.md)。缺少接口时不会清空配置或通过模拟输入兜底；新旧策略不能同时启用。

```bash
python3 scripts/prepare-osk-ui.py --futo-ui --output-dir out/osk-native-source
bash scripts/build-native-launcher.sh out/osk-native-source
```

这两条只准备源码、运行13项策略测试并编译启动器，不安装或重启。也可把 `prepare-native-launcher.py SOURCE` 应用到已核验的、尚未修改启动器的FUTO源码树，保留其UI和中文引擎。2026-11-21在sheng ARM64上13项测试与release编译通过，包含ScreenSaver提前锁定信号，防止合成器锁状态尚未更新时误弹普通面板；已安装原生启动器，须正常重新登录完成交接，实际中文、密码页、PIN热插拔仍待在用户方便时正常重新登录后验收。旧版仅保留在Git历史和设备私有回退包中。
