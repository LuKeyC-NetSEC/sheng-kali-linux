// SPDX-License-Identifier: GPL-3.0-or-later
// Runs in plasmashell. Uses the desktop's explicit appletsLayout API, not a
// recursive object-tree search or a transient QML binding during every touch.
#include <Plasma/Applet>
#include <Plasma/Containment>
#include <Plasma/Corona>
#include <PlasmaQuick/AppletQuickItem>
#include <KPluginFactory>
#include <QCoreApplication>
#include <QDBusConnection>
#include <QDBusConnectionInterface>
#include <QDBusServiceWatcher>
#include <QMetaMethod>
#include <QPointer>
#include <QQmlProperty>
#include <QQuickItem>
#include <QSet>
#include <QTimer>
#include <QTouchEvent>

class ShengDesktopEditPolicy final : public Plasma::Applet {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.sheng.DesktopEditPolicy")
public:
    ShengDesktopEditPolicy(QObject *parent,const KPluginMetaData &metadata,const QVariantList &arguments)
        : Plasma::Applet(parent,metadata,arguments) {
        connect(this,&Plasma::Applet::containmentChanged,this,[this]{QTimer::singleShot(0,this,&ShengDesktopEditPolicy::setup);});
    }
    void init() override {
        Plasma::Applet::init();
        setStatus(Plasma::Types::HiddenStatus);
        QTimer::singleShot(0,this,&ShengDesktopEditPolicy::setup);
    }
    ~ShengDesktopEditPolicy() override {
        if(m_statusRegistered){
            QDBusConnection::sessionBus().unregisterObject(QStringLiteral("/org/sheng/DesktopEditPolicy"));
            QDBusConnection::sessionBus().unregisterService(QStringLiteral("org.sheng.DesktopEditPolicy"));
        }
    }
public Q_SLOTS:
    Q_SCRIPTABLE QVariantMap GetStatus()const {
        QVariantList conditions;
        for(auto *layout:m_observedLayouts)conditions.append(layout->property("editModeCondition").toInt());
        return {{QStringLiteral("native"),true},{QStringLiteral("automaticEdit"),false},
            {QStringLiteral("explicitEditing"),m_corona && m_corona->isEditMode()},
            {QStringLiteral("layoutConditions"),conditions},
            {QStringLiteral("layouts"),m_layouts},{QStringLiteral("containers"),m_containers}};
    }
private Q_SLOTS:
    void setup() {
        auto *corona=containment()?containment()->corona():nullptr;
        if(!corona || corona==m_corona)return;
        m_corona=corona;
        connect(corona,&Plasma::Corona::editModeChanged,this,&ShengDesktopEditPolicy::apply);
        connect(corona,&Plasma::Corona::containmentAdded,this,[this](Plasma::Containment *desktop){observe(desktop);});
        // ShellCorona publishes readiness after asynchronous desktop UI load.
        // Use its declared signal so this also applies on a fresh login, when
        // AppletQuickItem does not exist yet at containment restore time.
        const int ready=corona->metaObject()->indexOfSignal("screenUiReadyChanged(int,bool)");
        if(ready>=0)QObject::connect(corona,corona->metaObject()->method(ready),this,metaObject()->method(metaObject()->indexOfSlot("apply()")));
        auto bus=QDBusConnection::sessionBus();
        const bool alreadyManaged=bus.objectRegisteredAt(QStringLiteral("/org/sheng/DesktopEditPolicy"))!=nullptr;
        registerStatus();
        auto *watcher=new QDBusServiceWatcher(QStringLiteral("org.sheng.DesktopEditPolicy"),bus,QDBusServiceWatcher::WatchForUnregistration,this);
        connect(watcher,&QDBusServiceWatcher::serviceUnregistered,this,[this]{registerStatus();});
        // Close the accidentally entered editor once. Later explicit edit-mode
        // actions remain authoritative and are observed through Corona signals.
        if(!alreadyManaged)corona->setEditMode(false);
        for(auto *desktop:corona->containments())observe(desktop);
        apply();
    }
    void apply() {
        if(m_applying || !m_corona)return;
        m_applying=true;m_layouts=m_containers=0;
        for(auto *desktop:m_corona->containments()) {
            if(desktop->containmentType()!=Plasma::Containment::Desktop && desktop->containmentType()!=Plasma::Containment::Custom)continue;
            auto *root=PlasmaQuick::AppletQuickItem::itemForApplet(desktop);
            auto *layout=root?qobject_cast<QQuickItem *>(root->property("appletsLayout").value<QObject *>()):nullptr;
            if(!layout)continue;
            if(!m_observedLayouts.contains(layout)) {
                m_observedLayouts.insert(layout);
                connect(layout,&QQuickItem::childrenChanged,this,&ShengDesktopEditPolicy::apply);
                connect(layout,&QObject::destroyed,this,[this,layout]{m_observedLayouts.remove(layout);});
            }
            // Exact enum values from Plasma 6.7.4: Locked=0, Manual=1,
            // AfterPressAndHold=2. Never make the containment immutable.
            const int condition=desktop->immutability()!=Plasma::Types::Mutable?0:m_corona->isEditMode()?2:1;
            if(layout->property("editModeCondition").toInt()!=condition) {
                QQmlProperty::write(layout,QStringLiteral("editModeCondition"),condition);
                if(condition==1){QTouchEvent cancel(QEvent::TouchCancel);QCoreApplication::sendEvent(layout,&cancel);}
            }
            ++m_layouts;
            for(auto *container:layout->childItems()) {
                if(container->metaObject()->indexOfProperty("editModeCondition")<0)continue;
                if(container->property("editModeCondition").toInt()!=condition) {
                    if(condition==1)QMetaObject::invokeMethod(container,"cancelEdit");
                    QQmlProperty::write(container,QStringLiteral("editModeCondition"),condition);
                }
                ++m_containers;
            }
        }
        m_applying=false;
    }
private:
    void registerStatus(){
        auto bus=QDBusConnection::sessionBus();
        if(bus.objectRegisteredAt(QStringLiteral("/org/sheng/DesktopEditPolicy")))return;
        if(bus.registerService(QStringLiteral("org.sheng.DesktopEditPolicy")))
            m_statusRegistered=bus.registerObject(QStringLiteral("/org/sheng/DesktopEditPolicy"),this,QDBusConnection::ExportScriptableSlots);
    }
    void observe(Plasma::Containment *desktop) {
        if(desktop->containmentType()!=Plasma::Containment::Desktop && desktop->containmentType()!=Plasma::Containment::Custom)return;
        connect(desktop,&Plasma::Applet::immutabilityChanged,this,&ShengDesktopEditPolicy::apply);
        connect(desktop,&Plasma::Containment::appletAdded,this,[this]{QTimer::singleShot(0,this,&ShengDesktopEditPolicy::apply);});
        if(auto *item=PlasmaQuick::AppletQuickItem::itemForApplet(desktop))
            connect(item,&PlasmaQuick::AppletQuickItem::fullRepresentationItemChanged,this,&ShengDesktopEditPolicy::apply);
        QTimer::singleShot(0,this,&ShengDesktopEditPolicy::apply);
    }
    QPointer<Plasma::Corona> m_corona;
    QSet<QQuickItem *> m_observedLayouts;
    bool m_applying=false,m_statusRegistered=false;
    int m_layouts=0,m_containers=0;
};
K_PLUGIN_CLASS_WITH_JSON(ShengDesktopEditPolicy,"metadata.json")
#include "policy.moc"
