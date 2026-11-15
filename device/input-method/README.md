# 实验：水杉输入法与触屏键盘

用户目标为实体键盘和触屏都使用水杉。当前实现：**水杉 Fcitx5 引擎 + Fcitx5 OSK 屏幕键盘 + KWin Wayland 输入面板**，不是水杉内置独立软键盘。尚未完成解锁后的实际中文上屏验收，不属于稳定基础镜像。

## 固定来源

- 官方 [msime-linux 0.16.1 ARM64](https://github.com/metasequoiaime/msime/releases/tag/linux-v0.16.1)，deb SHA-256：`1f2542ed775e9bbf74b86aa0a901ce02af8f3f3652ef8aee54392b2b62fa853c`。
- 本机 Fcitx5 5.1.23，安装 Qt5/Qt6/GTK3/GTK4 前端。
- [fortime/fcitx5-osk](https://github.com/fortime/fcitx5-osk) 0.2.1，annotated tag 对象 `b9827484569af50ffb2b33fbc859492b3b0db0f1` 指向源码 commit `76a33b65b1c72519788c09cfb9f94c1df0f61949`；按上游原生 ARM64 构建，不编译实验 KWin 插件。
- 依赖 `xdg-desktop-portal` 与 `xdg-desktop-portal-kde`，缺失时 OSK 无法正常完成部分启动流程。

## 复现与策略

`build-device-package.py STAGING GUARD OUTPUT.deb` 只打包**已完成上游安装的 staging**（含 `usr/bin/fcitx5-osk`、helper、service 及上游许可证），GUARD 为仓库 `scripts/keyboard-policy.py`。源码打包版本 `0.2.1-2` 增加卸载回退；实机此前为 `0.2.1-1`，未因源码发布升级，也未将新版标记已验。

KWin 的 `Wayland/InputMethod` 指向 `/usr/share/applications/sheng-msime-fcitx5.desktop`，其 wrapper 进入 `sheng-msime-launcher`。热切换用 `kwriteconfig6 ... --notify`；只调用 reconfigure 不足以替换输入面板。

Fcitx 默认引擎为 msime，保留 keyboard-us；全拼 `quanpin`。本机关闭云候选与翻译，停用语音/在线 socket 和剪贴板服务。每个开发者从官方设置初始化自己的资源和账户，**不能复制作者 preferences、匿名凭据、学习库或运行缓存**。

Plasma 会话只设置 `XMODIFIERS=@im=fcitx`，不全局强制 `QT_IM_MODULE`/`GTK_IM_MODULE`，避免干扰 Wayland text-input。禁用重复的 Fcitx autostart，由 KWin launcher 管理。

实体键盘连接时通过 OSK `ManualMode`/`ForceHide` 阻止触屏自动弹出；候选窗口同属 input-panel，不能强制清除 KWin active 来抑制，否则可能取消中文组合。新 guard 以包内 drop-in 覆盖服务 ExecStart，保留基础脚本可回退。helper 为受限修饰键用途，udev 和路径当前针对 kali/UID1000。

## 待验收与恢复

最后检查时平板锁屏，OSK 进入独立锁屏模式并正常停止普通会话 Fcitx；测试窗口无法接收输入。此状态不能证明引擎失败，也不能证明中文成功。

待解锁后检查：实体中文组合/上屏、触屏中文、PIN接入不弹软键盘、拔下后恢复、锁屏解锁及挂起恢复。每项分开记录。未完成前保留 `/usr/share/applications/org.kde.plasma.keyboard.desktop` 回退入口，卸载集成包后确认 KWin InputMethod 与用户服务回到基础实现。不要为验收绕过锁屏或关闭已有应用。
