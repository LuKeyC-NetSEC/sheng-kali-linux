// SPDX-License-Identifier: GPL-3.0-or-later
#include "inputpresence.h"
#include <core/inputdevice.h>
#include <input.h>
#include <main.h>
#include <tabletmodemanager.h>
#include <QDir>
#include <QMetaProperty>
#include <libudev.h>
#include <linux/input.h>
#include <sys/stat.h>

InputPresence::InputPresence(QObject *parent) : QObject(parent)
{
    m_debounce.setSingleShot(true);
    m_debounce.setInterval(350); // Coalesce Bluetooth reconnect/udev bursts.
    connect(&m_debounce,&QTimer::timeout,this,&InputPresence::refresh);
    connect(KWin::input(),&KWin::InputRedirection::deviceAdded,this,[this](KWin::InputDevice *device){observe(device);schedule();});
    connect(KWin::input(),&KWin::InputRedirection::deviceRemoved,this,&InputPresence::schedule);
    connect(KWin::input(),&KWin::InputRedirection::hasAlphaNumericKeyboardChanged,this,&InputPresence::schedule);
    connect(KWin::input(),&KWin::InputRedirection::hasTabletModeSwitchChanged,this,&InputPresence::schedule);
    connect(&m_paths,&QFileSystemWatcher::directoryChanged,this,[this]{openPinAttribute();schedule();});
    for (const auto &path : {QStringLiteral("/sys/class/misc"),QStringLiteral("/sys/class/misc/nanosic_hinge")}) {
        if (QDir(path).exists()) m_paths.addPath(path);
    }
    for (auto *device:KWin::input()->devices()) observe(device);
    openPinAttribute();
    refresh();
}

void InputPresence::observe(KWin::InputDevice *device)
{
    // Observe the compositor's existing switch stream. This still runs when a
    // user forces tablet mode off/on; a UI preference is not a physical fold.
    if(device->isTabletModeSwitch())connect(device,&KWin::InputDevice::switchToggle,this,&InputPresence::schedule);
    const int index=device->metaObject()->indexOfProperty("enabled");
    if(index>=0){
        const auto signal=device->metaObject()->property(index).notifySignal();
        const auto slot=metaObject()->method(metaObject()->indexOfSlot("schedule()"));
        if(signal.isValid()) QObject::connect(device,signal,this,slot);
    }
}

void InputPresence::schedule()
{
    m_debounce.start();
}

void InputPresence::openPinAttribute()
{
    if(m_pin.isOpen()) {
        struct stat opened{},current{};
        if(fstat(m_pin.handle(),&opened)==0 && stat(m_pin.fileName().toLocal8Bit().constData(),&current)==0
            && opened.st_dev==current.st_dev && opened.st_ino==current.st_ino) return;
    }
    m_notification.reset();m_pin.close();
    m_pin.setFileName(QStringLiteral("/sys/class/misc/nanosic_hinge/keyboard_attached"));
    if(!m_pin.open(QIODevice::ReadOnly|QIODevice::Unbuffered)) return;
    // sysfs_notify produces POLLPRI. QFileSystemWatcher alone doesn't observe
    // this attribute's value changes; there is no periodic polling fallback.
    m_pin.readAll();
    m_notification=std::make_unique<QSocketNotifier>(m_pin.handle(),QSocketNotifier::Exception,this);
    connect(m_notification.get(),&QSocketNotifier::activated,this,[this]{refresh();});
    const auto directory=QStringLiteral("/sys/class/misc/nanosic_hinge");
    if(!m_paths.directories().contains(directory)) m_paths.addPath(directory);
}

void InputPresence::refresh()
{
    openPinAttribute();
    bool pin=false;
    if(m_pin.isOpen()){
        m_pin.seek(0);
        pin=m_pin.readAll().trimmed()=="1";
    }
    auto *tablet=KWin::kwinApp()->tabletModeManager();
    const bool folded=KWin::input()->hasTabletModeSwitch() && tablet && tablet->isTablet();
    const bool available=pin && !folded;
    bool keyboard=available,pointer=false;
    struct udev *context=udev_new();
    for(auto *device:KWin::input()->devices()){
        if(!device->isEnabled() || device->sysPath().isEmpty() || device->sysPath().contains(QStringLiteral("/devices/virtual/"))
            || device->busType()==BUS_VIRTUAL || device->isTouch() || device->isTabletTool() || device->isTabletPad()) continue;
        const bool dock=device->name()==QStringLiteral("Xiaomi Keyboard") || device->name()==QStringLiteral("Xiaomi Touchpad");
        if(dock && !available) continue; // Folded or detached covers retain HID nodes.
        pointer |= device->isPointer() || device->isTouchpad();
        if(!context || !device->isKeyboard() || dock) continue;
        auto *entry=udev_device_new_from_syspath(context,device->sysPath().toLocal8Bit().constData());
        if(!entry) continue;
        const auto property=[entry](const char *name){const char *value=udev_device_get_property_value(entry,name);return value?QByteArray(value):QByteArray();};
        keyboard |= property("ID_INPUT_KEYBOARD")=="1" &&
            (property("ID_BUS")=="usb" || property("ID_BUS")=="bluetooth" || property("ID_INTEGRATION")=="external");
        udev_device_unref(entry);
    }
    if(context) udev_unref(context);
    const bool changed=keyboard!=m_keyboard || pointer!=m_pointer || pin!=m_pinAttached || folded!=m_pinFolded;
    m_keyboard=keyboard;m_pointer=pointer;m_pinAttached=pin;m_pinFolded=folded;
    if(changed)Q_EMIT this->changed();
}
