# Mesa 上游稳定版同步

仅面向 Xiaomi Pad 6S Pro 12.4 (`sheng`) / Kali ARM64 / 主线 DRM/MSM。
固定 Mesa **26.3.1**（2026-11-18），来源、官方 SHA-256、Kali 签名打包源码见
[provenance.json](provenance.json)。本增量不更换内核、固件、libdrm 或 PIN 模块。

## 构建范围

同一次构建生成 EGL、GLX、GBM、Gallium、DRI 和 Vulkan 配套包，使用 Debian 原包名、
依赖约束、符号清单和版权文件。保留发行版 `path_max.diff`；GLX 头文件补丁仅因
`driDestroyConfigs` 上游移出该头文件而重定位上下文，typedef 内容不变。

实机首次上游测试发现 LLVM 21 的 ARM64 JIT 生成了当前系统未启用的 SVE2 指令，
导致三个 llvmpipe 测试 SIGILL。新增小补丁在构造 LLVM 特性参数前明确禁用未检出的
SVE/RNG，参照 [LLVM 22.1.8 的上游修正](https://github.com/llvm/llvm-project/blob/llvmorg-22.1.8/llvm/lib/TargetParser/Host.cpp)。
仅影响 Linux ARM64 + LLVM 21 的软件 JIT，不改变 Freedreno/Turnip 的 GPU 指令生成。
失败日志保留本地，修复后重跑完整测试，不跳过这些测试。

此机型配置编译 Freedreno OpenGL、Turnip Vulkan、Zink，以及 llvmpipe/softpipe/Lavapipe
软件回退；不构建其他 GPU 驱动、VA/VDPAU、OpenCL/Rusticl、Teflon 或 Android KGSL。
这不是通用 ARM64 Mesa 发行包，也不用于外接其他厂商 GPU。桌面和 Burp 保持直接 OpenGL，
不设置全局 Zink 或 Vulkan 环境变量。

## 从源码构建

在 ARM64 Linux 仓库根目录执行，Python ≥3.12。Windows 仅负责传输，不能编译 Linux ELF。

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends build-essential dpkg-dev debhelper \
  fakeroot gpgv debian-keyring patch python3 ca-certificates
python3 scripts/prepare-mesa-upstream.py
sudo apt-get build-dep --no-install-recommends ./out/mesa-upstream-source
JOBS=4 bash scripts/build-mesa-upstream.sh
```

准备器验证官方 tarball 的固定 SHA-256、发行版 `.dsc` 和打包归档 SHA-256，
使用 Debian keyring 验证 `.dsc` 签名；逐一零 fuzz 检查后应用两处发行版补丁和 JIT 修复。
Meson 的发行版包装器禁用自动下载子项目；缺依赖时应补发行版开发包。
保留编译树、配置和日志，未改源码的中断构建可用 `RESUME=1` 继续。
构建器运行上游测试，任何失败都会阻止打包，不沿用发行版忽略测试失败的规则。

产物在 `out/`，包括 `26.3.1-1+sheng1` 的八个包：`libgbm1`、`libgbm-dev`、
`libegl-mesa0`、`libglx-mesa0`、`libgl1-mesa-dri`、`mesa-common-dev`、
`mesa-libgallium`、`mesa-vulkan-drivers`。自动生成的调试包不属于安装集合。

## 隔离验证与安装

在目标设备以普通用户测试。先确保内核和旧会话正常、磁盘及电量足够，保存重要工作。
不执行完整性能基准，也不固定 GPU 频率。

```bash
sudo apt-get install --no-install-recommends libegl-dev libepoxy-dev libvulkan-dev \
  glslang-tools mesa-utils vulkan-tools dpkg-repack
python3 scripts/test-mesa-upstream.py --package-dir out
sudo python3 scripts/install-mesa-upstream.py out
# 安装后，验证新的独立进程确实加载新驱动
python3 scripts/test-mesa-upstream.py --output-dir out/mesa-smoke-installed
```

测试器自行解包完整包集到 `out/smoke-stage/stage`，只向测试子进程传入 EGL/DRI/Vulkan
库路径；分别运行 Freedreno、Turnip、Zink 的短暂离屏绘制，比较 3048×2032 RGBA8
读回 SHA-256，核对两种 API 实际版本。诊断 UUID 等完整信息只存本地，公开报告仅含驱动信息。
安装器要求同一包集 SHA-256 对应的成功隔离报告，备份原已安装的包后一次 APT 事务安装，
禁止卸载其他包；未安装的开发包不额外安装。

安装器不重启 KWin、Plasma、锁屏或应用。已经运行的进程仍可能映射旧驱动；
桌面合成器需要用户正常注销、重新登录后加载新版。不能将独立进程通过等同于桌面视觉验收。
基础镜像仍采用 Kali 源提供的 Mesa，此源码增量需单独构建。

## 回退

原包和清单保存在安装器打印的 `/var/lib/sheng-mesa-backup/<UTC时间>/`。
使用本次真实备份路径，在目标设备恢复整套原包：

```bash
sudo apt-get --allow-downgrades --no-remove install /var/lib/sheng-mesa-backup/<本次备份>/*.deb
```

之后正常重新登录。不要删除唯一驱动、混用 Gallium 内部库、强退合成器或从其他 ABI 复制库。
后续 Kali 提供更高版本时可按正常 APT 更新，不设置永久 hold。

## 验收边界

本次实机结果见 [validation.json](validation.json) 与[公开验证矩阵](../../docs/VALIDATION.md)。
短暂离屏读回不证明性能、耗电或长期稳定性改善；锁屏/解锁、横竖屏、挂起恢复、Firefox、
Burp 和重新登录后的桌面显示需分别验收。测试前后记录 GPU governor 与频率范围；
本测试器没有写入这些参数。

上游：[发布说明](https://docs.mesa3d.org/relnotes/26.3.1.html)、
[安装与隔离测试](https://docs.mesa3d.org/install.html)、
[Freedreno/Turnip](https://docs.mesa3d.org/drivers/freedreno.html)。
保留 Mesa 各文件及 Debian 打包版权，参见[第三方来源](../../THIRD_PARTY.md)。
