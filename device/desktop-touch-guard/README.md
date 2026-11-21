# 原桌面的触屏手势与防框选

本组件在 KWin Wayland 内处理**桌面窗口**的触摸移动，桌面上滑打开 Linexin 抽屉；没有鼠标/触摸板时，右半区下滑打开已有控制中心。另在 Dock 隐藏时保留屏幕底边 10 逻辑像素，用于两段上滑唤出；应用普通内容区、鼠标和触摸板不被此策略接管。不读取或独占 `/dev/input/event*`。

两段唤出：第一次上滑显示 3 秒白条，期间再次上滑唤出临时 Dock；其上角圆、下角贴齐屏幕呈直角。默认显示 8 秒，触摸 Dock 延长。点击 Dock 外部窗口时立即请求原生向下隐藏，原点击继续传给应用；Dock 弹出菜单和全屏抽屉排除在外。临时 Dock 显示时，再从相同底边上滑一次返回桌面，应用继续留在后台。锁屏会清理入口。详见[交互说明](../../docs/TOUCH_LOCKSCREEN_FONTS.md)。

鼠标/触摸板按下与触屏按下在合成器内按实际命中窗口判断，因此点已获得焦点的最大化窗口同样能收起 Dock，不依赖焦点变化。只观察这些按下，不拦截应用；底边 10 逻辑像素继续作为系统手势区域。返回桌面使用 KWin 原生显示桌面状态，保留窗口的最大化/全屏状态；回到应用后继续正常自动隐藏。

首次桌面触摸移动达到 3 逻辑像素时，向桌面发送 Wayland touch cancel，避免 Folder View 的模拟鼠标路径启动框选。手势结束仍向下层 KWin 过滤器传递 touch up，清理屏幕边缘及多指跟踪状态；多指序列不触发抽屉/控制中心。点击与长按仍使用桌面原有规则。这里只拦截桌面表面的移动，因此桌面部件上的触屏拖动也会受限；编辑布局请使用鼠标/触摸板。

它调用 `org.sheng.DesktopPolicy` 的 `OpenAppDrawer` / `OpenControlCenter`，使用自身原生输入设备状态；没有添加另一个主屏幕，也没有全局应用内导航入口。旧QML桌面手势部件已移除，取消/长按生命周期在原生Plasma组件处理。

全屏 Sheng 抽屉存在时，还为同一输出的底部 Plasma 面板添加 KWin stacking constraint，使真实 Dock 保持在抽屉上方；关闭抽屉后移除。Dock 不进入抽屉自身的缩放/淡入动画，不再显示两份。输入命中也使用同一窗口堆叠顺序。

## 构建与加载

仅在目标 Linux 系统或与其开发包完全匹配的构建环境编译。已验证 KWin `4:6.7.4-2+b1`、Qt `6.11.2`、ARM64；KWin 内部输入 API 不稳定，CMake 当前严格要求 `6.7.4 EXACT`。更新 KWin/Qt 后必须重新审核源码和编译，不能复制旧 `.so` 或仅删除版本检查。

在仓库根目录：

```bash
sudo apt-get install build-essential cmake ninja-build extra-cmake-modules \
    kwin-dev qt6-base-dev qt6-declarative-dev libudev-dev
bash scripts/build-desktop-touch-guard.sh
sudo cmake --install out/build-desktop-touch-guard
# 以下以正在运行 Plasma 的用户执行
guard_id=$(cat out/build-desktop-touch-guard/touch-guard-id.txt)
kwriteconfig6 --file kwinrc --group Plugins --key "${guard_id}Enabled" true
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.loadEffect "$guard_id"
qdbus6 org.sheng.DesktopTouch /org/sheng/DesktopTouch org.sheng.DesktopTouch.GetStatus
```

先按[抽屉部署说明](../../docs/DESKTOP_DRAWER.md)安装用户会话服务和启动器。`GetStatus` 仅返回次数、范围、指针和 Dock 约束状态，不记录输入内容或坐标。热加载无需重启 KWin。构建从 C++、元数据和 CMake 内容生成不同的插件 ID/文件名，避开 Qt 插件工厂缓存；升级先卸载并将旧 ID 的 Enabled 写成 false，再启用新 ID，不能同时加载两个 guard，也不在同一路径覆盖已映射的二进制。

## 验收与回退

