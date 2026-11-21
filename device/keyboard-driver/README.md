# sheng PIN 键盘驱动修复

2026-11-21 当前安装 `sheng-dock-fix 1.3-2`，模块版本 `1.3.1-shengfix`。只适用于 `7.3.4-sm8550-00104-g87ac0f2347eb` 内核。驱动使用 `ianchb/sm8550-mainline@87ac0f2347eb433933841e6854950dd90e96e6b2`、运行内核配置和 Clang 21.1.8-13 原生编译；本轮配置差异只有未启用 BTF 时的三个 pahole 能力项。固定 archive/基线哈希见 [provenance.json](provenance.json)。

[驱动补丁](0001-fix-auth-and-resume.patch) 修改以下路径：

- 认证客户端接入、键盘连接和唤醒时主动安排握手，避免客户端启动较晚时只能等待下一次固件请求。
- 将最多 5 秒的用户态认证等待移出 IRQ 线程；等待期间中断线程继续接收数据。
- 恢复后重新安排原来的 12 秒键盘保活任务；原驱动在挂起时取消它，恢复路径没有重新安排。
- 正确取消新增认证任务，增加只读输入/认证计数，便于诊断，不记录按键内容、触摸坐标或认证材料。

第二个[热插拔补丁](0002-fix-hotplug-input-restore.patch)在它之后应用：

- 对照小米官方 `sheng-u-oss@29db5d592c5b577aa9d9611da988a5e071d100dd` 的 [nanosic_platform.c](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/29db5d592c5b577aa9d9611da988a5e071d100dd/drivers/power/supply/pogoChg/extSOC/nanosic_platform.c)，连接状态接受低两位为1或3，另用 `0x60/0x20` 区分数据链路就绪，忽略失败状态回复；链路变化不再被相同的物理连接状态吞掉。
- 首次插入立即发送原有唤醒命令，12秒仅保留为后续保活周期；认证回复提交后重新应用触摸板/指示灯/背光输入状态。认证仍由原安全存储协议与键盘固件决定，不把提交回复当作固件已接受。
- `/sys/class/misc/nanosic_auth/ready` 在固件、输入处理和 IRQ 完成后变为1并发出事件。udev 的 `SYSTEMD_READY` 与服务的 TEE/字符设备依赖保证认证自动按顺序启动，避免节点先出现、固件未就绪造成反复退出。没有增加另一个保活守护进程。

官方公开参考是 pogo 连接/充电适配，不是完整 Android PIN HID/认证框架的移植。继续保留主线 HID 与上游用户态安全存储实现。

认证还需要配套用户态服务。使用 `ianchb/sheng_devauth` 提交 `bac03b5bcfefa1467ebad490edd910a6cef8a207`，配合 [认证补丁](../keyboard-auth/service-fixes.patch)。当前 Kali 没有公共 qteesupplicant，因此服务自身必须注册上游原版使用的 RPMB 回调；只发送一个非零 token 不能证明键盘接受了认证。服务不记录 UID 或 token。

上游源码包 SHA-256：`bc48c5263c607ddf798cbc21a2aecde8e72bbbab3843aa662e99668d8722bfb4`。该源码包包含 ARM64 静态依赖及许可证，认证程序在平板本地编译，链接 `-lrpmbservice -lminkadaptor -lqcomtee -lqcbor`。

## 验证

本轮先保留故障现场：旧驱动在插回约185ms后已提交认证回复，键盘/触摸板报告计数仍不增长。第一版1.3恢复原连接后仍收到延迟反馈；后续明确拔插测试确认快速恢复，最终1.3.1用户连续两次确认很快恢复。无内容计数继续增长，KWin 两个输入设备均为 enabled。不能据此给出精确端到端延迟或长期无故障保证。

最终模块83个导入与原模块/运行内核导出匹配。设备就绪后通过udev自动启动认证，失败重试数为0；没有手动start来通过这项验收。冷启动、这版的挂起恢复、快速抖动拔插仍待独立验证，见 [validation.json](validation.json)。

热替换初期误用了会递归移除闲置依赖的 `modprobe -r`，导致 `qcom_battmgr` 一并重载，UPower 重建电池并出现0%告警。新的[增量安装器](../../scripts/install-pin-driver.py)只使用 `rmmod hid_nanosic_wn8030`，检查电池模块及电源设备的内核实例均保留。实测替换前后90%→90%，UPower无新的电池重建；没有屏蔽真实低电量告警，也未修改电池/充电驱动或MiPPS服务。

