// SPDX-License-Identifier: GPL-2.0-or-later
#include "shengdesktoppolicy.h"
#include "shellcorona.h"
#include "panelview.h"
#include <KConfigGroup>
#include <KConfigLoader>
#include <KWindowSystem>
#include <KWayland/Client/plasmawindowmanagement.h>
#include <Plasma/Applet>
#include <Plasma/Containment>
#include <PlasmaQuick/AppletQuickItem>
#include <QDBusConnection>
#include <QDBusMessage>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDBusServiceWatcher>
#include <QSignalBlocker>

using KWayland::Client::PlasmaWindow;
using KWayland::Client::PlasmaWindowManagement;

ShengDesktopPolicy::ShengDesktopPolicy(ShellCorona *corona) : QObject(corona),m_corona(corona)
{
    auto bus=QDBusConnection::sessionBus();
    bus.registerService(QStringLiteral("org.sheng.DesktopPolicy"));
    bus.registerObject(QStringLiteral("/org/sheng/DesktopPolicy"),this,QDBusConnection::ExportAllSlots|QDBusConnection::ExportAllSignals);
    bus.connect(QStringLiteral("org.sheng.DesktopTouch"),QStringLiteral("/org/sheng/DesktopTouch"),QStringLiteral("org.sheng.DesktopTouch"),
        QStringLiteral("KeyboardContextChanged"),this,SLOT(refreshInputContext()));
    auto *owners=new QDBusServiceWatcher(QStringLiteral("org.sheng.DesktopTouch"),bus,QDBusServiceWatcher::WatchForOwnerChange,this);
    connect(owners,&QDBusServiceWatcher::serviceOwnerChanged,this,[this]{refreshInputContext();});
    m_settle.setSingleShot(true);m_settle.setInterval(100);
    connect(&m_settle,&QTimer::timeout,this,&ShengDesktopPolicy::updateWindows);
    m_revealTimer.setSingleShot(true);m_revealTimer.setInterval(8000);
    connect(&m_revealTimer,&QTimer::timeout,this,&ShengDesktopPolicy::DismissDock);
    connect(KWindowSystem::self(),&KWindowSystem::showingDesktopChanged,this,[this](bool showing){
        m_dock.desktop=showing;if(showing){m_revealTimer.stop();m_dock.dismiss();}applyDock();
    });
    connect(corona,&Plasma::Corona::containmentAdded,this,[this](Plasma::Containment *containment){observe(containment);});
    for(auto *containment:corona->containments())observe(containment);
    m_dock.desktop=KWindowSystem::showingDesktop();
    refreshInputContext();
}

void ShengDesktopPolicy::observe(Plasma::Containment *containment)
{
    connect(containment,&Plasma::Containment::appletAdded,this,[this](Plasma::Applet *applet){
        QTimer::singleShot(0,this,[this,applet=QPointer<Plasma::Applet>(applet)]{if(applet)updateApplet(applet);});
    });
    for(auto *applet:containment->applets())updateApplet(applet);
}

void ShengDesktopPolicy::updateApplet(Plasma::Applet *applet)
{
    QString name=applet->pluginMetaData().pluginId();
    if(name.isEmpty())name=applet->config().parent().readEntry("plugin",QString());
    if(name.startsWith(QStringLiteral("org.sheng.desktop-gesture"))){applet->destroy();return;}
    const bool drawer=name.startsWith(QStringLiteral("org.sheng.linexin.launcher"));
    if(!m_inputKnown || (!drawer && name!=QStringLiteral("org.kontrol.center")))return;
    auto *scheme=applet->configScheme();
    auto *item=scheme?scheme->findItemByName(drawer?QStringLiteral("physicalKeyboardPresent"):QStringLiteral("pointerPresent")):nullptr;
    const bool value=drawer?m_keyboard:m_pointer;
    bool changed=false;
    if(item && item->property().toBool()!=value){item->setProperty(value);changed=true;}
    if(!changed)return;
    { const QSignalBlocker blocker(scheme);scheme->save();scheme->read(); }
    Q_EMIT scheme->configChanged();
    applet->configChanged();
}

void ShengDesktopPolicy::refreshInputContext()
{
    const auto request=QDBusMessage::createMethodCall(QStringLiteral("org.sheng.DesktopTouch"),QStringLiteral("/org/sheng/DesktopTouch"),
        QStringLiteral("org.sheng.DesktopTouch"),QStringLiteral("GetInputContext"));
    auto *watcher=new QDBusPendingCallWatcher(QDBusConnection::sessionBus().asyncCall(request,1000),this);
    connect(watcher,&QDBusPendingCallWatcher::finished,this,[this](QDBusPendingCallWatcher *done){
        const QDBusPendingReply<QVariantMap> reply=*done;done->deleteLater();
        if(reply.isError() || reply.value().value(QStringLiteral("integrationVersion")).toInt()<2)return;
        const bool pointer=reply.value().value(QStringLiteral("physicalPointer")).toBool();
        const bool keyboard=reply.value().value(QStringLiteral("physicalKeyboard")).toBool();
        const bool changed=!m_inputKnown || pointer!=m_pointer || keyboard!=m_keyboard;
        m_inputKnown=true;m_pointer=pointer;m_keyboard=keyboard;
        if(changed){
            for(auto *containment:m_corona->containments())for(auto *applet:containment->applets())updateApplet(applet);
            Q_EMIT PointerPresenceChanged(pointer);
        }
    });
}

