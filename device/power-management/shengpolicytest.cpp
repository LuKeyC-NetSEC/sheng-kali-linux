// SPDX-License-Identifier: GPL-2.0-or-later
#include "shengpolicy.h"
#include <KConfigGroup>
#include <QTemporaryDir>
#include <QTest>

class ShengPolicyTest : public QObject {
    Q_OBJECT
private Q_SLOTS:
    void migratesLegacyPolicyWithoutLosingUnrelatedPreferences()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const auto config = KSharedConfig::openConfig(directory.filePath(QStringLiteral("powerdevilrc")), KConfig::SimpleConfig);
        KConfigGroup general(config, QStringLiteral("General"));
        general.writeEntry("UserPreference", QStringLiteral("keep"));
        auto battery = KConfigGroup(config, QStringLiteral("Battery")).group(QStringLiteral("SuspendAndShutdown"));
        battery.writeEntry("AutoSuspendAction", 8);
        auto legacy = KConfigGroup(config, QStringLiteral("AC")).group(QStringLiteral("RunScript"));
        legacy.writeEntry("ProfileLoadCommand", QStringLiteral("/usr/libexec/sheng-set-screen-lock-timeout 60"));
        auto custom = KConfigGroup(config, QStringLiteral("Battery")).group(QStringLiteral("RunScript"));
        custom.writeEntry("ProfileLoadCommand", QStringLiteral("/custom/user-command"));
        QVERIFY(PowerDevil::ShengPolicy::migrateDefaults(config, true));
        QCOMPARE(general.readEntry("UserPreference", QString()), QStringLiteral("keep"));
        QCOMPARE(battery.readEntry("AutoSuspendAction", -1), 0);
        QCOMPARE(KConfigGroup(config, QStringLiteral("AC")).group(QStringLiteral("SuspendAndShutdown")).readEntry("AutoSuspendAction", -1), 0);
        const auto low = KConfigGroup(config, QStringLiteral("LowBattery")).group(QStringLiteral("SuspendAndShutdown"));
        QCOMPARE(low.readEntry("AutoSuspendAction", -1), 1);
        QCOMPARE(low.readEntry("AutoSuspendIdleTimeoutSec", -1), 300);
        for (const auto &profile : {QStringLiteral("AC"), QStringLiteral("Battery"), QStringLiteral("LowBattery")}) {
            const auto display = KConfigGroup(config, profile).group(QStringLiteral("Display"));
            QCOMPARE(display.readEntry("TurnOffDisplayIdleTimeoutSec", -1), 60);
            QVERIFY(display.readEntry("LockBeforeTurnOffDisplay", false));
        }
        QVERIFY(!legacy.hasKey("ProfileLoadCommand"));
        QCOMPARE(custom.readEntry("ProfileLoadCommand", QString()), QStringLiteral("/custom/user-command"));
        const KConfigGroup levels(config, QStringLiteral("BatteryManagement"));
        QCOMPARE(levels.readEntry("BatteryLowLevel", -1), 10);
        QCOMPARE(levels.readEntry("BatteryCriticalLevel", -1), 5);
        QCOMPARE(levels.readEntry("BatteryCriticalAction", -1), 1);
        // A later user edit is not silently overwritten on the next daemon start.
        battery.writeEntry("AutoSuspendIdleTimeoutSec", 900);
        QVERIFY(!PowerDevil::ShengPolicy::migrateDefaults(config, true));
        QCOMPARE(battery.readEntry("AutoSuspendIdleTimeoutSec", -1), 900);
    }

    void unsupportedSuspendPreservesExistingCriticalProtection()
    {
        QTemporaryDir directory;
        const auto config = KSharedConfig::openConfig(directory.filePath(QStringLiteral("powerdevilrc")), KConfig::SimpleConfig);
        KConfigGroup battery(config, QStringLiteral("BatteryManagement"));
        battery.writeEntry("BatteryCriticalAction", 8);
        QVERIFY(PowerDevil::ShengPolicy::migrateDefaults(config, false));
        QCOMPARE(battery.readEntry("BatteryCriticalAction", -1), 8);
        QCOMPARE(KConfigGroup(config, QStringLiteral("LowBattery")).group(QStringLiteral("SuspendAndShutdown"))
                     .readEntry("AutoSuspendAction", -1), 0);
    }

    void alignsLockerWithNativeDisplayProfiles()
    {
        QCOMPARE(PowerDevil::ShengPolicy::lockMinutes(60), 1);
        QCOMPARE(PowerDevil::ShengPolicy::lockMinutes(3600), 60);
        QCOMPARE(PowerDevil::ShengPolicy::lockMinutes(1800), 30);
        QCOMPARE(PowerDevil::ShengPolicy::lockMinutes(300), 5);
        QCOMPARE(PowerDevil::ShengPolicy::lockMinutes(-1), -1);
        QCOMPARE(PowerDevil::ShengPolicy::lockMinutes(0), -1);
    }

    void upgradesManagedDefaultsWithoutChangingUserPreferences()
    {
        QTemporaryDir directory;
        const auto config = KSharedConfig::openConfig(directory.filePath(QStringLiteral("powerdevilrc")), KConfig::SimpleConfig);
        KConfigGroup(config, QStringLiteral("ShengPower")).writeEntry("PolicyVersion", 1);
        auto ac = KConfigGroup(config, QStringLiteral("AC")).group(QStringLiteral("Display"));
        auto battery = KConfigGroup(config, QStringLiteral("Battery")).group(QStringLiteral("Display"));
        auto low = KConfigGroup(config, QStringLiteral("LowBattery")).group(QStringLiteral("SuspendAndShutdown"));
        ac.writeEntry("TurnOffDisplayIdleTimeoutSec", 3600);
        battery.writeEntry("TurnOffDisplayIdleTimeoutSec", 900); // User customization.
        low.writeEntry("AutoSuspendIdleTimeoutSec", 300);
        low.writeEntry("AutoSuspendAction", 1);
        QVERIFY(PowerDevil::ShengPolicy::migrateDefaults(config, true));
        QCOMPARE(ac.readEntry("TurnOffDisplayIdleTimeoutSec", -1), 60);
        QCOMPARE(battery.readEntry("TurnOffDisplayIdleTimeoutSec", -1), 900);
        QCOMPARE(low.readEntry("AutoSuspendIdleTimeoutSec", -1), 300);
        QCOMPARE(low.readEntry("AutoSuspendAction", -1), 1);
        QCOMPARE(KConfigGroup(config, QStringLiteral("ShengPower")).readEntry("PolicyVersion", 0), 2);
        ac.writeEntry("TurnOffDisplayIdleTimeoutSec", 420);
        QVERIFY(!PowerDevil::ShengPolicy::migrateDefaults(config, true));
        QCOMPARE(ac.readEntry("TurnOffDisplayIdleTimeoutSec", -1), 420);
    }
};
QTEST_GUILESS_MAIN(ShengPolicyTest)
#include "shengpolicytest.moc"