`GetInputContext()` / `KeyboardContextChanged()` 为输入策略提供锁屏状态、前台窗口角色和变化序号，不返回窗口标题或文本内容。桌面残留文本焦点不再触发自动软键盘；新启动器要求匹配的原生上下文接口，不能提前卸掉当前正在承担锁屏输入的组件。

`GetInputContext()` 以 `a{sv}` 返回上下文v2，包含上述事实以及物理键盘、鼠标/触摸板状态。它由 [inputpresence.cpp](inputpresence.cpp) 监听KWin已有设备增删、启用状态和PIN属性的sysfs通知；USB/蓝牙按udev属性识别，排除触屏、笔和虚拟输入，PIN拔下时排除残留HID节点。设备事件合并350ms，恢复后重新检查，没有周期扫描或第二个libinput客户端。接口不返回设备名称、按键或输入内容。

v2插件 `sheng_desktop_touch_guard_96793da01c9e` 已在匹配ARM64环境构建，已随原生包安装，当前会话已加载v2插件。它是[原生输入法启动器](../input-method/README.md)的必需接口，须与KWin/Plasma迁移一起安排加载。现有用户确认属于下面的v1部署；不能套用为v2的热插拔/锁屏验收。USB键盘、蓝牙鼠标暂无实物，本轮仍未验证。

已获用户确认：原桌面左/中/右上滑打开抽屉；触屏无框选；临时 Dock 点击外部立即向下收起、原点击生效、Dock 本身不误收起；第三次底边上滑返回桌面及重新打开应用后 Dock 自动隐藏均正常。当前构建为 sheng ARM64 / KWin 6.7.4 / Qt 6.11.2，2026-11-21 增补键盘上下文接口并原生编译，启用的源码散列 ID 为 `sheng_desktop_touch_guard_5e3a927fc736`；用户确认桌面等待不弹软键盘，应用输入框仍正常。原 Dock 手势未在此次改动后全面复验；鼠标/触摸板的新按下观察路径未独立实测；横竖屏、挂起恢复仍待回归。

停用后恢复原生桌面触控行为，用户应用继续运行：

```bash
guard_id=$(cat out/build-desktop-touch-guard/touch-guard-id.txt)
kwriteconfig6 --file kwinrc --group Plugins --key "${guard_id}Enabled" false
qdbus6 org.kde.KWin /Effects org.kde.kwin.Effects.unloadEffect "$guard_id"
```

源码为 GPL-3.0-or-later，许可证见仓库根 [LICENSE](../../LICENSE)。

控制中心打开时，桌面上滑序列在初次按下即归控制中心所有，后续面板隐藏不会改变它；底边Dock入口也让位于控制中心。滑条与Wi-Fi/蓝牙列表由控制中心自己的保护区域处理，不会触发关闭。取消序列不会打开底层抽屉。对应跨组件回归场景见Plasma策略测试，实机触屏仍待复验。

原生部署包已包含该插件，安装迁移工具会设置新ID并删除旧副本，不需另启用键盘/桌面策略服务。构建插件时使用新KWin包提取的SDK；部署包通过CMake安装阶段移除临时RPATH。

## PIN背折姿态

`InputPresence` 在PIN物理连接的基础上，读取KWin原生TabletModeManager的硬件原始状态；只在确有物理 `SW_TABLET_MODE` 开关时采用该值。它不使用用户手动强制的平板模式设置，不增加evdev读取器或轮询服务。现有驱动已经接收霍尔开关并控制PIN输入，桌面侧把背折的PIN键盘及其触摸板视为不可用；另接的USB/蓝牙键鼠仍独立统计。

输入上下文v2新增 `pinAttached`、`pinFoldedBack`、`pinAvailable` 三个只读诊断字段。折回背部时可解除软键盘抑制，并在没有其他指针设备时开放桌面右半区控制中心入口；展开后恢复正常PIN判定。认证和实际连接状态不被伪造或重置。

2026-11-21已使用匹配的原生KWin SDK编译并热加载 `sheng_desktop_touch_guard_07ab61dd7a95`，包为桌面1.0-8+native1/输入法0.2.1-11+native1。正常展开实际读取attached=true、folded=false、available=true；认证仍active且NRestarts=0，KWin/Plasma未重启。背折、展开往返和外部键鼠共存的实机验收尚未完成，不能把存在SW能力或编译成功当作物理检测通过。
