// SPDX-License-Identifier: GPL-2.0-or-later
// Native PowerDevil integration for Xiaomi sheng. No process-spawned policies.
#include "shengpolicy.h"
#include "powerdevilcore.h"
#include "controllers/suspendcontroller.h"

#include <KConfigGroup>
#include <KScreen/Config>
#include <KScreen/GetConfigOperation>
#include <KScreen/Output>
#include <KScreen/SetConfigOperation>
#include <QDBusArgument>
#include <QDBusConnection>
#include <QDBusMessage>
#include <QDBusObjectPath>
#include <QDBusVariant>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QObject>
#include <QStandardPaths>
#include <QTimer>
#include <algorithm>
#include <cmath>
#include <unistd.h>

namespace PowerDevil::ShengPolicy {

bool migrateDefaults(const KSharedConfig::Ptr &config, bool canSuspend)
{
    KConfigGroup managed(config, QStringLiteral("ShengPower"));
    const int version = managed.readEntry("PolicyVersion", 0);
    if (version >= 2) {
        return false; // Subsequent System Settings edits remain authoritative.
    }
    const QStringList profiles{QStringLiteral("AC"), QStringLiteral("Battery"), QStringLiteral("LowBattery")};
    if (version == 1) {
        // Update only the previous managed defaults. Preserve later user edits,
        // including suspension and battery protection settings.
        for (const auto &profile : profiles) {
            const int previousSeconds = profile == QStringLiteral("AC") ? 3600 : profile == QStringLiteral("Battery") ? 1800 : 300;
            auto group = KConfigGroup(config, profile);
            auto display = group.group(QStringLiteral("Display"));
            if (display.readEntry("TurnOffDisplayIdleTimeoutSec", -1) == previousSeconds) {
                display.writeEntry("TurnOffDisplayIdleTimeoutSec", 60);
            }
            auto suspend = group.group(QStringLiteral("SuspendAndShutdown"));
            if (profile != QStringLiteral("LowBattery") && suspend.readEntry("AutoSuspendIdleTimeoutSec", -1) == previousSeconds) {
                suspend.writeEntry("AutoSuspendIdleTimeoutSec", 60);
            }
        }
        managed.writeEntry("PolicyVersion", 2);
        config->sync();
        return true;
    }
    for (const auto &profile : profiles) {
        KConfigGroup group(config, profile);
        auto suspend = group.group(QStringLiteral("SuspendAndShutdown"));
        suspend.writeEntry("AutoSuspendAction", profile == QStringLiteral("LowBattery") && canSuspend ? 1 : 0);
        suspend.writeEntry("AutoSuspendIdleTimeoutSec", profile == QStringLiteral("LowBattery") ? 300 : 60);
        suspend.writeEntry("SleepMode", 1);
        suspend.writeEntry("PowerButtonAction", 32);
        suspend.writeEntry("PowerDownAction", 16);
        auto display = group.group(QStringLiteral("Display"));
        display.writeEntry("TurnOffDisplayWhenIdle", true);
        display.writeEntry("TurnOffDisplayIdleTimeoutSec", 60);
        display.writeEntry("TurnOffDisplayIdleTimeoutWhenLockedSec", 0);
        display.writeEntry("LockBeforeTurnOffDisplay", true);
        auto script = group.group(QStringLiteral("RunScript"));
        if (script.readEntry("ProfileLoadCommand", QString()).startsWith(QStringLiteral("/usr/libexec/sheng-set-screen-lock-timeout "))) {
            script.deleteEntry("ProfileLoadCommand");
        }
    }
    KConfigGroup battery(config, QStringLiteral("BatteryManagement"));
    battery.writeEntry("BatteryLowLevel", 10);
    battery.writeEntry("BatteryCriticalLevel", 5);
    if (canSuspend) {
        battery.writeEntry("BatteryCriticalAction", 1);
    }
    managed.writeEntry("SyncLockTimeout", true);
    managed.writeEntry("PolicyVersion", 2);
    config->sync();
    return true;
}

int lockMinutes(int seconds)
{
    return seconds >= 30 ? std::min(1440, std::max(1, seconds / 60)) : -1;
}

namespace {
QVariant systemProperty(const QString &path, const QString &interface, const QString &name)
{
    auto message = QDBusMessage::createMethodCall(QStringLiteral("org.freedesktop.login1"), path,
        QStringLiteral("org.freedesktop.DBus.Properties"), QStringLiteral("Get"));
    message.setArguments({interface, name});
    const auto reply = QDBusConnection::systemBus().call(message, QDBus::Block, 1000);
    return reply.type() == QDBusMessage::ReplyMessage && !reply.arguments().isEmpty()
        ? qvariant_cast<QDBusVariant>(reply.arguments().first()).variant() : QVariant();
}

struct Session {
    QString id;
    QDBusObjectPath path;
};

Session activeSession()
{
    Session session;
    const auto value = systemProperty(QStringLiteral("/org/freedesktop/login1/seat/seat0"),
        QStringLiteral("org.freedesktop.login1.Seat"), QStringLiteral("ActiveSession"));
    if (value.metaType() == QMetaType::fromType<QDBusArgument>()) {
        const auto argument = qvariant_cast<QDBusArgument>(value);
        argument.beginStructure();
        argument >> session.id >> session.path;
        argument.endStructure();
    }
    return session;
}

bool ownedSession(const Session &session)
{
    if (session.id.isEmpty()) {
        return false;
    }
    const auto value = systemProperty(session.path.path(), QStringLiteral("org.freedesktop.login1.Session"), QStringLiteral("User"));
    if (value.metaType() != QMetaType::fromType<QDBusArgument>()) {
        return false;
    }
    uint uid = 0;
    QDBusObjectPath user;
    const auto argument = qvariant_cast<QDBusArgument>(value);
    argument.beginStructure();
    argument >> uid >> user;
    argument.endStructure();
    return uid == getuid()
        && systemProperty(session.path.path(), QStringLiteral("org.freedesktop.login1.Session"), QStringLiteral("Type")).toString() == QStringLiteral("wayland")
        && systemProperty(session.path.path(), QStringLiteral("org.freedesktop.login1.Session"), QStringLiteral("Class")).toString() == QStringLiteral("user");
}

class Integration final : public QObject {
public:
    explicit Integration(Core *core) : QObject(core)
    {
        connect(core, &Core::profileChanged, this, [this](const QString &profile) { syncLock(profile); });
        connect(core->suspendController(), &SuspendController::aboutToSuspend, this, [this] {
            const auto session = activeSession();
            m_session = ownedSession(session) ? session : Session{};
        });
        connect(core->suspendController(), &SuspendController::resumeFromSuspend, this, [this] {
            QTimer::singleShot(3000, this, [this] { restoreSession(); });
        });
        QTimer::singleShot(0, this, [this, core] { syncLock(core->currentProfile()); });
    }

private:
    Session m_session;

