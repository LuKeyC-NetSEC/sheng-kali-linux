// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <QObject>
#include <QFile>
#include <QFileSystemWatcher>
#include <QSocketNotifier>
#include <QTimer>
#include <memory>

namespace KWin { class InputDevice; }

class InputPresence final : public QObject {
    Q_OBJECT
public:
    explicit InputPresence(QObject *parent=nullptr);
    bool keyboard() const { return m_keyboard; }
    bool pointer() const { return m_pointer; }
    bool pinAttached() const { return m_pinAttached; }
    bool pinFolded() const { return m_pinFolded; }
    bool pinAvailable() const { return m_pinAttached && !m_pinFolded; }
    void reconcile() { refresh(); }
Q_SIGNALS:
    void changed();
private Q_SLOTS:
    void schedule();
    void refresh();
private:
    void observe(KWin::InputDevice *device);
    void openPinAttribute();
    QFile m_pin;
    std::unique_ptr<QSocketNotifier> m_notification;
    QFileSystemWatcher m_paths;
    QTimer m_debounce;
    bool m_keyboard=false,m_pointer=false;
    bool m_pinAttached=false,m_pinFolded=false;
};
