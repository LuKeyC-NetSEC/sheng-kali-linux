# Plasma Shell 原生桌面策略

目标为 `sheng / Kali ARM64 / plasma-workspace 4:6.7.4-2 / Qt 6.11.2+dfsg-5`。本轮将原 `desktop-policy.py` 的运行时脚本注入迁入 `ShellCorona` 持有的 [ShengDesktopPolicy](shengdesktoppolicy.cpp)。它是现有plasmashell中的对象，不是另一个桌面或后台守护进程。

- 用KWayland原生窗口模型观察最大化、全屏、最小化、焦点和瞬态窗口；直接调用自己的PanelView控制Dock。保留临时8秒唤出、外部点击收起与第三次上滑回桌面，应用保持运行。
- 原生遍历Corona已有的Containment/Applet模型，调用部件激活信号；不再通过 `evaluateScript` 查询和修改桌面对象。控制中心打开时，上滑入口先关闭控制中心。
- 从KWin触控插件的原生上下文v2接收物理输入设备事实，经KConfigLoader更新所属部件。无实体键盘时，抽屉初次打开不自动聚焦搜索。
- [workspace.patch](workspace.patch)同时在原AppletsLayout组件里先处理TouchCancel/空触点，再读取触点，终止旧长按计时器。

旧桌面手势QML、Python策略和服务已删除。新Shell在加载布局时清理旧手势部件实例；桌面触摸由KWin插件接管。控制中心通过原生D-Bus发布可见状态，KWin同时检查标记的实际弹窗；上滑动作在按下时确定归属，即使面板在松手前隐藏，也只执行关闭，不会转而打开抽屉。

固定源和签名见 [native-source-pins.json](../../configs/native-source-pins.json)，本地改动见 [provenance.json](provenance.json)。在匹配的ARM64环境构建：

```bash
python3 scripts/prepare-plasma-native.py
sudo apt-get build-dep --no-install-recommends ./out/plasma-native-source
bash scripts/build-plasma-native.sh
cmake -S device/plasma-integration/tests -B out/plasma-policy-tests
cmake --build out/plasma-policy-tests
ctest --test-dir out/plasma-policy-tests --output-on-failure
```

构建不安装或重启桌面。新Shell、KWin、上下文插件和输入法启动器须一起安排激活；当前会话的旧服务先保留，不能提前移除导致输入失效。首次加载和UI/输入验收需要用户方便时保存应用并正常重新登录，不绕过锁屏。完整组件及未完成迁移见 [源码归属审查](../../docs/NATIVE_SOURCE_MIGRATION.md)。

`migrate-installed.py` 是安装时的一次性清理工具：备份已知旧脚本、单元、插件和配置，删除旧副本，设置新的guard ID；不作为用户服务运行，不重启合成器/桌面。`--backup-only` 只创建私有备份；当前已保存26项且未改变服务。工具会检查本机和匹配的原生包，迁移须在用户正常退出会话的维护窗口执行。

Dock/手势归属的8个业务场景在ARM64 QtTest中实际执行通过（加上初始化/清理共10项）。包含控制中心在松手前已隐藏、可见窗体早于D-Bus通知和取消序列不穿透底层三种冲突场景；这些不是实机触屏验收。
