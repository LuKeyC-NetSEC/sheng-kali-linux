# 蓝牙耳机与 LDAC

2026-11-21，sheng / Kali ARM64：BlueZ 5.87、PipeWire 1.6.9、WirePlumber 0.5.18。
本机 Sony **WF-1000XM6** 已配对连接，PipeWire实际音频节点为
`api.bluez5.codec=ldac`、`api.bluez5.profile=a2dp-sink`，用户确认耳机正常出声。
去敏版本与验收范围见 [validation.json](validation.json)。

## 配对与音频输出

按 [Sony XM6 官方指南](https://helpguide.sony.net/mdr/2985/v1/en/contents/F032_Pairing_and_connecting_with_a_Bluetooth_device.html)：
将两只耳机放入盒内，保持盒盖打开，按住盒背配对按钮约5秒，确认蓝灯连续双闪。
配对模式5分钟后会自动取消。实际以设备显示的型号/名称为准；排查时可先让其他设备断开这副耳机。

配对成功后，系统的默认输出和已经运行的应用音频流仍可能留在原来的扬声器上。
在系统设置的声音页面选择耳机作为默认输出，并检查正在播放的应用是否也使用耳机。
本次切换默认输出并迁移已有流，保留耳机40%音量；最终确认实际应用流在耳机，
扬声器内部虚拟滤波流仍在其原输出。后续诊断应区分应用流和内部虚拟滤波流。
没有修改蓝牙固件/驱动或删除配对记录；本次未确立最初未发现设备的唯一原因。

## 核对实际编码

LDAC在经典蓝牙A2DP下协商；LE Audio使用LC3，见
[Sony支持的编码](https://helpguide.sony.net/mdr/2985/v1/en/contents/F055_Supported_codecs.html)。
按官方说明，LDAC对应Sound Connect的音质优先设置。插件已安装只能证明本机具备支持条件，
还需读取实际音频节点的编码。本机的Pulse兼容层profile显示为通用 `a2dp-sink`，
编码信息在PipeWire节点属性中。

```bash
pw-dump | python3 -c '
import json, sys
for obj in json.load(sys.stdin):
    p = obj.get("info", {}).get("props", {})
    if p.get("media.class") == "Audio/Sink" and p.get("api.bluez5.codec"):
        print(json.dumps({k: p.get(k) for k in (
            "node.description", "api.bluez5.codec", "api.bluez5.profile"
        )}, ensure_ascii=False))
'
```

命令检查与用户听到声音分别记录。LDAC码率、耳机麦克风/HFP、LE Audio、重新连接或重启后的
默认路由与长期稳定性均未验证；本次不宣称固定990kbps。设备地址、配对密钥、附近设备清单、
音频内容和完整PipeWire转储均不随仓库发布。
