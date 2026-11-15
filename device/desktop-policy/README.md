# Dock 与桌面触屏策略

当前平板只有一个虚拟桌面。活动应用最大化或全屏时，KWin 的 [DesktopPolicy.qml](../recents/contents/ui/DesktopPolicy.qml) 通知用户会话服务，将底部原生 Dock 切为自动隐藏；还原小窗口或最小化后恢复显示。上下滑入／滑出由 Plasma 原生底边动画处理。最大化、还原、全屏、最小化四种状态已做设备测试，用户已确认动画正常。

[desktop-policy.py](desktop-policy.py) 通过 KWin 输入设备信号识别鼠标、触摸板。PIN 键盘的输入节点在脱离后可能仍存在，额外以 `nanosic_hinge/keyboard_attached` 判断实际连接；该内存属性每 250 毫秒只读检查一次，变化时才更新配置。触摸板按用户要求计入鼠标。

无鼠标和触摸板时，[桌面手势部件](desktop-gesture/contents/ui/main.qml) 将触屏下滑区域放到现有桌面窗口的整个右半区。它在拖动完成时调用已有控制中心，不添加可点击入口；应用窗口、状态栏、Dock 使用各自窗口的触控，不被桌面区域遮挡。应用内的整条最右侧入口已删除。原状态栏的下滑入口继续沿用。

用户服务为 `sheng-desktop-policy.service`，会话总线为 `org.sheng.DesktopPolicy`，状态保存在 `~/.local/state/sheng-desktop-policy/state.json`。服务在 Plasma 重启后重新同步输入状态。原有物理键盘软键盘策略保持不变。

安装包与验证见本机 `out/desktop-privacy-verification.json`；本轮配置备份由平板 `~/.local/state/sheng-ui-update/backup-path` 指向。构建包需提供本机已编译的隐私 BPF 程序：

```sh
python3 build-device-package.py /usr/libexec/sheng-privacy-bpf sheng-tablet-controls_1.0-1_arm64.deb
```

此包安装会话服务、桌面手势和隐私后端。控制中心与 KWin 效果分别使用 `out/packages/` 下的 `.plasmoid` 和任务卡片 `.zip` 包，保留现有插件 ID／部件布局配置。当前实现针对本机 `kali` 用户（UID 1000）。
