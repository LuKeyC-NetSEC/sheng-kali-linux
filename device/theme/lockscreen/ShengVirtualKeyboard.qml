/*
    SPDX-FileCopyrightText: 2021 Aleix Pol Gonzalez <aleixpol@kde.org>
    SPDX-License-Identifier: LGPL-2.1-only OR LGPL-3.0-only OR LicenseRef-KDE-Accepted-LGPL

    Based on KDE plasma-workspace v6.7.4 VirtualKeyboard_wayland.qml.
    Use the 6.7 mode API and respect the physical-keyboard policy.
*/
import QtQuick
import org.kde.plasma.workspace.keyboardlayout as Keyboards

Item {
    readonly property bool active: Keyboards.KWinVirtualKeyboard.visible
    property bool activated: false
    visible: Keyboards.KWinVirtualKeyboard.visible
    x: InputMethod.keyboardRectangle.x
    y: InputMethod.keyboardRectangle.y
    height: InputMethod.keyboardRectangle.height
    width: InputMethod.keyboardRectangle.width

    // KWin 6.7: Never=0, NonMouseInput=1, AnyInput=2.
    onActivatedChanged: if (activated && Keyboards.KWinVirtualKeyboard.mode !== 0) {
        Qt.inputMethod.show();
    }
}
