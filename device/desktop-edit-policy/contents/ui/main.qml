import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore

PlasmoidItem {
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    implicitWidth: 1
    implicitHeight: 1
    Layout.minimumWidth: 1
    Layout.minimumHeight: 1
    preferredRepresentation: fullRepresentation
    fullRepresentation: Item { implicitWidth: 1; implicitHeight: 1 }
}
