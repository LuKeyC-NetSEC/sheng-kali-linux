# KWin 原生输入集成

匹配 `sheng / Kali ARM64 / KWin 4:6.7.4-2 / Qt 6.11.2+dfsg-5`，本地构建版本为 `4:6.7.4-2+sheng1`。保留发行版源码和补丁，不替换正在运行的合成器。固定下载与签名信息在 [native-source-pins.json](../../configs/native-source-pins.json)，本地改动散列在 [provenance.json](provenance.json)。

## 实现

- [input-method-reload.patch](input-method-reload.patch)：`/VirtualKeyboard` 增加 `configuredInputMethod`、`shengIntegrationVersion=1` 和 `restartInputMethod(expectedDesktopFile)`。不清空持久配置；异步终止旧输入面板并撤销其私有 Wayland 连接，重复重载合并；最多等待1.5秒后请求终止进程，不阻塞KWin事件循环。
- [tabboxgesture.h](tabboxgesture.h)、[tabbox-gestures.patch](tabbox-gestures.patch)：在原生TabBox中消费已有三指触摸板事件，直接打开原生选窗器、传递方向键并确认/取消。竖向意图无动作；横向开始后四向选窗，保留方向锁定、反向滞回、步进间隔和取消清理。没有第二个libinput客户端或uinput虚拟Alt。
- [input-method-tests.patch](input-method-tests.patch)：在KWin自己的隔离Wayland测试框架中检查配置保持、错误配置拒绝、TERM不退出的面板异步替换和重复请求合并。

## 构建与测试

在匹配的ARM64 Linux环境，从仓库根运行：

```bash
python3 scripts/prepare-kwin-native.py
sudo apt-get build-dep --no-install-recommends ./out/kwin-native-source
bash scripts/build-kwin-native.sh
bash scripts/test-kwin-native.sh
```

构建器不安装包，也不重启用户桌面。测试另开私有D-Bus、运行目录和配置，不能把测试环境换成正在运行的会话。实际PIN三指交互必须在用户保存应用、正常重新登录加载匹配组件后独立验收；旧桥接器不得与原生处理器同时启用。

新启动器还依赖[桌面触控插件](../desktop-touch-guard/README.md)的设备/窗口上下文v2。只有构建成功不能证明实机手势、中文或锁屏输入成功。部署前备份原KWin的所有匹配deb与相关配置；回退成组恢复原包、旧桥接器和旧输入法启动器，在下次正常登录加载。

2026-11-21在sheng ARM64构建匹配deb；随后对同一源码启用上游测试框架，在私有D-Bus/运行目录中运行 `testVirtualKeyboardDBus`：7项通过、0失败，含TERM不退出面板的重载、重复请求合并和错误启动项拒绝。新KWin已安装到磁盘；当前会话仍映射登录时的旧二进制，原生三指与输入法的新路径尚未激活和实机验收。
