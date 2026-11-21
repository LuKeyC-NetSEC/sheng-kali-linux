# MiPPS 120W 充电：静态审查与离线适配

2026-11-21，目标为 sheng / Kali ARM64 / 内核 `7.3.4-sm8550-00104-g87ac0f2347eb`。本次**未连接平板、未写 sysfs、未安装服务、未更换内核、未测充电功率**。当前设备没电充电中，所有修改限于电脑上的源代码与模拟测试。

## 无法进入官方快充的首要嫌疑

仓库 [build-kali.sh](../../scripts/build-kali.sh) 没有安装 `xiaomi-mipps-auth`、对应 systemd 单元或 udev 触发规则；历史镜像的本地 `packages.tsv` 中也没有它。以上只能确认构建/历史镜像缺项，不能证明设备此刻的服务状态。

固定内核的配置已启用 `CONFIG_BATTERY_QCOM_BATTMGR=m`、`CONFIG_QCOM_PMIC_GLINK=y`、`CONFIG_UCSI_PMIC_GLINK=y`。sheng DTS 使用 `xiaomi,sm8550-pmic-glink`，`qcom_battmgr.c` 提供 `xiaomi/` 属性组，包括双电量计认证、适配器 UVDM 命令和认证状态。内核的 enable worker 请求通知，未主动执行整个 MiPPS 用户态认证流程。因而优先补查认证服务，而非直接替换整套充电驱动。

