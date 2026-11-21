// SPDX-License-Identifier: MIT
// Native launcher policy. KWin supplies roles/device presence, never input text.
use std::{collections::HashMap, time::Duration};

use anyhow::{Context as _, Result, ensure};
use fcitx5_osk_common::dbus::{client::Fcitx5OskControllerServiceProxy, entity::WindowManagerMode};
use futures_util::StreamExt;
use zbus::{Connection, MatchRule, Message, MessageStream, fdo::DBusProxy, message::Type, proxy::CacheProperties};
use zvariant::OwnedValue;

use crate::dbus::client::{FdoScreenSaverServiceProxy, KwinVirtualKeyboardServiceProxy};

#[zbus::proxy(default_service = "org.sheng.DesktopTouch", default_path = "/org/sheng/DesktopTouch", interface = "org.sheng.DesktopTouch")]
trait InputContextService {
    #[zbus(name = "GetInputContext")]
    fn get_input_context(&self) -> zbus::Result<HashMap<String, OwnedValue>>;
}

#[zbus::proxy(default_service = "org.fcitx.Fcitx5", default_path = "/virtualkeyboard", interface = "org.fcitx.Fcitx.VirtualKeyboard1")]
trait FcitxVirtualKeyboardService {
    fn show_virtual_keyboard(&self) -> zbus::Result<()>;
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct Snapshot {
    owner: String,
    keyboard: bool,
    locked: bool,
    foreground: String,
    generation: i64,
    secure: bool,
    manual: bool,
    active: bool,
    supports_text: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Visibility { ForceHide, Hide, ShowViaFcitx }

#[derive(Debug, PartialEq, Eq)]
struct Plan {
    manual: bool,
    visibility: Option<Visibility>,
}

// Visibility isn't an input: dismissing a keyboard must not reopen it. Wait for
// ManualMode's actual acknowledgement before asking Fcitx to enter OSK mode.
fn plan(state: &Snapshot) -> Plan {
    let eligible = !matches!(state.foreground.as_str(), "desktop" | "none" | "lockscreen");
    let manual = state.keyboard || (state.locked && !state.secure) || (!state.secure && !eligible);
    let visibility = if manual {
        Some(Visibility::ForceHide)
    } else if state.secure || state.locked || state.manual {
        None // Only the greeter controls a secure panel's visibility.
    } else if state.active && state.supports_text {
        Some(Visibility::ShowViaFcitx)
    } else {
        Some(Visibility::Hide)
    };
    Plan { manual, visibility }
}

fn relevant(message: &Message) -> bool {
    let header = message.header();
    let path = header.path().map(|p| p.as_str()).unwrap_or_default();
    let member = header.member().map(|p| p.as_str()).unwrap_or_default();
    let interface = header.interface().map(|p| p.as_str()).unwrap_or_default();
    if interface == "org.freedesktop.DBus" && member == "NameOwnerChanged" {
        return message.body().deserialize::<(String, String, String)>().is_ok_and(|(name, _, _)| {
            matches!(name.as_str(), "org.kde.KWin" | "org.sheng.DesktopTouch" | "org.fcitx.Fcitx5" | "fyi.fortime.Fcitx5Osk" | "org.freedesktop.ScreenSaver")
        });
    }
    if path == "/org/sheng/DesktopTouch" && interface == "org.sheng.DesktopTouch" {
        return member == "KeyboardContextChanged" || member == "InputPresenceChanged";
    }
    if path == "/VirtualKeyboard" && interface == "org.kde.kwin.VirtualKeyboard" {
        return matches!(member, "activeChanged" | "activeClientSupportsTextInputChanged" | "modeChanged");
    }
    if interface == "org.freedesktop.ScreenSaver" && member == "ActiveChanged" {
        return path == "/ScreenSaver" || path == "/org/freedesktop/ScreenSaver";
    }
    if path == "/fyi/fortime/Fcitx5Osk/Controller" && interface == "org.freedesktop.DBus.Properties" && member == "PropertiesChanged" {
        return message.body().deserialize::<(String, HashMap<String, OwnedValue>, Vec<String>)>().is_ok_and(|(name, values, invalidated)| {
            name == "fyi.fortime.Fcitx5Osk.Controller1" &&
                (values.contains_key("ManualMode") || values.contains_key("Mode") ||
                 invalidated.iter().any(|key| key == "ManualMode" || key == "Mode"))
        });
    }
    false
}

async fn reconcile(connection: &Connection, previous: &mut Option<Snapshot>) -> Result<()> {
    let bus = DBusProxy::new(connection).await?;
    // No service activation just to inspect a controller. Wait for owner signals.
    for name in ["org.kde.KWin", "org.sheng.DesktopTouch", "org.fcitx.Fcitx5", "fyi.fortime.Fcitx5Osk", "org.freedesktop.ScreenSaver"] {
        if !bus.name_has_owner(name.try_into()?).await? {
            *previous = None;
            return Ok(());
        }
    }
    let kwin = KwinVirtualKeyboardServiceProxy::builder(connection).cache_properties(CacheProperties::No).build().await?;
    ensure!(kwin.sheng_integration_version().await? >= 1, "Native KWin input API is required");
    let context = InputContextServiceProxy::new(connection).await?.get_input_context().await?;
    ensure!(context.get("integrationVersion").and_then(|v| i32::try_from(v).ok()).unwrap_or(0) >= 2,
        "Native device/context API v2 is required");
    let keyboard = context.get("physicalKeyboard").and_then(|v| bool::try_from(v).ok()).context("Missing keyboard presence")?;
    let desired_mode = if keyboard { 0 } else { 2 };
    if kwin.mode().await? != desired_mode {
        kwin.set_mode(desired_mode).await?;
    }
    let owner = bus.get_name_owner("fyi.fortime.Fcitx5Osk".try_into()?).await?;
    let controller = Fcitx5OskControllerServiceProxy::builder(connection).destination(owner.as_str())?
        .cache_properties(CacheProperties::No).build().await?;
    let state = Snapshot {
        owner: owner.to_string(), keyboard,
        locked: context.get("locked").and_then(|v| bool::try_from(v).ok()).context("Missing lock state")?
            || FdoScreenSaverServiceProxy::new(connection).await?.get_active().await?,
        foreground: context.get("foreground").and_then(|v| <&str>::try_from(v).ok()).context("Missing window role")?.to_owned(),
        generation: context.get("generation").and_then(|v| i64::try_from(v).ok()).context("Missing context generation")?,
        secure: controller.mode().await? == WindowManagerMode::KwinLockScreen,
        manual: controller.manual_mode().await?,
        active: kwin.active().await?, supports_text: kwin.active_client_supports_text_input().await?,
    };
    if previous.as_ref() == Some(&state) { return Ok(()); }
    let desired = plan(&state);
    if state.manual != desired.manual {
        controller.change_manual_mode(desired.manual).await?;
    }
    match desired.visibility {
        Some(Visibility::ForceHide) => controller.force_hide().await?,
        Some(Visibility::Hide) => controller.hide().await?,
        Some(Visibility::ShowViaFcitx) => {
            // This sets Fcitx's input-device mode as well as showing the panel.
            FcitxVirtualKeyboardServiceProxy::new(connection).await?.show_virtual_keyboard().await?;
        }
        None => {}
    }
    *previous = Some(state);
    Ok(())
}

pub async fn watch() -> Result<()> {
    let connection = Connection::session().await?;
    let rule = MatchRule::builder().msg_type(Type::Signal).build();
    let mut signals = MessageStream::for_match_rule(rule, &connection, Some(128)).await?;
    let mut previous = None;
    loop {
        // Bound IPC failures without exiting the launcher or spinning a poller.
        match tokio::time::timeout(Duration::from_secs(3), reconcile(&connection, &mut previous)).await {
            Ok(Ok(())) => {}
            Ok(Err(error)) => { previous = None; tracing::warn!("Native keyboard reconciliation: {error}"); }
            Err(_) => { previous = None; tracing::warn!("Native keyboard reconciliation timed out"); }
        }
        loop {
            match signals.next().await {
                Some(Ok(message)) if relevant(&message) => break,
                Some(Ok(_)) => {}
                Some(Err(error)) => return Err(error.into()),
                None => return Ok(()),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn application() -> Snapshot {
        Snapshot { owner: ":1.1".into(), keyboard: false, locked: false, foreground: "application".into(), generation: 1,
            secure: false, manual: false, active: true, supports_text: true }
    }
    #[test]
    fn detached_context_waits_for_manual_ack() {
        let mut s=application();s.manual=true;
        assert_eq!(plan(&s),Plan { manual:false, visibility:None });
        s.manual=false;assert_eq!(plan(&s).visibility,Some(Visibility::ShowViaFcitx));
    }
    #[test]
    fn real_keyboard_preserves_physical_composition() {
        let mut s=application();s.keyboard=true;
        assert_eq!(plan(&s),Plan { manual:true, visibility:Some(Visibility::ForceHide) });
        assert!(s.active); // The plan never deactivates KWin's text context.
    }
    #[test]
    fn focus_controls_show_and_hide() {
        let mut s=application();assert_eq!(plan(&s).visibility,Some(Visibility::ShowViaFcitx));
        s.supports_text=false;assert_eq!(plan(&s).visibility,Some(Visibility::Hide));
        s.supports_text=true;s.active=false;assert_eq!(plan(&s).visibility,Some(Visibility::Hide));
    }
    #[test]
    fn secure_panel_is_never_force_shown() {
        let mut s=application();s.secure=true;
        assert_eq!(plan(&s),Plan { manual:false, visibility:None });
        s.locked=true;assert_eq!(plan(&s).visibility,None);
    }
    #[test]
    fn desktop_residual_context_is_suppressed() {
        let mut s=application();s.foreground="desktop".into();
        assert_eq!(plan(&s),Plan { manual:true, visibility:Some(Visibility::ForceHide) });
    }
    #[test]
    fn returning_from_desktop_waits_for_ack() {
        let mut s=application();s.manual=true;s.generation=2;
        assert_eq!(plan(&s).visibility,None);
        s.manual=false;assert_eq!(plan(&s).visibility,Some(Visibility::ShowViaFcitx));
    }
    #[test]
    fn locking_hides_stale_normal_panel() {
        let mut s=application();s.locked=true;
        assert_eq!(plan(&s),Plan { manual:true, visibility:Some(Visibility::ForceHide) });
        s.secure=true;assert_eq!(plan(&s).visibility,None);
    }
    #[test]
    fn explicitly_focused_drawer_search_is_allowed() {
        let mut s=application();s.foreground="drawer".into();
        assert_eq!(plan(&s).visibility,Some(Visibility::ShowViaFcitx));
    }
    #[test]
    fn unknown_application_role_keeps_input_available() {
        let mut s=application();s.foreground="unknown".into();
        assert_eq!(plan(&s).visibility,Some(Visibility::ShowViaFcitx));
    }
    #[test]
    fn detach_on_password_page_restores_automatic_mode() {
        let mut s=application();s.locked=true;s.secure=true;s.manual=true;
        assert_eq!(plan(&s),Plan { manual:false, visibility:None });
    }
    #[test]
    fn attach_on_password_page_hides_secure_panel() {
        let mut s=application();s.locked=true;s.secure=true;s.keyboard=true;
        assert_eq!(plan(&s),Plan { manual:true, visibility:Some(Visibility::ForceHide) });
    }
    #[test]
    fn dismissed_visibility_is_not_a_reconciliation_trigger() {
        let s=application();let same=s.clone();assert_eq!(Some(&s),Some(&same));
        let message=zbus::Message::signal("/fyi/fortime/Fcitx5Osk/Controller","org.freedesktop.DBus.Properties","PropertiesChanged").unwrap()
            .build(&("fyi.fortime.Fcitx5Osk.Controller1",HashMap::from([("VisibleRequest", zvariant::Value::Bool(false))]),Vec::<String>::new())).unwrap();
        assert!(!relevant(&message));
    }
    #[test]
    fn locking_signal_is_observed_before_compositor_context_changes() {
        for path in ["/ScreenSaver", "/org/freedesktop/ScreenSaver"] {
            let message=zbus::Message::signal(path,"org.freedesktop.ScreenSaver","ActiveChanged").unwrap().build(&(true,)).unwrap();
            assert!(relevant(&message));
        }
    }
}
