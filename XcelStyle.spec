# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for XcelStyle
# Build: pyinstaller XcelStyle.spec

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='XcelStyle',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,       # no terminal window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='XcelStyle',
)

# macOS .app bundle
app = BUNDLE(
    coll,
    name='XcelStyle.app',
    icon=None,
    bundle_identifier='com.xcelstyle.app',
    info_plist={
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleName': 'XcelStyle',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,  # allow dark mode
    },
)
