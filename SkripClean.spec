# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# Списки для сборки
datas = []
binaries = []
hiddenimports = []

# Только необходимые пакеты для метаданных
meta_pkgs = [
    'numpy',
    'pandas',
    'scikit_learn',
    'psutil',
    'tqdm',
]

# Только необходимые пакеты для данных и подмодулей
mod_pkgs = [
    'numpy',
    'pandas',
    'sklearn',
    'psutil',
    'tqdm',
]

# Сбор метаданных
for pkg in meta_pkgs:
    try:
        datas += copy_metadata(pkg)
    except Exception as e:
        print(f"[metadata] ⚠️ {pkg}: {e}")

# Сбор данных и подмодулей
for pkg in mod_pkgs:
    try:
        datas += collect_data_files(pkg)
        hiddenimports += collect_submodules(pkg)
    except Exception as e:
        print(f"[data/submodules] ⚠️ {pkg}: {e}")

# Добавление пользовательских файлов
datas += [
    ('icon1.ico', '.'),
    ('config.json', '.'),
]

a = Analysis(
    ['main_pyqt.py'],
    pathex=[os.getcwd()],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        'win32file', 'win32api', 'wmi', 'sip',
        'PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets',
        'folder_search_cpp', 'winreg', 'threading', 'shutil',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'transformers', 'torch', 'tokenizers', 'huggingface-hub',
        'einops', 'safetensors', 'tensorflow', 'keras',
    ],
    noarchive=False,  # Использовать архив PYZ
    optimize=2,  # Максимальная оптимизация
)

# Удаляем ненужные библиотеки
a.datas = [d for d in a.datas if not any(name in d[0] for name in ['transformers', 'torch', 'tokenizers', 'huggingface'])]

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SkripClean',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,  # Удалить отладочную информацию
    upx=True,    # Включить UPX-сжатие
    upx_exclude=[],  # Ничего не исключать из UPX
    console=False,
    icon='icon1.ico',
    disable_windowed_traceback=True,  # Отключить traceback в GUI
    target_arch=None,
    codesign_identity=None,
    runtime_tmpdir=None,  # Не сохранять во временную папку,
    version='version.txt',  # Добавляем информацию о версии
)
