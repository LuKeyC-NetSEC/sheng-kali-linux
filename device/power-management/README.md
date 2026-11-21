# Sheng 原生电源管理

电源策略运行在 **PowerDevil 的 C++ 进程内**，使用现有 UPower、电源档、KIdleTime、logind/systemd 与 KScreen。没有新增电源策略守护进程，不通过定时脚本决定休眠，也不在电源档切换时执行锁屏配置脚本。

目标：sheng / Kali ARM64 / Plasma 6.7.4 / Qt 6.11.2。当前本地包为 `4:6.7.4-2+sheng5`，同时更新 PowerDevil、其核心库及匹配 data 包；保留 Debian 的 `upstream_avoid_low_battery_notification.diff`。更换 Plasma/Qt 后需重新移植和编译，不能复用不匹配的 ELF。

## 当前策略

| 状态 | 闲置锁屏和息屏 | 自动挂起 |
| --- | --- | --- |
| 插电，包括电脑USB | 1分钟 | 不自动挂起，后台继续 |
| 普通电量、离电 | 1分钟 | 不自动挂起，后台继续 |
| 进入KDE的10%低电量档、离电 | 1分钟 | 闲置5分钟后挂起 |
| 5%临界电量 | 保留PowerDevil临界保护 | 原生临界处理，支持挂起时选择挂起到RAM |

短按电源键通过原生DPMS直接息屏，同时保持“关屏前锁定”；长按显示原生电源菜单。正常电量保持后台运行，会有持续待机耗电，不能据此承诺Android式深睡续航。电脑USB供电不足时，外部电源在线与电池净放电也可能同时成立。

## 原生实现

- [shengpolicy.cpp](shengpolicy.cpp)：在 `Core::onControllersReady()` 中仅对本机做一次配置迁移；普通电量关闭自动挂起、低电量保留5分钟挂起、保留10%/5%阈值。以 `ShengPower/PolicyVersion` 标记迁移，后续用户通过系统设置调整的值不会在每次启动时被覆盖。
- `Core::profileChanged` 直接调用C++锁屏时间同步，通过KConfig写入当前档位的分钟数，再通过D-Bus通知原生锁屏服务；删除已知的 `sheng-set-screen-lock-timeout` 档位脚本调用，保留用户自己的其他命令。
- [powerdevil.patch](powerdevil.patch)：将组件接入现有Core，并在本机的原生DPMS闲置息屏路径中落实 `LockBeforeTurnOffDisplay`，避免只息屏而没有按该时限锁屏。
- `migrateDisplayOffDefaults()` 一次性写入原生KWin的 `Effect-Kscreen/Duration=1`、`Plugins/kscreenEnabled=false`，卸载当前渐黑特效并请求KWin重新读取配置；按 `DisplayOffPolicyVersion=2` 标记迁移。后续用户明确修改的配置不会被反复覆盖。其他特效、动画速度、闲置时限和低电量保护保持原配置。
- 对仍配置为 `PowerButtonAction=32` 且 `LockBeforeTurnOffDisplay=true` 的档位，迁移为原生 `TurnOffScreen=64`，经HandleButtonEvents直接触发DPMSControl；原生DPMS仍发送锁屏请求，关屏不再等待锁屏页加载。迁移完成后调用现有 `Core::refreshStatus()` 重载按钮动作；显式选择的其他动作和未开启关屏前锁定的配置不改写，长按16保持不变。
- 锁屏激活后的最短原生DPMS闲置等待仅在sheng上由100ms改为1ms，保留KIdleTime的唤醒/恢复生命周期、抑制策略以及锁屏后正常交互的10秒最小时限。自动息屏与短按电源键均不再先绘制KScreen的全屏渐黑层。
- [上游亮度恢复补丁](upstream-brightness-restore.patch)：回移KDE Plasma/6.7的 `76dc5ace88031d03a86acd93767730e389e2b8ab`，保留原作者和补丁内容。停止管理输出时清除遗留调暗；重新接管时读取输出实际调暗系数，并应用当前控制器的有效系数。用户选择的亮度和当前有意设置的调暗限制均保留，不增加周期性亮度覆盖。
- 原生挂起/恢复信号捕获当前会话；恢复时只允许回到同一用户、已锁定且原生锁屏仍活动的会话。KScreen仅在内屏缩放实际偏离保存值时修正。不会重启KWin/Plasma、关闭应用、杀死键盘或强制激活输入上下文。
- 旧 `60-sheng-desktop` system-sleep脚本由安装器备份并停用；输入连接继续由现有KWin/Fcitx launcher管理。热点自己的硬件睡眠恢复钩子保留。

`configure-power-buttons.sh` 留作基础镜像及一次性配置工具。原生包安装后，它不再写入档位脚本钩子。[power-status.py](power-status.py)是用户主动运行的只读诊断命令；[validate-suspend.py](validate-suspend.py)是一次性验收工具。这些都不承担常驻电源策略。

## 固定源码与构建

[provenance.json](provenance.json)固定 KDE 6.7.4 提交、Debian 6.7.4-2 的dsc/orig/debian归档及SHA-256；dsc通过Debian开发者密钥验证。原始版权、Debian补丁和许可证均保留。

在匹配的ARM64 Linux平板/构建环境，从仓库根运行：

```bash
sudo apt-get install --no-install-recommends dpkg-dev gpgv debian-keyring
python3 scripts/prepare-powerdevil.py
sudo apt-get build-dep --no-install-recommends ./out/powerdevil-source
bash scripts/build-powerdevil.sh
# 只重启PowerDevil，保留KWin、Plasma、应用和锁屏。
sudo python3 scripts/install-power-management.py --packages out --user kali --sleep-mode s2idle
```

