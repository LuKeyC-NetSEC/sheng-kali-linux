# 桌面原生防误入编辑

sheng / Plasma 6.7.4 / Qt 6.11.2 / ARM64。轻点、停留和触屏滑动不应自动进入桌面编辑；用户明确选择“编辑桌面”后仍可编辑。应用抽屉的图标长按编辑不受影响。

已阅读匹配的Plasma源码：桌面 `main.qml` 的布局与部件容器均默认使用 `AfterPressAndHold`；后者还会接收Qt合成的鼠标长按。只修复TouchCancel不能覆盖两条入口。

[policy.cpp](policy.cpp)作为C++ applet运行在现有plasmashell中，使用原桌面已声明的 `appletsLayout` 接口及直属容器。正常状态设为 `Manual`，明确进入全局编辑后恢复编辑条件；不把桌面设为不可变，不递归扫描其他部件，不注册全局触摸处理器。首次部署清理已误入的编辑状态，后续升级保留手动编辑状态。

它监听Corona、桌面UI就绪及布局子项变化，没有轮询、额外守护进程或常驻Python策略。极小的声明式宿主只负责装载原生插件，代码在Plasma进程执行。公开状态接口仅返回模式和管理对象数量，不返回输入或窗口内容。

```bash
bash scripts/build-desktop-edit-policy.sh
python3 scripts/package-desktop-edit-policy.py out/build-desktop-edit-policy out/packages/sheng-desktop-edit-policy_1.0-1_arm64.deb
sudo apt-get install ./out/packages/sheng-desktop-edit-policy_1.0-1_arm64.deb
# 安装器会以桌面用户执行一次配置；手动部署时可单独执行：
python3 scripts/install-desktop-edit-policy.py
qdbus6 org.sheng.DesktopEditPolicy /org/sheng/DesktopEditPolicy org.sheng.DesktopEditPolicy.GetStatus
```

构建器编译本组件，打包器仅打包已经构建的ELF。安装保存桌面配置并通过标准Applet模型加载新ID，无需重启KWin或会话；不同源码使用不同插件ID，避免Qt工厂缓存。

2026-11-21已原生编译、打包安装，管理1个布局/3个直属容器，正常状态条件为Manual；KWin/Plasma进程保持不变。用户确认“触屏不再误入、手动编辑正常”。新组件还需长期使用及冷登录验收。配置私有备份在用户的 `.local/state/sheng-desktop-edit-policy/`；回退先移除该策略部件，再于下次正常登录恢复标准桌面条件。源码GPL-3.0-or-later，依赖的KDE版权保留。