以下为此前1.2版的历史验证：

用户先后确认了保持原连接时恢复，以及自动休眠唤醒后键盘和触摸板均正常。驱动计数由零恢复增长。系统级挂起约 12.8 秒后自动唤醒，认证服务保持活动，认证计数继续增长，键盘与触摸板的事件节点保持不变；没有通过拔插或重绑定来通过恢复测试。

最终记录合并到本机 `out/keyboard-hotspot-cleanup-verification.json`，包括此前休眠、保活和用户确认结果。安装包为 `out/packages/sheng-dock-fix_1.2-2_arm64.deb`。旧报告、构建日志和测试缓存已清理；此前 83 个运行时导出符号检查通过。这是一轮实机修复验证，不承诺所有键盘固件版本或长期使用场景均已覆盖。

## 安装与回退

在同一内核的 ARM64 平板上安装包后，模块从 `/lib/modules/7.3.4-sm8550-00104-g87ac0f2347eb/kernel/drivers/hid/hid-nanosic-wn8030.ko.zst` 加载，认证服务开机自启。补丁包通过 `Replaces` 接管原文件；旧 `updates/sheng/` 副本已移除。无需重新刷写 boot 或清除用户数据。打包脚本为 [build-dock-fix-package.sh](../../scripts/build-dock-fix-package.sh)，它仍只打包编译产物。

在匹配的ARM64 Linux、Clang/LLVM 21.1.8-13和内核构建依赖环境中，从仓库根执行：

```bash
sudo python3 scripts/build-pin-driver.py
# AUTH_BINARY 需按部署手册从固定上游另行编译，许可证保留在相邻libs/LICENSE。
sudo bash scripts/build-dock-fix-package.sh out/pin-driver/module/hid-nanosic-wn8030.ko \
  /path/to/sheng-devauth "$PWD" out/packages
# 安装并在当前会话只重载PIN模块；不加--reload则等下次正常启动加载。
sudo python3 scripts/install-pin-driver.py out/packages/sheng-dock-fix_1.3-2_arm64.deb --reload
```

构建器从固定来源下载并验SHA，检查运行配置与编译器；只在 `MODVERSIONS=n` 时从运行中导出重建无CRC符号表，并要求新模块的导入不超过原匹配模块。它不加载模块、不刷写内核。构建报告在 `out/pin-driver/build-report.json`；编译器/配置/ABI不匹配直接停止，不能强制加载。增量安装器先备份模块、服务和规则到 `/var/lib/sheng-pin-installer/backup-*`，失败恢复这些文件并尝试恢复PIN；备份包版本信息与文件回退需一起核对。

按用户要求，平板只保留补丁版模块，原版备份和试验认证程序已删除。卸载补丁不会自动恢复原版；如需回退，必须重新安装原内核包。原模块仍有先前的间歇失灵问题。

```sh
sudo apt remove sheng-dock-fix
sudo apt install --reinstall linux-xiaomi-sheng
sudo reboot
```

若需不停机回退，应先停止认证服务，再用 `rmmod hid_nanosic_wn8030` 只卸载PIN，保留 `qcom_battmgr`，重新安装原内核包后加载原模块。不要使用会连带移除依赖的 `modprobe -r`，也不要在认证客户端持有字符设备时直接重绑定控制器。

新模块的编译需要精确匹配的内核源码、配置和工具链。本次使用 `make LLVM=-21 olddefconfig` 与 `prepare modules_prepare` 准备源码树，在独立模块目录编译。该内核 `CONFIG_MODVERSIONS=n`，从运行中内核的 `__ksymtab_*` 列表取得导出符号及所属模块，生成不使用 CRC 的符号表；最终 83 个依赖全部匹配，构建不再有未解析符号警告。没有强制加载不匹配 ABI 的模块。

旧的重绑定休眠脚本已停用；最终方案由驱动自身恢复保活与认证。此前导出的 rootfs/boot 镜像尚未重新打包此修复，重新安装旧镜像需另行安装该包。更换内核后需要重新编译，不能把此模块用于另一内核版本。
