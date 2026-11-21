# Sheng 原生电源管理

电源策略运行在 **PowerDevil 的 C++ 进程内**，使用现有 UPower、电源档、KIdleTime、logind/systemd 与 KScreen。没有新增电源策略守护进程，不通过定时脚本决定休眠，也不在电源档切换时执行锁屏配置脚本。

目标：sheng / Kali ARM64 / Plasma 6.7.4 / Qt 6.11.2。当前本地包为 `4:6.7.4-2+sheng2`，同时更新 PowerDevil、其核心库及匹配 data 包；保留 Debian 的 `upstream_avoid_low_battery_notification.diff`。更换 Plasma/Qt 后需重新移植和编译，不能复用不匹配的 ELF。

## 当前策略

| 状态 | 闲置锁屏和息屏 | 自动挂起 |
| --- | --- | --- |
| 插电，包括电脑USB | 1分钟 | 不自动挂起，后台继续 |
| 普通电量、离电 | 1分钟 | 不自动挂起，后台继续 |
| 进入KDE的10%低电量档、离电 | 1分钟 | 闲置5分钟后挂起 |
| 5%临界电量 | 保留PowerDevil临界保护 | 原生临界处理，支持挂起时选择挂起到RAM |

短按电源键锁屏并按原生锁屏策略息屏；长按显示原生电源菜单。正常电量保持后台运行，会有持续待机耗电，不能据此承诺Android式深睡续航。电脑USB供电不足时，外部电源在线与电池净放电也可能同时成立。

## 原生实现

- [shengpolicy.cpp](shengpolicy.cpp)：在 `Core::onControllersReady()` 中仅对本机做一次配置迁移；普通电量关闭自动挂起、低电量保留5分钟挂起、保留10%/5%阈值。以 `ShengPower/PolicyVersion` 标记迁移，后续用户通过系统设置调整的值不会在每次启动时被覆盖。
- `Core::profileChanged` 直接调用C++锁屏时间同步，通过KConfig写入当前档位的分钟数，再通过D-Bus通知原生锁屏服务；删除已知的 `sheng-set-screen-lock-timeout` 档位脚本调用，保留用户自己的其他命令。
- [powerdevil.patch](powerdevil.patch)：将组件接入现有Core，并在本机的原生DPMS闲置息屏路径中落实 `LockBeforeTurnOffDisplay`，避免只息屏而没有按该时限锁屏。
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

原生包需要与设备相同的Qt `6.11.2+dfsg-5`；构建依赖解析不得顺带升级当前Plasma/Qt ABI。原始deb会在修改前下载备份，三个匹配的原生包作为一组安装；如果原先安装了powerdevil-dev，也必须提供匹配的dev包。安装器检查运行中的核心库映射与磁盘新库一致，并确认电池提供者的内核实例未变。

安装器只负责部署、备份和回退，不作为常驻进程运行。备份保存在 `/var/lib/sheng-power-management/backup-*`，含原deb和相关配置，不公开上传。回退会恢复该次安装前的电源/锁屏配置及旧恢复钩子：

```bash
sudo python3 scripts/install-power-management.py --user kali --restore
```

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

6组CTest已在目标ARM64环境通过，包含升级旧默认时限而保留用户设置、一次性迁移不损坏无关配置、保留自定义命令及无挂起能力时保留现有临界保护。受控挂起、供电切换、低电量触发与离电长时功耗另见[验证记录](validation.json)。

诊断中的电池净功率由电量计电压/电流估算，负值表示净放电，不是USB输入功率；DPMS关闭后背光驱动仍可能报告缓存的亮度值，不能单凭该值判断屏幕仍发光。已有检查中Wi-Fi省电开启，GPU和空闲音频节点支持运行时休眠；没有叠加TLP、TuneD或另一个电源档后端。