原项目 [ianchb/xiaomi-mipps-auth](https://github.com/ianchb/xiaomi-mipps-auth) 专门支持 sheng；其完整源码仅在准备时从固定提交下载，认证常量不复制进本仓库。不能把 PIN 键盘的 `sheng-devauth` 当作充电器认证服务。

## 小米官方对照

优先参考 [MiCode 官方 sheng-u-oss 充电驱动](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/29db5d592c5b577aa9d9611da988a5e071d100dd/drivers/power/supply/qti_battery_charger.c)。提交与下载 SHA-256 见 [provenance.json](provenance.json)。

1. `enum uvdm_state` 是最近命令的状态编号；6/7/8 不能单独证明认证成功，另有 `pd_verifed`、`authentic`、`slave_authentic` 布尔结果。
2. `usbpd_request_vdm_cmd` 对种子、认证、反向认证按四个 32 位字转换；现有主线 `qcom_battmgr_xiaomi_parse_vdm_payload` 已对应处理，不在用户态再交换一次。命令6/7使用32位结果，命令4/5/8使用128位数据，保留该 ABI。
3. 官方 `fastchg_mode`、`power_max` 是固件上报的只读属性，后者不能冒充实测输入功率。保留普通 PD 与 PD_PPS 的区分。
4. 官方公开版本是 Android U，**与当前主线适配的属性编号不同**：`VDM_CHARGER_VERSION` 为 `0x09` 对 `0x0d`，`PD_VERIFED` 为 `0x14` 对 `0x18`。没有当前固件协议验证前，不将旧编号硬套到新系统，也不改动电流、电压、温控和保护阈值。

官方内核公开了传输和属性接口，不等同于公开了完整 Android 用户态认证/温控策略。本次保持上游已有认证算法，只调整能够证明的 Linux 集成与状态处理问题；没有据此声称复现官方整条充电策略。

## 已确认的问题与调整

| 缺陷 | 离线修改 | 验证范围 |
| --- | --- | --- |
| `request_vdm_cmd`、随机挑战、预期摘要/设备响应可能进入 journal | 移除相关日志；超时只记录命令编号，未复制上游认证常量 | 敏感样本捕获测试；不采集真实材料 |
| 双电量计最多10轮、每轮至少1.6秒，总计可超过服务20秒超时 | 服务超时120秒，失败重试5秒、300秒最多3次，支持 SIGTERM 失败清理 | 配置与模拟时序；不保证硬件最坏延迟 |
| 握手等待/最终回写期间未核对当前连接 | 会话开始记录 Type-C 连接标识，等待和写入前核对 USB online/标识；发生变化终止 | 模拟拔插；独立 sysfs 操作之间仍非原子，若固件没有可靠连接标识则保障受限 |
| 仅用状态6/7跳过认证，可能把失败结果当完成 | 最终状态7还必须同时确认 PD 结果与两侧电量计结果；未通过不能当完成 | 模拟真假状态组合 |
| 反向认证超时被吞掉后仍发布成功 | 传播失败，不回写最终成功标志；成功回写后再读固件结果 | 模拟超时/失败 |
| 响应/适配器 ID 被截断，接受多余数据 | 固定长度十六进制校验；摘要用 `hmac.compare_digest` | 畸形/截断/超长样本 |
| systemd 启动失败前已写 online 标记，抑制后续重试 | 启动请求成功后才更新标记；异常/终止清理标记 | 模拟调度失败和终止 |
| PD/未知快充状态可能被当作 PPS/MiPPS，通知将最大功率写成当前功率 | 按真实类型及认证/快充状态分类；通知明确为固件报告上限、非实测功率 | 模拟状态与通知文本 |

此次适配没有增加未经官方证实的 `verify_process` 写入顺序，也没有给 `pps_ptf`、`fg_fastcharge`、充电限流或温控节点强写常量。此类改变需要明确的固件行为和独立实机证据。

上述14项离线测试全部通过；认证摘要只用人工构造的测试材料。官方公开源码中也存在未限制 `%s` 长度、部分传输函数不向调用者传播错误的旧实现，这些没有原样移入现有主线代码；现有主线的定长解析和错误返回继续保留。尚未修改/重新构建内核模块。

当前内核还存在一条 `dev_dbg` 打印认证摘要响应的路径，默认调试状态不代表它一定输出。[可选内核脱敏补丁](qcom-battmgr-no-auth-logs.patch)仅删除该打印，不改认证数据或收发逻辑；固定基线/补丁SHA见 provenance。补丁仅完成应用校验，未编译或安装；如后续决定更新内核，仍需完整匹配构建并重建 PIN 模块，不为去日志而强制加载不匹配的 `qcom_battmgr`。

## 准备、测试与后续部署边界

Windows 或 Linux、Python3 和 Git，仅准备源码：

```bash
python3 scripts/prepare-mipps-auth.py
python3 -m unittest discover -s tests -p test_mipps_auth.py -v
```

输出 `out/mipps-source`，下载固定 archive 并验证补丁和基础文件 SHA；重复准备请用新的 `--output-dir`。允许用 `--archive /path/to/cache.tar.gz` 提供缓存，仍强制校验；其他开发者不需要作者 `.work/`。源码使用 GPL-2.0-only，保留上游 SPDX 和作者信息；[mipps-hardening.patch](mipps-hardening.patch) 是本项目改动，没有向上游提交 PR。

**不要现在在充电设备上执行下载脚本或安装此实验版本。** 设备电量恢复后先只读检查 `xiaomi/` 节点、服务存在性、PD 类型、电压/电流、温度和认证布尔结果，再决定安装。禁止将认证状态手工改成1冒充通过，也不记录 `verify_digest`、VDM 认证响应、挑战或设备认证材料。

如后续授权部署，在匹配内核的 ARM64 Linux 中使用准备后的 `build-deb.sh` 打包，审阅并备份现有 service/udev 文件后安装；当前不自动接入基础镜像。USB 数据角色切换可能影响 USB 网络，部署前应安排恢复通道。回退恢复原服务/规则，或卸载增量包，保留固件自己的基础充电路径；不通过反复重绑 PMIC/ADSP 解决问题。

## 未验证

设备现时安装状态、原装适配器/线材识别、实际 MiPPS 握手、低电量阶段、两侧电量计响应时间、持续功率、温控、离线关机充电及休眠恢复均未验证。模拟测试不能证明达到120W，也不证明当前固件的私有属性编号正确。
