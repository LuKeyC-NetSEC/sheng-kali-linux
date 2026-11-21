// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <QObject>
#include <QPointer>
#include <QTimer>
#include <QVariantMap>

class ShellCorona;
namespace Plasma { class Applet; class Containment; }
namespace KWayland::Client { class PlasmaWindowManagement; class PlasmaWindow; }

struct ShengDockState {
    bool maximized=false, revealed=false, desktop=false, drawer=false;
    bool hidden() const { return maximized && !revealed && !desktop && !drawer; }
    void setMaximized(bool value) { if(value!=maximized)revealed=false;maximized=value; }
    bool reveal() { if(!maximized)return false;revealed=true;return true; }
    void dismiss() { revealed=false; }
    bool canGoHome() const { return maximized && revealed; }
};

class ShengDesktopPolicy final : public QObject {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.sheng.DesktopPolicy")
public:
    explicit ShengDesktopPolicy(ShellCorona *corona);
    void setWindowManagement(KWayland::Client::PlasmaWindowManagement *management);
    void panelCreated();
public Q_SLOTS:
    void RevealDock();
    void DismissDock();
    void ShowDesktop();
    void OpenAppDrawer();
    void OpenControlCenter();
    void CloseControlCenter();
    QVariantMap GetNativeState() const;
    void refreshInputContext();
Q_SIGNALS:
    void PointerPresenceChanged(bool present);
    void DockVisibilityChanged(bool hidden);
private:
    void observe(Plasma::Containment *containment);
    void observe(KWayland::Client::PlasmaWindow *window);
    void updateWindows();
    void applyDock();
    void updateApplet(Plasma::Applet *applet);
    Plasma::Applet *findApplet(const QString &prefix) const;
    bool closeControlCenter();
    ShellCorona *m_corona;
    QPointer<KWayland::Client::PlasmaWindowManagement> m_windows;
    ShengDockState m_dock;
    QTimer m_revealTimer,m_settle;
    bool m_pointer=false,m_keyboard=false,m_inputKnown=false,m_published=false;
};
