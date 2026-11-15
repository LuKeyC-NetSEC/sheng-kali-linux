import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as P5Support

PlasmoidItem {
    id: root
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    preferredRepresentation: fullRepresentation
    implicitWidth: 1
    implicitHeight: 1
    Layout.minimumWidth: 1
    Layout.minimumHeight: 1
    fullRepresentation: Item { implicitWidth: 1; implicitHeight: 1 }
    P5Support.DataSource {
        id: execute
        engine: "executable"
        connectedSources: []
        onNewData: function(source, data) { disconnectSource(source) }
    }
    Item {
        id: region
        parent: root.Window.window ? root.Window.window.contentItem : null
        visible: !Plasmoid.configuration.pointerPresent
        x: parent ? parent.width / 2 : 0
        y: 0
        width: parent ? parent.width / 2 : 0
        height: parent ? parent.height : 0
        z: 100000
        DragHandler {
            property bool qualified: false
            target: null
            acceptedDevices: PointerDevice.TouchScreen
            minimumPointCount: 1
            maximumPointCount: 1
            dragThreshold: 12
            xAxis.enabled: false
            onActiveChanged: {
                if (active) qualified = false
                else if (qualified) {
                    qualified = false
                    execute.connectSource("qdbus6 org.sheng.DesktopPolicy /org/sheng/DesktopPolicy org.sheng.DesktopPolicy.OpenControlCenter")
                }
            }
            onActiveTranslationChanged: if (active && activeTranslation.y > 48) qualified = true
        }
    }
}
