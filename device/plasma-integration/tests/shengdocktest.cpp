// SPDX-License-Identifier: GPL-2.0-or-later
#include "../shengdesktoppolicy.h"
#include "../../desktop-touch-guard/gestureownership.h"
#include <QTest>

class DockTest : public QObject {
    Q_OBJECT
private Q_SLOTS:
    void upwardSwipeRemainsOwnedByClosingControlCenter()
    {
        DesktopGestureOwnership owner;
        owner.controlCenterVisible=true;owner.begin();
        owner.controlCenterVisible=false; // The panel hides before touch-up.
        QCOMPARE(owner.finishUpward(),DesktopGestureOwnership::Action::CloseControlCenter);
        QCOMPARE(owner.finishUpward(),DesktopGestureOwnership::Action::None);
        owner.begin();
        QCOMPARE(owner.finishUpward(),DesktopGestureOwnership::Action::OpenDrawer);
    }
    void cancelledTouchCannotOpenAnythingUnderneath()
    {
        DesktopGestureOwnership owner;owner.begin();owner.cancel();
        QCOMPARE(owner.finishUpward(),DesktopGestureOwnership::Action::None);
    }
    void visibleWindowWinsBeforeBusPublication()
    {
        DesktopGestureOwnership owner;owner.controlCenterVisible=false;
        owner.begin(true); // The compositor already sees the control window.
        QCOMPARE(owner.finishUpward(),DesktopGestureOwnership::Action::CloseControlCenter);
    }
    void outsidePressDismissesTemporaryDock()
    {
        ShengDockState state;state.setMaximized(true);QVERIFY(state.hidden());
        QVERIFY(state.reveal());QVERIFY(!state.hidden());
        state.dismiss();QVERIFY(state.hidden());QVERIFY(!state.canGoHome());
    }
    void normalDockCannotBeDismissedOrSendHome()
    {
        ShengDockState state;QVERIFY(!state.reveal());
        state.dismiss();QVERIFY(!state.hidden());QVERIFY(!state.canGoHome());
    }
    void thirdSwipeGoesHomeWithoutClosingApplication()
    {
        ShengDockState state;state.setMaximized(true);state.reveal();
        QVERIFY(state.canGoHome());state.dismiss();state.desktop=true;
        QVERIFY(!state.hidden());QVERIFY(state.maximized);
        state.desktop=false;QVERIFY(state.hidden());
    }
    void restoringWindowClearsTemporaryReveal()
    {
        ShengDockState state;state.setMaximized(true);state.reveal();
        state.setMaximized(false);QVERIFY(!state.revealed);QVERIFY(!state.hidden());
        state.setMaximized(true);QVERIFY(state.hidden());
    }
    void appDrawerKeepsSameDockVisible()
    {
        ShengDockState state;state.setMaximized(true);state.reveal();
        state.drawer=true;QVERIFY(!state.hidden());
        state.drawer=false;QVERIFY(!state.hidden());QVERIFY(state.revealed);
        state.dismiss();QVERIFY(state.hidden());
    }
};
QTEST_GUILESS_MAIN(DockTest)
#include "shengdocktest.moc"
