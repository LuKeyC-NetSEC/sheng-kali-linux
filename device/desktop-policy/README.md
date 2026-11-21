# 原生桌面策略与隐私部署包

Dock、物理输入设备状态和桌面入口已迁到 [Plasma Shell C++](../plasma-integration/README.md) 与 [KWin触控插件](../desktop-touch-guard/README.md)。旧Python桌面策略、用户服务、QML桌面手势部件及三指桥接器的源码和打包分支已删除。

`sheng-tablet-controls 1.0-7+native1` 只部署隐私后端、一次性桌面配置工具和指向原生plasmashell的D-Bus激活入口。它严格依赖匹配的原生KWin/Plasma包，与旧 `sheng-task-gestures` 包冲突；安装时停用旧桥接器和旧桌面策略。不会另外启动桌面策略守护进程。隐私访问隔离仍由独立的最小权限系统组件负责，见 [privacy](../privacy/README.md)。

```bash
bash scripts/build-desktop-touch-guard.sh
mkdir -p out/bin out/packages
gcc -std=gnu11 -O2 -Wall -Wextra -Werror device/privacy/device-guard.c -o out/bin/sheng-privacy-bpf
python3 device/desktop-policy/build-device-package.py out/bin/sheng-privacy-bpf out/packages/sheng-tablet-controls_1.0-7+native1_arm64.deb --touch-guard-build out/build-desktop-touch-guard
```

构建不部署。KWin、Plasma、上下文插件与输入法须成组安排维护，在用户保存应用后正常重新登录加载。不能在旧组件仍承担当前锁屏输入时提前清理运行链路。当前实机既有交互确认属于迁移前版本；新路径的UI与输入仍需重新验收。配置备份保存在设备私有状态目录，不上传用户配置。
