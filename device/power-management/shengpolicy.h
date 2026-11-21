// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <KSharedConfig>
#include <QFile>

namespace PowerDevil {
class Core;
namespace ShengPolicy {
inline bool isDevice()
{
    QFile model(QStringLiteral("/sys/firmware/devicetree/base/model"));
    return model.open(QIODevice::ReadOnly)
        && QString::fromUtf8(model.readAll()).remove(QChar(u'\0')).trimmed() == QStringLiteral("Xiaomi Pad 6S Pro 12.4");
}
bool migrateDefaults(const KSharedConfig::Ptr &config, bool canSuspend);
int lockMinutes(int displayIdleSeconds);
void initialize(Core *core);
}
}
