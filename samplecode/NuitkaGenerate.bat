@rem generation with nuitka
nuitka --standalone --show-progress --show-scons MergingComments.py
nuitka --standalone --nofollow-import-to=pandas --nofollow-import-to=PIL --nofollow-import-to=numpy --show-progress --show-scons PDFComments2XL.py
