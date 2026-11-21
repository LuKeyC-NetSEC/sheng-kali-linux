// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "tabbox.h"
#include "input.h"
#include "input_event.h"
#include "wayland_server.h"
#include <QDBusConnection>
#include <QDBusMessage>
#include <QDBusPendingCallWatcher>
#include <QElapsedTimer>
#include <QKeyEvent>
#include <cmath>

namespace KWin::TabBox {
// Owned by the native TabBox. Consumes the compositor's existing gesture
// stream; it never opens evdev/uinput or changes real keyboard modifiers.
class ShengTabBoxGestures final : public QObject, public InputEventFilter {
public:
    explicit ShengTabBoxGestures(TabBox *owner)
        : QObject(owner), InputEventFilter(InputFilterOrder::ScreenEdge), m_owner(owner)
    {
        input()->installInputEventFilter(this);
        connect(owner,&TabBox::tabBoxClosed,this,[this]{++m_generation;m_armed=m_switching=m_pending=m_owned=false;m_watchdog.stop();});
        connect(input(),&InputRedirection::deviceRemoved,this,[this]{finish(true);});
        m_watchdog.setSingleShot(true);
        m_watchdog.setInterval(30000);
        connect(&m_watchdog,&QTimer::timeout,this,[this]{finish(true);});
    }
    ~ShengTabBoxGestures() override { finish(true); }
    bool swipeGestureBegin(PointerSwipeGestureBeginEvent *event) override
    {
        finish(true);
        if(event->fingerCount!=3 || !waylandServer() || waylandServer()->isScreenLocked()) return false;
        m_armed=true;m_switching=m_owner->isDisplayed();m_pending=m_owned=false;m_intent=0;m_lastDirection=m_candidate=0;
        m_x=m_y=m_navX=m_navY=0;m_started.start();m_selected.start();m_watchdog.start();
        return true;
    }
    bool swipeGestureUpdate(PointerSwipeGestureUpdateEvent *event) override
    {
        if(!m_armed) return false;
        if(waylandServer()->isScreenLocked()){finish(true);return true;}
        m_watchdog.start();
        const auto delta=event->delta;
        if(std::hypot(delta.x(),delta.y())>35) return true;
        m_x+=delta.x();m_y+=delta.y();
        if(!m_switching){
            if(m_pending) return true;
            if(m_intent!=2 && std::abs(m_y)>=12 && std::abs(m_y)>=std::abs(m_x)*1.25) m_intent=2;
            else if(!m_intent && std::abs(m_x)>=32 && std::abs(m_x)>=std::abs(m_y)*1.8) m_intent=1;
            if(m_intent!=1 || std::abs(m_x)<std::abs(m_y)*1.8 || m_started.elapsed()<60) return true;
            m_pending=true;
            const bool forward=m_x>0;
            const auto generation=m_generation;
            auto request=QDBusMessage::createMethodCall(QStringLiteral("org.kde.kglobalaccel"),QStringLiteral("/component/kwin"),
                QStringLiteral("org.kde.kglobalaccel.Component"),QStringLiteral("invokeShortcut"));
            request.setArguments({QStringLiteral("Sheng Leave Task Cards")});
            auto *call=new QDBusPendingCallWatcher(QDBusConnection::sessionBus().asyncCall(request),this);
            connect(call,&QDBusPendingCallWatcher::finished,this,[this,forward,generation](QDBusPendingCallWatcher *done){
                done->deleteLater();if(generation!=m_generation)return;m_pending=false;
                if(!m_armed || waylandServer()->isScreenLocked()) return;
                m_owned=!m_owner->isDisplayed();
                if(m_owned && !m_owner->toggleMode(TabBoxWindowsMode)) return;
                if(m_owner->currentClientList().isEmpty()){m_owner->close(true);return;}
                m_owner->nextPrev(forward);
                m_switching=true;m_navX=m_navY=0;m_selected.restart();m_lastDirection=forward?1:-1;
            });
            return true;
        }
        m_navX+=delta.x();m_navY+=delta.y();
        const bool horizontal=std::abs(m_navX)>=std::abs(m_navY);
        const double distance=horizontal?m_navX:m_navY,cross=horizontal?std::abs(m_navY):std::abs(m_navX);
        const int direction=distance>0?1:-1,proposed=(horizontal?1:2)*direction;
        const double threshold=proposed==-m_lastDirection?140:110;
        if(std::abs(distance)<12 || std::abs(distance)<cross*1.5) return true;
        if(m_candidate!=proposed){m_candidate=proposed;m_candidateSince.restart();}
        if(std::abs(distance)>=threshold && m_candidateSince.elapsed()>=100 && m_selected.elapsed()>=180){
            const int key=horizontal?(direction>0?Qt::Key_Right:Qt::Key_Left):(direction>0?Qt::Key_Down:Qt::Key_Up);
            QKeyEvent navigation(QEvent::KeyPress,key,Qt::NoModifier);
            m_owner->grabbedKeyEvent(&navigation);
            m_navX=m_navY=0;m_candidate=0;m_selected.restart();m_lastDirection=proposed;
        }
        return true;
    }
    bool swipeGestureEnd(PointerSwipeGestureEndEvent *) override
    {
        const bool handled=m_armed;finish(false);return handled;
    }
    bool swipeGestureCancelled(PointerSwipeGestureCancelEvent *) override
    {
        const bool handled=m_armed;finish(true);return handled;
    }
private:
    void finish(bool cancelled)
    {
        const bool switching=m_switching,owned=m_owned;
        ++m_generation;m_armed=m_switching=m_pending=m_owned=false;m_watchdog.stop();
        if(switching && owned && m_owner->isDisplayed()) {
            if(cancelled || std::hypot(m_x,m_y)<40) m_owner->close(true);
            else m_owner->accept();
        }
    }
    TabBox *m_owner;
    QTimer m_watchdog;
    QElapsedTimer m_started,m_selected,m_candidateSince;
    bool m_armed=false,m_switching=false,m_pending=false,m_owned=false;
    quint64 m_generation=0;
    int m_intent=0,m_lastDirection=0,m_candidate=0;
    double m_x=0,m_y=0,m_navX=0,m_navY=0;
};
}
