#!/bin/bash
# Build a native ARM64 Kali KDE image for Xiaomi Pad 6S Pro (sheng).
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export LC_ALL=C.UTF-8 LANG=C.UTF-8
PROJECT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
BUILD_DIR=${BUILD_DIR:-"$PROJECT/.work/build"}
ASSET_DIR=${ASSET_DIR:-"$PROJECT/.work/assets"}
OUT_DIR=${OUT_DIR:-"$PROJECT/out"}
IMAGE_SIZE=${IMAGE_SIZE:-16G}
KALI_MIRROR=${KALI_MIRROR:-https://kali.download/kali}
KALI_PASSWORD=${KALI_PASSWORD:-kali}
RESUME=${RESUME:-0}
ROOTFS="$BUILD_DIR/rootfs"
if (( EUID != 0 )); then echo 'Run this script as root on Linux.' >&2; exit 1; fi
for tool in debootstrap img2simg mkfs.ext4 e2fsck python3 curl; do
    command -v "$tool" >/dev/null || { echo "Missing build dependency: $tool" >&2; exit 1; }
done
QEMU=$(command -v qemu-aarch64-static || command -v qemu-aarch64)
if [[ -e "$BUILD_DIR/rootfs.img" && "$RESUME" != 1 ]]; then
    echo "Build directory already contains rootfs.img; use a new BUILD_DIR." >&2
    exit 1
fi
mkdir -p "$BUILD_DIR" "$ROOTFS" "$ASSET_DIR" "$OUT_DIR"
cleanup() {
    for target in dev/pts dev proc sys ''; do
        if mountpoint -q "$ROOTFS${target:+/$target}"; then
            umount "$ROOTFS${target:+/$target}" || true
        fi
    done
}
trap cleanup EXIT
python3 "$PROJECT/scripts/fetch-assets.py" "$ASSET_DIR"
KEYRING=/usr/share/keyrings/kali-archive-keyring.gpg
if [[ ! -s "$KEYRING" ]]; then
    KEYRING="$ASSET_DIR/kali-archive-keyring.gpg"
    curl --fail --location --retry 3 https://archive.kali.org/archive-keyring.gpg -o "$KEYRING"
fi
gpg --show-keys --with-colons "$KEYRING" | grep -q 827C8569F2518CC677FECA1AED65462EC8D5E4C5
if [[ -e "$BUILD_DIR/rootfs.img" ]]; then
    mount -o loop "$BUILD_DIR/rootfs.img" "$ROOTFS"
    # Resume only an already configured Kali ARM64 base, never another image.
    chroot "$ROOTFS" /bin/bash -ec '
        . /etc/os-release
        test "$ID" = kali
        test "$(dpkg --print-architecture)" = arm64
        test "$(dpkg-query -W -f="\${Status}" bash)" = "install ok installed"
    '
else
    truncate -s "$IMAGE_SIZE" "$BUILD_DIR/rootfs.img"
    # Conservative ext4 features also allow inspection from older recovery images.
    mkfs.ext4 -F -L kali-sheng -O '^metadata_csum_seed,^orphan_file' "$BUILD_DIR/rootfs.img"
    mount -o loop "$BUILD_DIR/rootfs.img" "$ROOTFS"
    [[ -f /usr/share/debootstrap/scripts/kali-rolling ]] || \
        ln -s sid /usr/share/debootstrap/scripts/kali-rolling
    debootstrap --foreign --arch=arm64 --keyring="$KEYRING" \
        --components=main,contrib,non-free,non-free-firmware \
        kali-rolling "$ROOTFS" "$KALI_MIRROR"
    install -m 0755 "$QEMU" "$ROOTFS/usr/bin/qemu-aarch64-static"
    chroot "$ROOTFS" /debootstrap/debootstrap --second-stage
fi
mount --bind /dev "$ROOTFS/dev"
mount -t devpts devpts "$ROOTFS/dev/pts"
mount -t proc proc "$ROOTFS/proc"
mount -t sysfs sysfs "$ROOTFS/sys"
rm -f "$ROOTFS/etc/resolv.conf"
cp -L /etc/resolv.conf "$ROOTFS/etc/resolv.conf"
install -Dm 0644 "$KEYRING" "$ROOTFS/usr/share/keyrings/kali-archive-keyring.gpg"
printf 'deb [signed-by=/usr/share/keyrings/kali-archive-keyring.gpg] %s kali-rolling main contrib non-free non-free-firmware\n' \
    "$KALI_MIRROR" > "$ROOTFS/etc/apt/sources.list"
printf '#!/bin/sh\nexit 101\n' > "$ROOTFS/usr/sbin/policy-rc.d"
chmod 0755 "$ROOTFS/usr/sbin/policy-rc.d"
chroot "$ROOTFS" apt-get update
chroot "$ROOTFS" apt-get install -y --no-install-recommends \
    kali-archive-keyring kali-defaults kali-desktop-kde kali-tools-top10 \
    systemd-sysv sudo locales tzdata ca-certificates openssh-server \
    network-manager plasma-nm bluedevil wpasupplicant wireless-regdb iw \
    sddm plasma-keyboard qt6-virtualkeyboard-plugin konsole dolphin \
    pipewire-audio pulseaudio-utils playerctl brightnessctl brightness-udev wl-clipboard libgl1-mesa-dri mesa-vulkan-drivers xserver-xorg-input-libinput \
    fonts-noto-core fonts-noto-ui-core fonts-noto-cjk fonts-noto-color-emoji fonts-liberation fontconfig firefox-esr \
    dbus-user-session python3-dbus python3-gi polkitd rfkill usbutils pciutils dnsmasq-base \
    e2fsprogs kmod qrtr-tools rmtfs tqftpserv bluez libkscreen-bin \
    systemd-timesyncd systemd-zram-generator util-linux-extra build-essential meson ninja-build pkg-config \
    libglib2.0-dev libprotobuf-c-dev libqmi-glib-dev libmbim-glib-dev \
    protobuf-compiler protobuf-c-compiler cmake extra-cmake-modules qt6-base-dev \
    libkf6coreaddons-dev libksysguard-dev libsensors-dev upower mesa-utils vulkan-tools \
    alsa-utils alsa-ucm-conf rtkit powerdevil plasma-pa hostapd kdialog
install -Dm 0644 "$PROJECT/device/theme/fonts/31-sheng-material-icons-charset.conf" \
    "$ROOTFS/etc/fonts/conf.d/31-sheng-material-icons-charset.conf"
chroot "$ROOTFS" fc-cache -f
chroot "$ROOTFS" update-alternatives --set regulatory.db /lib/firmware/regulatory.db-upstream
mkdir -p "$ROOTFS/tmp/sheng-libssc-source" "$ROOTFS/tmp/sheng-packages" "$OUT_DIR/packages"
tar -xzf "$ASSET_DIR/libssc.tar.gz" --strip-components=1 -C "$ROOTFS/tmp/sheng-libssc-source"
install -m 0755 "$PROJECT/scripts/build-libssc.sh" "$ROOTFS/tmp/build-libssc.sh"
chroot "$ROOTFS" /bin/bash /tmp/build-libssc.sh /tmp/sheng-libssc-source /tmp/sheng-packages
cp "$ROOTFS/tmp/sheng-packages/libssc_0.4.4-1_arm64.deb" "$OUT_DIR/packages/"
install -m 0644 "$ASSET_DIR/xiaomi-sheng-thp_0.3.9_arm64.deb" "$ROOTFS/tmp/sheng-packages/"
cp "$ASSET_DIR/xiaomi-sheng-thp_0.3.9_arm64.deb" "$OUT_DIR/packages/"
chroot "$ROOTFS" apt-get install -y /tmp/sheng-packages/libssc_0.4.4-1_arm64.deb /tmp/sheng-packages/xiaomi-sheng-thp_0.3.9_arm64.deb
mkdir -p "$ROOTFS/tmp/sheng-gpu-source/scripts" "$ROOTFS/tmp/sheng-gpu-source/device"
cp -a "$PROJECT/device/gpu-monitor" "$ROOTFS/tmp/sheng-gpu-source/device/"
cp "$PROJECT/scripts/build-gpu-monitor.sh" "$PROJECT/scripts/collect-gpu.py" "$ROOTFS/tmp/sheng-gpu-source/scripts/"
cp "$PROJECT/LICENSE" "$ROOTFS/tmp/sheng-gpu-source/"
chroot "$ROOTFS" /bin/bash /tmp/sheng-gpu-source/scripts/build-gpu-monitor.sh /tmp/sheng-packages
cp "$ROOTFS/tmp/sheng-packages/sheng-gpu-monitor_1.0.0_arm64.deb" "$OUT_DIR/packages/"
chroot "$ROOTFS" apt-get install -y /tmp/sheng-packages/sheng-gpu-monitor_1.0.0_arm64.deb
install -m 0644 "$ASSET_DIR/linux-xiaomi-sheng.deb" "$ROOTFS/tmp/kernel.deb"
chroot "$ROOTFS" apt-get install -y /tmp/kernel.deb
mkdir -p "$BUILD_DIR/firmware" "$BUILD_DIR/adaptation" "$ROOTFS/usr/lib/firmware"
tar -xzf "$ASSET_DIR/firmware.tar.gz" --strip-components=1 -C "$BUILD_DIR/firmware"
tar -xzf "$ASSET_DIR/adaptation.tar.gz" --strip-components=1 -C "$BUILD_DIR/adaptation"
cp -a "$BUILD_DIR/firmware/." "$ROOTFS/usr/lib/firmware/"
cp -a "$BUILD_DIR/adaptation/alsa-xiaomi-sheng/usr/." "$ROOTFS/usr/"
for dir in "$ROOTFS/usr/lib/modules/"*; do
    chroot "$ROOTFS" depmod "${dir##*/}"
done
printf 'kali-sheng\n' > "$ROOTFS/etc/hostname"
printf '127.0.0.1 localhost\n127.0.1.1 kali-sheng\n::1 localhost ip6-localhost ip6-loopback\n' > "$ROOTFS/etc/hosts"
printf 'PARTLABEL=userdata / ext4 defaults,noatime 0 1\n' > "$ROOTFS/etc/fstab"
printf 'en_US.UTF-8 UTF-8\nzh_CN.UTF-8 UTF-8\n' > "$ROOTFS/etc/locale.gen"
chroot "$ROOTFS" locale-gen
printf 'LANG=zh_CN.UTF-8\n' > "$ROOTFS/etc/default/locale"
chroot "$ROOTFS" ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
printf 'Asia/Shanghai\n' > "$ROOTFS/etc/timezone"
if ! chroot "$ROOTFS" id kali >/dev/null 2>&1; then
    chroot "$ROOTFS" useradd -m -s /bin/bash -G sudo,adm,audio,video,plugdev,netdev kali
fi
printf 'kali:%s\n' "$KALI_PASSWORD" | chroot "$ROOTFS" chpasswd
chroot "$ROOTFS" passwd -l root
install -d "$ROOTFS/etc/sddm.conf.d" "$ROOTFS/home/kali/.config"
if [[ -f "$ROOTFS/usr/share/wayland-sessions/plasma.desktop" ]]; then
    SESSION=plasma.desktop
elif [[ -f "$ROOTFS/usr/share/wayland-sessions/plasmawayland.desktop" ]]; then
    SESSION=plasmawayland.desktop
else
    echo 'Plasma Wayland session was not installed.' >&2
    exit 1
fi
printf '[Autologin]\nUser=kali\nSession=%s\nRelogin=false\n' "$SESSION" > "$ROOTFS/etc/sddm.conf.d/10-kali-sheng.conf"
cat > "$ROOTFS/home/kali/.config/kwinrc" <<'EOF'
[Wayland]
InputMethod=/usr/share/applications/org.kde.plasma.keyboard.desktop
VirtualKeyboardEnabled=true
[Xwayland]
Scale=2
EOF
chroot "$ROOTFS" chown -R kali:kali /home/kali
install -Dm 0755 "$PROJECT/scripts/set-screen-lock-timeout.sh" "$ROOTFS/usr/libexec/sheng-set-screen-lock-timeout"
install -m 0755 "$PROJECT/scripts/configure-power-buttons.sh" "$ROOTFS/tmp/configure-power-buttons.sh"
chroot "$ROOTFS" runuser -u kali -- /bin/bash /tmp/configure-power-buttons.sh --config-only
install -Dm 0644 "$PROJECT/device/50-sheng-logind.conf" "$ROOTFS/etc/systemd/logind.conf.d/50-sheng.conf"
install -Dm 0644 "$PROJECT/device/50-sheng-sleep.conf" "$ROOTFS/etc/systemd/sleep.conf.d/50-sheng.conf"
install -Dm 0644 "$PROJECT/device/20-sheng-sddm-display.conf" "$ROOTFS/etc/sddm.conf.d/20-sheng-display.conf"
install -Dm 0755 "$PROJECT/scripts/resume-desktop.py" "$ROOTFS/usr/libexec/sheng-desktop-resume.py"
install -Dm 0755 "$PROJECT/scripts/keyboard-policy.py" "$ROOTFS/usr/libexec/sheng-keyboard-policy.py"
install -Dm 0644 "$PROJECT/device/sheng-keyboard-policy.service" "$ROOTFS/usr/lib/systemd/user/sheng-keyboard-policy.service"
install -d "$ROOTFS/home/kali/.config/systemd/user/graphical-session.target.wants"
ln -sf /usr/lib/systemd/user/sheng-keyboard-policy.service "$ROOTFS/home/kali/.config/systemd/user/graphical-session.target.wants/sheng-keyboard-policy.service"
chroot "$ROOTFS" chown -R kali:kali /home/kali/.config/systemd
install -Dm 0755 "$PROJECT/device/sheng-desktop-sleep" "$ROOTFS/usr/lib/systemd/system-sleep/60-sheng-desktop"
install -Dm 0755 "$PROJECT/scripts/sheng-hotspot.py" "$ROOTFS/usr/libexec/sheng-hotspot/hotspot.py"
install -Dm 0755 "$PROJECT/scripts/setup-hotspot.py" "$ROOTFS/usr/libexec/sheng-hotspot/setup.py"
install -Dm 0755 "$PROJECT/scripts/hotspot-toggle.sh" "$ROOTFS/usr/local/bin/sheng-hotspot-toggle"
install -Dm 0644 "$PROJECT/device/sheng-hotspot.service" "$ROOTFS/etc/systemd/system/sheng-hotspot.service"
install -Dm 0644 "$PROJECT/device/sheng-hotspot-setup.service" "$ROOTFS/etc/systemd/system/sheng-hotspot-setup.service"
install -Dm 0644 "$PROJECT/device/50-sheng-hotspot.rules" "$ROOTFS/etc/polkit-1/rules.d/50-sheng-hotspot.rules"
install -Dm 0644 "$PROJECT/device/81-sheng-hotspot.rules" "$ROOTFS/etc/udev/rules.d/81-sheng-hotspot.rules"
install -Dm 0644 "$PROJECT/device/sheng-hotspot.desktop" "$ROOTFS/usr/share/applications/sheng-hotspot.desktop"
install -Dm 0755 "$PROJECT/device/sheng-hotspot-sleep" "$ROOTFS/usr/lib/systemd/system-sleep/50-sheng-hotspot"
install -d "$ROOTFS/etc/modules-load.d"
printf 'qcom_pd_mapper\nuinput\n' > "$ROOTFS/etc/modules-load.d/sheng.conf"
install -Dm 0755 "$PROJECT/scripts/sheng-usb-network.sh" "$ROOTFS/usr/local/sbin/sheng-usb-network"
install -Dm 0755 "$PROJECT/scripts/setup-swap.sh" "$ROOTFS/usr/local/sbin/sheng-setup-swap"
install -Dm 0644 "$PROJECT/device/sheng-swap.service" "$ROOTFS/etc/systemd/system/sheng-swap.service"
install -Dm 0644 "$PROJECT/device/zram-generator.conf" "$ROOTFS/etc/systemd/zram-generator.conf"
cat > "$ROOTFS/etc/systemd/system/sheng-usb-network.service" <<'EOF'
[Unit]
Description=USB RNDIS network for sheng
After=systemd-udevd.service NetworkManager.service
Wants=NetworkManager.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/sheng-usb-network
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOF
cat > "$ROOTFS/etc/systemd/system/sheng-grow-root.service" <<'EOF'
[Unit]
Description=Expand Kali root filesystem to the userdata partition
After=local-fs.target
Before=display-manager.service
ConditionPathExists=!/var/lib/sheng-root-grown
[Service]
Type=oneshot
ExecStart=/bin/sh -ec 'resize2fs /dev/disk/by-partlabel/userdata; touch /var/lib/sheng-root-grown'
[Install]
WantedBy=multi-user.target
EOF
install -d "$ROOTFS/etc/ssh/sshd_config.d"
printf 'PermitRootLogin no\n' > "$ROOTFS/etc/ssh/sshd_config.d/10-sheng.conf"
# Generate unique SSH keys on the tablet instead of cloning builder keys.
rm -f "$ROOTFS/etc/ssh/ssh_host_"*
cat > "$ROOTFS/etc/systemd/system/sheng-ssh-keys.service" <<'EOF'
[Unit]
Description=Generate unique SSH host keys
Before=ssh.service
[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A
[Install]
WantedBy=multi-user.target
EOF
# This Wi-Fi tablet has no enabled modem remoteproc for rmtfs to manage.
chroot "$ROOTFS" systemctl mask rmtfs.service
chroot "$ROOTFS" systemctl enable NetworkManager ssh sddm sheng-usb-network sheng-grow-root sheng-ssh-keys sheng-swap sheng-hotspot-setup xiaomi-sheng-thp systemd-timesyncd
chroot "$ROOTFS" systemctl set-default graphical.target
# Validate actual target binaries and installed packages, not just filenames.
chroot "$ROOTFS" /bin/bash -ec '
    test "$(dpkg --print-architecture)" = arm64
    . /etc/os-release
    test "$ID" = kali
    dpkg-query -W kali-desktop-kde plasma-workspace sddm linux-xiaomi-sheng xiaomi-sheng-thp libssc
    test -e /usr/share/wayland-sessions/plasma.desktop -o -e /usr/share/wayland-sessions/plasmawayland.desktop
    test -d /usr/lib/firmware/qcom
' > "$OUT_DIR/validation.txt"
chroot "$ROOTFS" dpkg-query -W -f='${binary:Package}\t${Version}\t${Architecture}\n' > "$OUT_DIR/packages.tsv"
chroot "$ROOTFS" apt-get clean
rm -f "$ROOTFS/tmp/kernel.deb" "$ROOTFS/usr/sbin/policy-rc.d" "$ROOTFS/usr/bin/qemu-aarch64-static"
rm -f "$ROOTFS/etc/resolv.conf"
ln -s /run/NetworkManager/resolv.conf "$ROOTFS/etc/resolv.conf"
truncate -s 0 "$ROOTFS/etc/machine-id"
rm -f "$ROOTFS/var/lib/dbus/machine-id"
ln -s /etc/machine-id "$ROOTFS/var/lib/dbus/machine-id"
cleanup
e2fsck -f -n "$BUILD_DIR/rootfs.img"
img2simg "$BUILD_DIR/rootfs.img" "$OUT_DIR/rootfs-kali-arm64-kde-sheng.img"
cp "$ASSET_DIR/boot_sheng_singleboot.img" "$OUT_DIR/boot-kali-sheng.img"
cp "$PROJECT/configs/sources.json" "$OUT_DIR/sources.json"
python3 "$PROJECT/scripts/validate-images.py" "$OUT_DIR" --write-manifest
echo BUILD_COMPLETE
