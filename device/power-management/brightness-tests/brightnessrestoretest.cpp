// SPDX-License-Identifier: GPL-2.0-or-later
#include "kwinbrightness.h"
#include <QCoreApplication>
#include <QEvent>
#include <QTest>
#include <QTimer>

// Replace only the scheduled backend write. No backend detection or D-Bus
// connection is made, and no real output or user's brightness is changed.
class PendingWrite final : public QObject {
public:
    KWinDisplayBrightness *display;
    int writes = 0;
    explicit PendingWrite(KWinDisplayBrightness *value) : display(value) {}
    bool eventFilter(QObject *object, QEvent *event) override
    {
        auto *timer = qobject_cast<QTimer *>(object);
        if (event->type() == QEvent::Timer && timer && timer->isSingleShot() && timer->interval() == 0) {
            timer->stop();
            display->applyPendingBrightness();
            ++writes;
            return true;
        }
        return false;
    }
};

class BrightnessRestoreTest : public QObject {
    Q_OBJECT
private Q_SLOTS:
    void restoresInheritedDimmingWithoutChangingUserBrightness()
    {
        KScreen::OutputPtr output(new KScreen::Output);
        output->setBrightness(0.8);
        output->setDimming(0.3);
        KWinDisplayDetector detector;
        KWinDisplayBrightness display(output, &detector, QStringLiteral("test"));
        PendingWrite writer(&display);
        QCoreApplication::instance()->installEventFilter(&writer);
        // This must schedule a write even when the new controller's desired
        // active state is 1.0. The pre-fix constructor incorrectly skips it.
        display.setDimmingMultiplier(1.0);
        QTRY_COMPARE_WITH_TIMEOUT(output->dimming(), 1.0, 100);
        QCOMPARE(writer.writes, 1);
        QCOMPARE(output->brightness(), 0.8);
    }

    void preservesAnIntentionalCurrentDimmingLimit()
    {
        KScreen::OutputPtr output(new KScreen::Output);
        output->setBrightness(0.6);
        output->setDimming(0.2);
        KWinDisplayDetector detector;
        KWinDisplayBrightness display(output, &detector, QStringLiteral("test"));
        PendingWrite writer(&display);
        QCoreApplication::instance()->installEventFilter(&writer);
        display.setDimmingMultiplier(0.4);
        QTRY_COMPARE_WITH_TIMEOUT(output->dimming(), 0.4, 100);
        QCOMPARE(output->brightness(), 0.6);
    }

    void doesNotRewriteAnAlreadyNormalOutput()
    {
        KScreen::OutputPtr output(new KScreen::Output);
        output->setBrightness(0.7);
        output->setDimming(1.0);
        KWinDisplayDetector detector;
        KWinDisplayBrightness display(output, &detector, QStringLiteral("test"));
        PendingWrite writer(&display);
        QCoreApplication::instance()->installEventFilter(&writer);
        display.setDimmingMultiplier(1.0);
        QTest::qWait(20);
        QCOMPARE(writer.writes, 0);
        QCOMPARE(output->brightness(), 0.7);
    }
};
QTEST_GUILESS_MAIN(BrightnessRestoreTest)
#include "brightnessrestoretest.moc"
