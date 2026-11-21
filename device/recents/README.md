# 平板任务卡片与原生三指手势

适用于sheng / Kali ARM64 / Plasma与KWin 6.7.4 Wayland。三指切窗由 [KWin原生TabBox](../kwin-integration/README.md) 处理；原libinput/uinput桥接器、服务和udev规则已删除。

- 独立三指上下无动作；竖向意图锁定后不会因横向晃动进入Alt+Tab。
- 三指左右打开原生Alt+Tab，随后四向滑动通过原生方向键选择，松手确认。保留方向确认、反向滞回、步进间隔及取消清理，不模拟Alt按键。
- [install-native-tabbox.py](install-native-tabbox.py)复用系统 `thumbnail_grid` 的源码、作者和许可证，仅把方向键的 `keyNavigationWraps` 设为false；普通键盘Alt+Tab仍循环。
- `Meta+W`任务卡片继续使用GPU缩略图、圆角和渐变模糊。点击切换、上滑单卡关闭、全部关闭均使用应用自身的窗口关闭流程，保留保存提示。

```bash
python3 scripts/build-task-cards.py --install
python3 device/recents/install-native-tabbox.py
```

按构建器输出启用新效果ID、停用旧副本。三指手势需构建匹配的原生KWin包，不再另装后台桥接器。任务效果中旧Dock状态发布器也已删除，改由Plasma自身的原生窗口模型驱动。

原先用户确认的同向稳定选窗、任务动画/模糊属于旧部署历史。新KWin包已构建并通过独立输入接口测试；新三指和卡片组合仍待正常重新登录后的实体PIN触摸板验收。回退使用部署前自己的配置与匹配deb；不关闭当前应用或强制重启合成器。

接口依据：[KDE QML效果](https://develop.kde.org/docs/plasma/kwineffect/)、[固定KWin源码与改动](../kwin-integration/provenance.json)。上游版权与许可证保留。
