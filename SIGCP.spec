# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import shutil


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('docs', 'docs'),
        ('app\\templates', 'app\\templates'),
        ('app\\static', 'app\\static'),
        ('app\\translations', 'app\\translations'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SIGCP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon=['docs\\favicon.ico'],
)

# O cliente instalado lê este ficheiro ao lado do executável publicado para
# apresentar as alterações da versão disponível antes de atualizar.
notes_source = Path.cwd() / 'SIGCP_alteracoes.txt'
notes_destination = Path(DISTPATH) / 'SIGCP_alteracoes.txt'
if notes_source.is_file():
    notes_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(notes_source, notes_destination)
