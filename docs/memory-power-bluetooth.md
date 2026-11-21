# 平板内存、电源键与蓝牙

2026-11-14 已在当前约 12GB RAM 的 sheng 平板应用，记录为本机 `out/system-tuning-verification.json`。

使用发行版 `systemd-zram-generator 1.2.1-2+b2` 创建 `/dev/zram0`，逻辑容量 6GiB、Zstd 压缩、swap 优先级 100。原有 `/swapfile` 保持 8GiB、优先级 10；分区未改动。配置源为 [zram-generator.conf](../device/zram-generator.conf)。ZRAM 按实际使用分配压缩存储，不预留 6GiB 物理内存。

`vm.swappiness` 按最新要求提高到 160，`vm.page-cluster` 保持 0。优先级决定先使用哪一个交换设备，swappiness 控制匿名内存与文件缓存的回收倾向，不是 swap 使用率目标；内存充足时低占用正常。实机对独立 32MiB 匿名映射执行页出，并确认 ZRAM 接收页面、读回 SHA-256 一致，随后释放测试映射。没有全局清空缓存、强制回收用户应用或为了提高表盘数值持续占用内存。参考 [内核内存管理参数](https://docs.kernel.org/admin-guide/sysctl/vm.html) 和 [ZRAM](https://docs.kernel.org/admin-guide/blockdev/zram.html)。

电源短按锁屏（32）、长按原生电源菜单（16）。各档位闲置1分钟锁屏息屏；AC和普通离电保持后台，只有离电10%低电量档闲置5分钟后挂起，保留5%临界保护。锁屏超时同步与恢复直接在 [PowerDevil C++](../device/power-management/README.md) 中运行，旧档位脚本和system-sleep桌面恢复钩子已移除。

持久默认仍为s2idle；此前deep受控测试进入/退出成功，但约3.511秒提前唤醒，原因未明。锁屏息屏本身不会挂起，后台继续运行；s2idle/deep是实际挂起时才使用的方式，不能把它们理解为锁屏外观或Android Doze。

蓝牙为 WCN7850，hci0 固件加载正常，已安装 BlueDevil 并启用 BlueZ 开机启动，状态栏始终显示蓝牙入口。控制中心也可切换蓝牙及打开设备列表；开关往返测试通过并恢复原状态。此前约 8 秒扫描收到 54 个不同设备地址。配对、蓝牙音频和外设输入尚未实测，未连接未知设备。界面与后端的最新记录为 `out/tablet-controls-verification.json`。

实体键盘事实由 [KWin原生设备监视器](../device/desktop-touch-guard/inputpresence.cpp) 发布，显示策略由 [Rust启动器](../device/input-method/native-policy.rs) 处理；排除触屏和虚拟设备，读取PIN实际连接状态，不记录按键。连接时禁止自动软键盘，拔下恢复AnyInput和Fcitx屏幕键盘模式；锁屏只由安全面板控制可见性。源码已构建，完整新路径仍待正常重新登录后的实体输入验收。