原生包需要与设备相同的Qt `6.11.2+dfsg-5`；构建依赖解析不得顺带升级当前Plasma/Qt ABI。原始deb会在修改前下载或从校验过的安装缓存备份，三个匹配的原生包作为一组安装；如果原先安装了powerdevil-dev，也必须提供匹配的dev包。安装器同时备份powerdevilrc、kscreenlockerrc、kwinrc，检查运行中的核心库映射与磁盘新库一致，并确认电池提供者的内核实例未变。

安装器只负责部署、备份和回退，不作为常驻进程运行。备份保存在 `/var/lib/sheng-power-management/backup-*`，含原deb和相关配置，不公开上传。回退会恢复该次安装前的电源/锁屏配置及旧恢复钩子：

```bash
sudo python3 scripts/install-power-management.py --user kali --restore
```

## 亮屏后变暗的回归验证

上游 [KDE Bug 523988](https://bugs.kde.org/show_bug.cgi?id=523988)描述了滑条不变、输出保持调暗的故障，修复进入6.7.6。本机在固定6.7.4源码上回移该单项修复，保持现有Qt/KWin ABI。

`brightness-tests`使用真实 `KWinDisplayBrightness` 源码与隔离的KScreen输出对象，将后端写入替换为测试捕获，不访问实际显示器或用户D-Bus。三个业务场景验证：接管0.3调暗的输出后恢复有效系数1.0且保留0.8亮度、保留当前有意请求的调暗限制、正常输出不产生多余写入。原6.7.4在首项失败；补丁后3项均通过（QtTest含初始化/清理共5项）。构建器自动运行这组额外CTest。

实机安装前在息屏状态读取到亮度设定0.8026、调暗系数0.3；更新后系数为1.0，滑条8026/10000及背光1643/2047保持不变，KWin/Plasma未重启。用户再次测试两次息屏/亮屏均正常。息屏期间存在0.3系数本身可以是正常闲置调暗；本次没有捕捉到原偶发故障发生时的亮屏现场，不能仅凭两次正常就认定长期问题完全消失。方法、源码和包哈希、未测项见[亮度验证](brightness-validation.json)。

## 挂起模式与验收

本机内核列出 `s2idle` 和 `deep`；systemd持久配置保留s2idle。这两者只决定真正挂起时的方式，普通电量的1分钟锁屏息屏不会进入挂起。s2idle依赖设备空闲和CPU休眠，deep尝试进入平台更深的挂起状态；实际省电与恢复效果必须实测。

2026-11-21经用户授权，以临时systemd配置测试过一次deep：内核确认进入和退出，挂起成功计数0→1、失败0，原桌面进程和锁屏保留；但在约3.511秒提前唤醒，原定20秒唤醒闹钟随后正常回调。唤醒来源尚未确认，不能登记为睡满20秒、deep稳定或已获得省电收益。测试结束已删除临时覆盖、恢复息屏，持久默认仍为s2idle。变更模式使用systemd的sleep配置，不直接替换内核、写PMIC寄存器或重绑电源管理设备。

验收工具调用PowerDevil自己的 `scheduleWakeup`、`suspendToRam` 和 `wakeup`，只登记和清理自己的闹钟。运行会暂停网络，自动唤醒后点亮锁屏，保持认证状态：

```bash
# 在能够接受短暂断网时运行；不是后台服务。
python3 device/power-management/validate-suspend.py --allow-suspend --seconds 20 --output out/suspend-check.json
sheng-power-status
```

通过计数和 `CLOCK_BOOTTIME - CLOCK_MONOTONIC` 增量确认是否真的挂起，比较原桌面进程及锁屏是否保留。PIN实际输入、触摸板、缩放、软键盘和网络恢复还需用户确认；不能只凭服务active登记通过。

2026-11-21 `+sheng4` 在目标ARM64完整清理构建后通过6组CTest，原生策略QtTest共8项通过；另有3项隔离KConfig配置测试通过。覆盖默认时限、临界保护、其他特效/动画保留、短按锁屏保护条件、用户其他电源动作及后续编辑保留。构建器先清理生成的构建/打包状态，避免debhelper旧stamp跳过新增逻辑；安装器核对运行库、原生迁移版本及配置，失败会回退。

用户确认自动息屏不再出现黑底指针阶段；初版`+sheng3`的短按锁屏仍有该阶段，改走原生DPMS的`+sheng4`复验确认直接息屏且再次点亮仍需解锁。两次安装均保留KWin/Plasma会话与电池提供者。当前[直接息屏验收](direct-display-off-validation.json)分别注明用户确认对应的版本；[旧电源策略与deep试验快照](validation.json)保留为历史记录。最终包的自动息屏视觉复测、离电实体供电切换、长期反复操作及实际硬件关屏延迟仍未单独测量。

KWin当前的动画TimeLine要求正时长，不能简单设置为0。此适配关闭息屏渐黑特效，并将原有250ms等待减至1ms事件循环调度最小值；显示输出仍由原生DRM/DPMS关闭，没有直接写背光、隐藏鼠标、停止应用或挂起来模拟息屏。面板实际断电仍有硬件提交延迟，不能把1ms配置值当作实测关屏延迟。

诊断中的电池净功率由电量计电压/电流估算，负值表示净放电，不是USB输入功率；DPMS关闭后背光驱动仍可能报告缓存的亮度值，不能单凭该值判断屏幕仍发光。已有检查中Wi-Fi省电开启，GPU和空闲音频节点支持运行时休眠；没有叠加TLP、TuneD或另一个电源档后端。
