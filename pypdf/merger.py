#!/usr/bin/python3
# vim: sw=4:expandtab:foldmethod=marker
#
# Copyright (c) 2006, Mathieu Fenniak
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# * Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
# * The name of the author may not be used to endorse or promote products
# derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
"""
Handles PDF Merging
"""

from .generic import (Bookmark, Destination)                        #pylint: disable=relative-beyond-top-level
from .pdfreader import PdfFileReader                                #pylint: disable=relative-beyond-top-level
from .pdfwriter import PdfFileWriter                                #pylint: disable=relative-beyond-top-level
from .pagerange import PageRange                                    #pylint: disable=relative-beyond-top-level

class PdfFileMerger(PdfFileWriter):                                 #pylint: too hudge change for the moment disable=invalid-name
    """
    PDF Page Merger defined a subclass

    See the functions :meth:`merge()<merge>` (or :meth:`append()<append>`)
    and :meth:`write()<write>` for usage information.

    """
    def __init__(self, output=None, strict=True, pdf_reader_as_source=None, debug=False):
        """
        Initializes a ``PdfFileMerger`` object. ``PdfFileMerger`` merges
        multiple PDFs into a single PDF. It can concatenate, slice, insert, or
        any combination of the above.

        :param output: I/O stream to be used to write the merge results to.
        :param bool strict: Determines whether user should be warned of all
                problems and also causes some correctable problems to be fatal.
                Defaults to ``True``.
                the other parameters pdfReaderAsSource and debug are kept for PdfFileWriter
        """
        super().__init__(output, pdf_reader_as_source, debug)
        self.strict = strict
        self._last_merged_pdf = None

    def merge(self, position, fileobj, bookmark=None, pages=None, import_bookmarks=True, #pylint: too hudge change for the moment disable=too-many-arguments
              prefix_nameddest=""):
        """
        Merges the pages from the given file into the output file at the
        specified page number.

        :param int position: The *page number* to insert this file. File will
            be inserted after the given number.
        :param fileobj: A File Object or an object that supports the standard
            read and seek methods similar to a File Object. Could also be a
            string representing a path to a PDF file.
        :param str bookmark: Optionally, you may specify a bookmark to be
            applied at the beginning of the included file by supplying the text
            of the bookmark.
        :param pages: can be a :ref:`Page Range <page-range>` or a
            ``(start, stop[, step])`` tuple to merge only the specified range
            of pages from the source document into the output document.
        :param bool import_bookmarks: You may prevent the source document's
            bookmarks from being imported by specifying this as ``False``.
        :param str/None prefix_nameddest: None : no named destination will be
            imported else the prefix add to the named destination
            ("" = no prefix added but named destination copied)
        """
        if position is None:
            position = self.num_pages

        if not isinstance(fileobj, PdfFileReader):
            fileobj = PdfFileReader(fileobj, strict=self.strict)
            if fileobj.is_encrypted:
                fileobj.decrypt("")

        if fileobj != self._last_merged_pdf:
            self._last_merged_pdf = fileobj
            self.reset_cloning()


        # Find the range of pages to merge.
        pages = (range(fileobj.num_pages) if pages is None else
                 range(*pages.indices(fileobj.num_pages)) if isinstance(pages, PageRange)
                 else eval(pages) if isinstance(pages, str)
                 else pages if isinstance(pages, tuple)
                 else None)
        assert pages is not None, TypeError('"pages" not good type')

        srcpages = {}
        for i__, p__ in enumerate(pages):
            pp_ = fileobj.pages[p__].indirectRef
            srcpages[pp_.idnum] = self.insert_page(pp_.clone(self), position+i__)

        self.convert_to_bookmarks()
        bkmark = self.add_bookmark(bookmark, position) if bookmark else self.get_outlines_root()

        if import_bookmarks and "/Outlines" in fileobj.root_object:
            self._copy_bookmarks(fileobj.root_object["/Outlines"], bkmark, srcpages)

        if isinstance(prefix_nameddest, str):
            if prefix_nameddest != "":
                self.add_named_destination(prefix_nameddest, position)
            for k__, v__ in fileobj.getNamedDestinations().items():
                if v__.pageref.idnum in srcpages:
                    try:
                        self.add_named_destination_object(v__.clone(self), prefix_nameddest + k__)
                    except AssertionError as e:
                        print(e)

    def append(self, fileobj, bookmark=None, pages=None, import_bookmarks=True):
        """
        Identical to the :meth:`merge()<merge>` method, but assumes you want to
        concatenate all pages onto the end of the file instead of specifying a
        position.

        :param fileobj: A File Object or an object that supports the standard
            read and seek methods similar to a File Object. Could also be a
            string representing a path to a PDF file.
        :param str bookmark: Optionally, you may specify a bookmark to be
            applied at the beginning of the included file by supplying the text
            of the bookmark.
        :param pages: can be a :ref:`Page Range <page-range>` or a
            ``(start, stop[, step])`` tuple to merge only the specified range
            of pages from the source document into the output document.
        :param bool import_bookmarks: You may prevent the source document's
            bookmarks from being imported by specifying this as ``False``.
        """
        self.merge(None, fileobj, bookmark, pages, import_bookmarks)

    def _copy_bookmarks(self, node, bkmark, srcpages):
        """
        copy outlines
        params:
            node : Bookmark/treeObject node to process
            bkmark : bookmark head to put outline below if null they will be straight at root
            srcpages : dict of pages, keyed with the idnum of the original page in pdf source
        """
        #assert isinstance(outlines, list)
        bkmark1 = bkmark # if node does point to the page, we use the parent to attach sub-children
        #if "/Dest" in node:
        try:
            if "/Type" in node and node["/Type"] == "/Outlines":
                raise AttributeError  #nothing to do for outlines_root
            if Destination("", node).pageref.idnum in srcpages:
                bm_ = Bookmark("", node)
                bkmark1 = self._add_object(Bookmark(bm_.title, bm_.dest.clone(self),
                                                    bm_.flag, bm_.color, None, None))
                bkmark.getObject().add_child(bkmark1, self)
        except AttributeError:  # case of the outlines root where
            pass

        if "/First" in node:
            cur_ = node["/First"]
            while True:
                self._copy_bookmarks(cur_, bkmark1, srcpages)
                try:
                    cur_ = cur_["/Next"]
                except KeyError:
                    break
