"""py2app build script for Claude Meter.

Usage:
    python setup.py py2app
"""

from setuptools import setup

APP = ["claude_meter/__main__.py"]

DATA_FILES = []

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "assets/icon.icns",
    "plist": {
        "CFBundleName": "Claude Meter",
        "CFBundleDisplayName": "Claude Meter",
        "CFBundleIdentifier": "com.claudemeter.app",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSUIElement": True,  # Hide from Dock (menu bar only)
        "NSHighResolutionCapable": True,
        "CFBundleDocumentTypes": [],
    },
    "packages": ["claude_meter"],
    "includes": [
        "rumps",
        "watchdog",
        "watchdog.observers",
        "watchdog.events",
    ],
}

setup(
    name="Claude Meter",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