    void syncLock(const QString &profile)
    {
        if (!QStringList{QStringLiteral("AC"), QStringLiteral("Battery"), QStringLiteral("LowBattery")}.contains(profile)) {
            return;
        }
        const auto config = KSharedConfig::openConfig(QStringLiteral("powerdevilrc"));
        config->reparseConfiguration();
        if (!KConfigGroup(config, QStringLiteral("ShengPower")).readEntry("SyncLockTimeout", true)) {
            return;
        }
        const auto display = KConfigGroup(config, profile).group(QStringLiteral("Display"));
        const int minutes = lockMinutes(display.readEntry("TurnOffDisplayIdleTimeoutSec", -1));
        if (!display.readEntry("TurnOffDisplayWhenIdle", true) || minutes < 0) {
            return;
        }
        const auto locker = KSharedConfig::openConfig(QStringLiteral("kscreenlockerrc"));
        auto daemon = KConfigGroup(locker, QStringLiteral("Daemon"));
        if (daemon.readEntry("Autolock", false) && daemon.readEntry("Timeout", -1) == minutes && daemon.readEntry("LockGrace", -1) == 0) {
            return;
        }
        daemon.writeEntry("Autolock", true);
        daemon.writeEntry("Timeout", minutes);
        daemon.writeEntry("LockGrace", 0);
        locker->sync();
        auto message = QDBusMessage::createMethodCall(QStringLiteral("org.freedesktop.ScreenSaver"), QStringLiteral("/ScreenSaver"),
            QStringLiteral("org.kde.screensaver"), QStringLiteral("configure"));
        QDBusConnection::sessionBus().asyncCall(message);
    }

