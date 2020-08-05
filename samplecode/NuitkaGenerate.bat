@rem generation with nuitka
if not "%LIB%" == "" goto build
set LIB=c:\Program Files (x86)\Windows Kits\10\Lib\10.0.17763.0\um\x64;c:\Program Files (x86)\Windows Kits\10\Lib\10.0.17763.0\ucrt\x64\;c:\Program Files (x86)\Microsoft Visual Studio\2017\Community\VC\Tools\MSVC\14.16.27023\lib\x64
:build
call nuitka --standalone --show-progress --show-scons MergingComments.py
call nuitka --standalone --nofollow-import-to=pandas --nofollow-import-to=PIL --nofollow-import-to=numpy --show-progress --show-scons PDFComments2XL.py
