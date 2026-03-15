# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['entry.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'rumps',
        'watchdog',
        'watchdog.observers',
        'watchdog.observers.fsevents',
        'watchdog.events',
        'claude_meter',
        'claude_meter.app',
        'claude_meter.config',
        'claude_meter.constants',
        'claude_meter.notifications',
        'claude_meter.utils',
        'claude_meter.watcher',
        'claude_meter.trackers',
        'claude_meter.trackers.claude_code',
        'claude_meter.trackers.api_tracker',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Claude Meter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='Claude Meter',
)

app = BUNDLE(
    coll,
    name='Claude Meter.app',
    icon='assets/icon.icns',
    bundle_identifier='com.claudemeter.app',
    info_plist={
        'LSUIElement': True,
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '0.1.0',
        'CFBundleDisplayName': 'Claude Meter',
    },
)
