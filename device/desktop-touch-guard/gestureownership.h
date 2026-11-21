// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

// Closing a surface during motion must not give the remaining touch sequence
// to the surface underneath it. Decide the upward action at the initial down.
class DesktopGestureOwnership {
public:
    enum class Action { None, OpenDrawer, CloseControlCenter };
    bool controlCenterVisible = false;
    void begin() { begin(controlCenterVisible); }
    void begin(bool visibleAtPress) { m_active=true;m_controlCenterAtPress=visibleAtPress; }
    void cancel() { m_active=false; }
    Action finishUpward() {
        if(!m_active)return Action::None;
        m_active=false;
        return m_controlCenterAtPress?Action::CloseControlCenter:Action::OpenDrawer;
    }
private:
    bool m_active=false,m_controlCenterAtPress=false;
};
