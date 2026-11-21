#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Configure Linexin Launcher with the native KWin desktop gesture integration."""
import argparse
import datetime
import json
import os
import pathlib
import shutil
import subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launcher-id',help='Plugin ID printed in the drawer build manifest')
    args=parser.parse_args()
    if os.geteuid()==0:
        raise SystemExit('Run as the Plasma desktop user, without sudo')
    import dbus
    launcher=args.launcher_id
    if not launcher:
        root=pathlib.Path.home()/'.local/share/plasma/plasmoids'
        found=[p for p in root.glob('org.sheng.linexin.launcher*') if (p/'metadata.json').is_file()]
        if not found:raise SystemExit('Install the built Linexin package first')
        launcher=json.loads((max(found,key=lambda p:p.stat().st_ctime)/'metadata.json').read_text(encoding='utf-8'))['KPlugin']['Id']
    if not launcher.startswith('org.sheng.linexin.launcher'):raise SystemExit('Unexpected launcher ID')
    bus=dbus.SessionBus()
    plasma=dbus.Interface(bus.get_object('org.kde.plasmashell','/PlasmaShell'),'org.kde.PlasmaShell')
    old_shortcut=json.loads(str(plasma.evaluateScript('var key="";panels().concat(desktops()).forEach(p=>p.widgets().forEach(w=>{if(w.type.indexOf("org.sheng.linexin.launcher")===0||w.type==="org.linexin.launcher"||w.type==="org.kde.plasma.kickerdash")key=String(w.globalShortcut||"");}));print(JSON.stringify(key));',timeout=10)))
    shortcut=old_shortcut
    if not shortcut:
        accel=dbus.Interface(bus.get_object('org.kde.kglobalaccel','/kglobalaccel'),'org.kde.KGlobalAccel')
        candidates=[('Meta+Ctrl+Alt+Shift+D',0x1e000044),('Meta+Ctrl+Alt+Shift+F12',0x1f00003b),('Meta+Ctrl+Alt+Shift+F24',0x1f000047)]
        for label,code in candidates:
            if accel.isGlobalShortcutAvailable(dbus.Int32(code),''):
                shortcut=label;break
        if not shortcut:raise SystemExit('No free drawer activation shortcut; configure the Dashboard shortcut first')
    state=pathlib.Path.home()/'.local/state/sheng-desktop-drawer'
    backup=state/('backup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True,exist_ok=True);backup.chmod(0o700)
    for name in ['plasma-org.kde.plasma.desktop-appletsrc','plasmashellrc']:
        path=pathlib.Path.home()/'.config'/name
        if path.exists():shutil.copy2(path,backup/name)
    script='''
var all=panels();
var preferences={};
var previous=[];panels().concat(desktops()).forEach(p=>p.widgets().forEach(w=>{if(w.type===TARGET)return;if(w.type==="org.kde.plasma.kickerdash"||w.type==="org.linexin.launcher"||w.type.indexOf("org.sheng.linexin.launcher")===0){if(w.type.indexOf("org.sheng.linexin.launcher")===0){w.currentConfigGroup=["General"];Array.from(w.configKeys).forEach(k=>preferences[k]=w.readConfig(k));}w.globalShortcut="";previous.push(w);}}));
var dock=all.find(function(p){p.currentConfigGroup=["General"];return p.readConfig("ShengThemeRole","")==="dock";});
if(!dock)dock=all.find(p=>p.location==="bottom"&&p.widgets().some(w=>w.type==="org.kde.plasma.icontasks"));
if(!dock)throw new Error("Existing Dock panel not found");
dock.currentConfigGroup=["General"];dock.writeConfig("ShengThemeRole","dock");
var oldTasks=dock.widgets().filter(w=>w.type==="org.kde.plasma.icontasks"||w.type==="org.kde.plasma.taskmanager");
var inherited=[];
oldTasks.forEach(function(w){w.currentConfigGroup=["General"];var raw=w.readConfig("launchers",[]);if(typeof raw==="string")raw=raw.split(",");Array.from(raw).forEach(l=>{if(l&&inherited.indexOf(l)<0)inherited.push(l);});});
var dashboard=null;
panels().concat(desktops()).forEach(p=>p.widgets().forEach(w=>{if(w.type===TARGET)dashboard=w;}));
if(!dashboard){
    dashboard=dock.addWidget(TARGET);
    if(!dashboard||dashboard.type!==TARGET)throw new Error("Install the pinned Linexin launcher first");
    dashboard.currentConfigGroup=["General"];
    dashboard.writeConfig("icon","view-grid-symbolic");
    dashboard.writeConfig("launchers",inherited);
    dashboard.writeConfig("defaultCategory",-2);
    dashboard.writeConfig("showAllAppsInDashboard",true);
    dashboard.writeConfig("showActiveApps",true);
    dashboard.writeConfig("appsIconSize",3);
    dashboard.writeConfig("dashboardFontSize",125);
    dashboard.writeConfig("allAppsFontSize",115);
    dashboard.writeConfig("categoryFontSize",110);
    dashboard.writeConfig("animationDuration",200);
    dashboard.writeConfig("iconEntranceDuration",180);
    dashboard.writeConfig("backgroundOpacity",80);
    dashboard.writeConfig("alphaSort",true);
    dashboard.writeConfig("showRecentDocs",false);
    dashboard.writeConfig("showRecentFolders",false);
    dashboard.writeConfig("showRecentApps",false);
    dashboard.writeConfig("useExtraRunners",false);
    dashboard.writeConfig("favoriteSystemActions",[]);
    Object.keys(preferences).forEach(k=>dashboard.writeConfig(k,preferences[k]));
    dashboard.writeConfig("showActiveApps",true);
    dashboard.reloadConfig();
}
if(!dashboard.globalShortcut)dashboard.globalShortcut=ACTIVATION;
previous.forEach(w=>w.remove());
oldTasks.forEach(w=>w.remove());
dock.height=84;dock.minimumLength=1;dock.maximumLength=1100;dock.lengthMode="fit";dock.alignment="center";dock.hiding="windowsgobelow";
dock.widgets().forEach(function(w){
    if(w.type!=="luisbocanegra.panel.colorizer")return;
    w.currentConfigGroup=["General"];
    try{
        var settings=JSON.parse(w.readConfig("globalSettings","{}"));
        ["panel","widgets"].forEach(function(group){
            var states=settings[group]||{};
            Object.keys(states).forEach(function(key){var state=states[key];if(!state||typeof state!=="object")return;state.blurBehind=false;if(state.backgroundColor)state.backgroundColor.enabled=false;if(state.border)state.border.enabled=false;if(state.borderSecondary)state.borderSecondary.enabled=false;if(state.shadow){if(state.shadow.background)state.shadow.background.enabled=false;if(state.shadow.foreground)state.shadow.foreground.enabled=false;}});
        });
        if(settings.nativePanel&&settings.nativePanel.background){settings.nativePanel.background.enabled=false;settings.nativePanel.background.opacity=0;settings.nativePanel.background.shadow=false;}
        w.writeConfig("globalSettings",JSON.stringify(settings));w.reloadConfig();
    }catch(error){}
});
desktops().forEach(d=>d.widgets().filter(w=>w.type.indexOf("org.sheng.desktop-gesture")===0).forEach(w=>w.remove()));
print(JSON.stringify({dashboard:dashboard.id,dock:dock.id}));
'''.replace('ACTIVATION',json.dumps(shortcut)).replace('TARGET',json.dumps(launcher))
    result=json.loads(str(plasma.evaluateScript(script,timeout=15)).strip())
    (state/'installed.json').write_text(json.dumps({'backup':str(backup),'activationShortcut':shortcut,**result},indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
