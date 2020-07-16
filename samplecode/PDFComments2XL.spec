# -*- mode: python ; coding: utf-8 -*-
import sys
sys.setrecursionlimit(2000)
block_cipher = None


a = Analysis(['PDFComments2XL.py'],
             pathex=['E:\\PyPDF4.git\\PyPDF4\\samplecode'],
             binaries=[],
             datas=[('*.py', '.')],
             #hiddenimports=['pkg_resources','pkg_resources.py2_warn','win32api','win32com'],
             hiddenimports=['openpyxl'],
             hookspath=[],
             runtime_hooks=[],
             #excludes=['pandas','win32com'],
             excludes=[ 'pyi_rth__tkinter','pyi_rth_certifi','pyi_rth_mplconfig','pyi_rth_mpldata','pyi_rth_multiprocessing','pyi_rth_pkgres','pyi_rth_pyqt5','pyi_rth_pyside2','pyi_rth_traitlets','pyi_rth_win32comgenpy','pandas','PIL','numpy' ],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='PDFComments2XL',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='PDFComments2XL')