    void restoreSession()
    {
        if (!ownedSession(m_session)) {
            return;
        }
        const auto active = activeSession();
        if (active.id != m_session.id) {
            const auto activeClass = systemProperty(active.path.path(), QStringLiteral("org.freedesktop.login1.Session"), QStringLiteral("Class")).toString();
            if (!activeClass.isEmpty() && activeClass != QStringLiteral("greeter")) {
                return;
            }
            if (!systemProperty(m_session.path.path(), QStringLiteral("org.freedesktop.login1.Session"), QStringLiteral("LockedHint")).toBool()) {
                return;
            }
            const auto saver = QDBusConnection::sessionBus().call(QDBusMessage::createMethodCall(QStringLiteral("org.freedesktop.ScreenSaver"),
                QStringLiteral("/ScreenSaver"), QStringLiteral("org.freedesktop.ScreenSaver"), QStringLiteral("GetActive")), QDBus::Block, 1000);
            if (saver.type() != QDBusMessage::ReplyMessage || saver.arguments().isEmpty() || !saver.arguments().first().toBool()) {
                return;
            }
            auto activate = QDBusMessage::createMethodCall(QStringLiteral("org.freedesktop.login1"), QStringLiteral("/org/freedesktop/login1"),
                QStringLiteral("org.freedesktop.login1.Manager"), QStringLiteral("ActivateSession"));
            activate.setArguments({m_session.id});
            if (QDBusConnection::systemBus().call(activate, QDBus::Block, 1000).type() != QDBusMessage::ReplyMessage) {
                return;
            }
        }
        // The existing KWin/Fcitx launcher restores its own input connection.
        // Never kill a keyboard or force a text-input context active here.
        QFile saved(QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation) + QStringLiteral("/kwinoutputconfig.json"));
        if (!saved.open(QIODevice::ReadOnly)) {
            return;
        }
        double scale = 0;
        for (const auto &value : QJsonDocument::fromJson(saved.readAll()).array()) {
            const auto section = value.toObject();
            if (section.value(QStringLiteral("name")).toString() != QStringLiteral("outputs")) {
                continue;
            }
            for (const auto &entry : section.value(QStringLiteral("data")).toArray()) {
                const auto output = entry.toObject();
                if (output.value(QStringLiteral("connectorName")).toString() == QStringLiteral("DSI-1")) {
                    scale = output.value(QStringLiteral("scale")).toDouble();
                }
            }
        }
        if (!std::isfinite(scale) || scale < 1 || scale > 4) {
            return;
        }
        auto *operation = new KScreen::GetConfigOperation(KScreen::GetConfigOperation::NoEDID);
        connect(operation, &KScreen::ConfigOperation::finished, this, [this, scale](KScreen::ConfigOperation *op) {
            if (op->hasError()) {
                return;
            }
            const auto configuration = qobject_cast<KScreen::GetConfigOperation *>(op)->config();
            if (!configuration) {
                return;
            }
            for (const auto &output : configuration->outputs()) {
                if (output->name() == QStringLiteral("DSI-1") && output->isEnabled() && std::abs(output->scale() - scale) > 0.01) {
                    output->setScale(scale);
                    new KScreen::SetConfigOperation(configuration);
                    return;
                }
            }
        });
    }
};
}

void initialize(Core *core)
{
    if (isDevice()) {
        new Integration(core);
    }
}
}
