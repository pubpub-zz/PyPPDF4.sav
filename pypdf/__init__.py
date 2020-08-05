#!/usr/bin/python3
"""
PyPDF4
init
"""

import sys

from ._version import __version__                                   #pylint: disable=relative-beyond-top-level
from . import utils                                                 #pylint: disable=relative-beyond-top-level
from . import generic                                               #pylint: disable=relative-beyond-top-level
from . import filters                                               #pylint: disable=relative-beyond-top-level
#from . import pdf                                                   #pylint: disable=relative-beyond-top-level
from . import pagerange                                             #pylint: disable=relative-beyond-top-level
from . import merger                                                #pylint: disable=relative-beyond-top-level
from . import xmp                                                   #pylint: disable=relative-beyond-top-level
from .generic import (BooleanObject, ArrayObject, IndirectObject,    #pylint: disable=relative-beyond-top-level
                      FloatObject, NumberObject, NameObject,
                      create_string_object, createStringObject, TextStringObject,
                      DictionaryObject, TreeObject,
                      Destination, PageLabel, Bookmark,)
from .pdfreader import PdfFileReader                                #pylint: disable=relative-beyond-top-level
from .pdfwriter import PdfFileWriter                                #pylint: disable=relative-beyond-top-level
from .pagerange import PageRange                                    #pylint: disable=relative-beyond-top-level
from .merger import PdfFileMerger                                   #pylint: disable=relative-beyond-top-level

sys.setrecursionlimit(max(10000,sys.getrecursionlimit()))

__all__ = [
    # Basic PyPDF elements
    "PdfFileReader",
    "PdfFileWriter",
    "PdfFileMerger",
    "PageRange",
    # most used elements from generic
    "BooleanObject",
    "ArrayObject",
    "IndirectObject",
    "FloatObject",
    "NumberObject",
    "create_string_object",
    "createStringObject",
    "TextStringObject",
    "NameObject",
    "DictionaryObject",
    "TreeObject",
    "Destination",
    "PageLabel",
    "Bookmark",
    # PyPDF modules
    "pdf",
    "generic",
    "utils",
    "filters",
    "merger",
    "pagerange",
    "xmp", ]