void ShengDesktopPolicy::setWindowManagement(PlasmaWindowManagement *management)
{
    m_windows=management;
    connect(management,&PlasmaWindowManagement::windowCreated,this,[this](PlasmaWindow *window){observe(window);});
    connect(management,&PlasmaWindowManagement::activeWindowChanged,this,[this]{m_settle.start();});
    for(auto *window:management->windows())observe(window);
    m_settle.start();
}

void ShengDesktopPolicy::observe(PlasmaWindow *window)
{
    const auto schedule=[this]{m_settle.start();};
    connect(window,&PlasmaWindow::fullscreenChanged,this,schedule);
    connect(window,&PlasmaWindow::maximizedChanged,this,schedule);
    connect(window,&PlasmaWindow::minimizedChanged,this,schedule);
    connect(window,&PlasmaWindow::parentWindowChanged,this,schedule);
    connect(window,&PlasmaWindow::titleChanged,this,schedule);
    connect(window,&QObject::destroyed,this,schedule);
    m_settle.start();
}

void ShengDesktopPolicy::updateWindows()
{
    if(!m_windows)return;
    auto *window=m_windows->activeWindow();
    const bool wasDrawer=m_dock.drawer;
    m_dock.drawer=false;
    for(auto *candidate:m_windows->windows()){
        if(candidate->title()==QStringLiteral("Sheng Application Drawer") &&
            candidate->appId()==QStringLiteral("org.kde.plasmashell") && !candidate->isMinimized()){
            m_dock.drawer=true;break;
        }
    }
    if(m_dock.drawer){m_revealTimer.stop();applyDock();return;}
    int depth=0;
    while(window && window->parentWindow() && depth++<16)window=window->parentWindow();
    const bool maximized=window && !window->isMinimized() && !window->skipTaskbar()
        && window->appId()!=QStringLiteral("org.kde.plasmashell") && (window->isMaximized()||window->isFullscreen());
    if(maximized!=m_dock.maximized)m_revealTimer.stop();
    m_dock.setMaximized(maximized);
    if(wasDrawer && m_dock.revealed)m_revealTimer.start();
    applyDock();
}

void ShengDesktopPolicy::panelCreated(){applyDock();}
void ShengDesktopPolicy::applyDock()
{
    const bool hidden=m_dock.hidden();
    for(auto *containment:m_corona->containments()){
        if(containment->config().group(QStringLiteral("General")).readEntry("ShengThemeRole",QString())!=QStringLiteral("dock"))continue;
        if(auto *view=m_corona->panelView(containment))view->setVisibilityMode(hidden?PanelView::AutoHide:PanelView::WindowsGoBelow);
    }
    if(hidden!=m_published){m_published=hidden;Q_EMIT DockVisibilityChanged(hidden);}
}
void ShengDesktopPolicy::RevealDock(){if(m_dock.reveal()){applyDock();if(!m_dock.drawer)m_revealTimer.start();}}
void ShengDesktopPolicy::DismissDock(){m_revealTimer.stop();m_dock.dismiss();applyDock();}
void ShengDesktopPolicy::ShowDesktop(){if(!m_dock.canGoHome())return;m_revealTimer.stop();m_dock.dismiss();KWindowSystem::setShowingDesktop(true);}

Plasma::Applet *ShengDesktopPolicy::findApplet(const QString &prefix) const
{
    for(auto *containment:m_corona->containments())for(auto *applet:containment->applets())
        if(applet->pluginMetaData().pluginId().startsWith(prefix))return applet;
    return nullptr;
}
bool ShengDesktopPolicy::closeControlCenter()
{
    auto *applet=findApplet(QStringLiteral("org.kontrol.center"));
    auto *item=applet?PlasmaQuick::AppletQuickItem::itemForApplet(applet):nullptr;
    if(item && item->property("popupOpen").toBool()){
        QMetaObject::invokeMethod(item,"closePopup");return true;
    }
    return false;
}
void ShengDesktopPolicy::OpenAppDrawer()
{
    if(closeControlCenter())return; // One upward gesture cannot open both UIs.
    if(auto *applet=findApplet(QStringLiteral("org.sheng.linexin.launcher")))Q_EMIT applet->activated();
}
void ShengDesktopPolicy::OpenControlCenter()
{
    if(auto *applet=findApplet(QStringLiteral("org.kontrol.center")))Q_EMIT applet->activated();
}
void ShengDesktopPolicy::CloseControlCenter(){closeControlCenter();}
QVariantMap ShengDesktopPolicy::GetNativeState() const
{
    auto *control=findApplet(QStringLiteral("org.kontrol.center"));
    auto *item=control?PlasmaQuick::AppletQuickItem::itemForApplet(control):nullptr;
    return {{QStringLiteral("nativeIntegrationVersion"),1},{QStringLiteral("pointer_present"),m_pointer},
        {QStringLiteral("physicalKeyboard"),m_keyboard},{QStringLiteral("inputKnown"),m_inputKnown},{QStringLiteral("dock_hidden"),m_dock.maximized},
        {QStringLiteral("dock_revealed"),m_dock.revealed},{QStringLiteral("showing_desktop"),m_dock.desktop},
        {QStringLiteral("drawer_visible"),m_dock.drawer},{QStringLiteral("effectiveHidden"),m_dock.hidden()},
        {QStringLiteral("control_center_open"),item && item->property("popupOpen").toBool()}};
}
