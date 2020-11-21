# -*- coding: utf-8 -*-
#
# vim: sw=4:expandtab:foldmethod=marker
#
# Copyright (c) 2006, Mathieu Fenniak
# Copyright (c) 2007, Ashish Kulkarni <kulkarni.ashish@gmail.com>
#
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
A pure-Python PDF library with an increasing number of capabilities.
See README.md for links to FAQ, documentation, homepage, etc.
"""

from hashlib import md5
import os
import random
import struct
import time
import datetime
import uuid
import warnings
import codecs

from .utils import (is_string, pypdfBytes as by_, ConvertFunctionsToVirtualList, #pylint: disable=relative-beyond-top-level
                    pypdfUnicode, PyPdfError, PdfStreamError, PdfReadError,)
from .generic import (BooleanObject, ArrayObject, IndirectObject,                #pylint: disable=relative-beyond-top-level
                      FloatObject, NumberObject, NameObject, create_string_object,
                      TextStringObject, DictionaryObject, TreeObject, DecodedStreamObject,
                      StreamObject, ContentStream, ByteStringObject, NullObject,
                      RectangleObject, Destination, PageObject, PageLabel, Bookmark)

from .pdfcommon import PdfDocument, _alg33, _alg34, _alg35                       #pylint: disable=relative-beyond-top-level
from .pdfreader import PdfFileReader                                             #pylint: disable=relative-beyond-top-level

__author__ = "Mathieu Fenniak"
__author_email__ = "biziqe@mathieu.fenniak.net"
__maintainer__ = "Phaseit, Inc."
__maintainer_email__ = "PyPDF4@phaseit.net"


class PdfFileWriter(PdfDocument):
    #pylint: already validated api/code disable=too-many-instance-attributes,too-many-public-methods
    """
    PDF document object  in writing mode
    """
    def __init__(self, stream=None, pdf_as_source=None, debug=False):
        """
        This class supports writing PDF files out, given pages produced by
        another class (typically :class:`PdfFileReader<PdfFileReader>`).

        :param stream: File-like object or path to a PDF file in ``str``
            format. If of the former type, the object must support the
            ``write()`` and the ``tell()`` methods.
        :para pdf_as_source: pdfFileReader object :
            if passed, it is cloned into the writer
        :param bool debug: Whether this class should emit debug informations
            (recommended for development). Defaults to False.
        """
        super().__init__(debug)
        self._header = by_("%PDF-1.3")
        self._objects = []  # array of indirect objects
        self._id_translated = {}
        self.stack = None     # to prevent pylint alerts

        # seems to be initialized with encryt
        self._id = None
        self._encrypt = None
        self._encrypt_key = None

        if is_string(stream):
            self._stream = open(stream, "wb")
        else:
            # We rely on duck typing
            self._stream = stream

        if hasattr(self._stream, "mode") and "b" not in self._stream.mode:
            warnings.warn(
                "File <%s> to write to is not in binary mode. It may not be "
                "written to correctly." % self._stream.name)

        if isinstance(pdf_as_source, str):
            pdf_as_source = PdfFileReader(pdf_as_source, strict=False)
            # check if the document has to be decrypted
            if pdf_as_source.is_encrypted and pdf_as_source.decrypt("") == 0:
                raise PdfReadError("can not decrypt", pdf_as_source.filepath)
        if isinstance(pdf_as_source, (PdfFileReader, PdfFileWriter)):
            self.clone(pdf_as_source)
            return
        if pdf_as_source is not None:
            raise PdfReadError("pdf_as_source is not of good type", pdf_as_source)

        # The root of our page tree node.
        pages = DictionaryObject()
        pages.update({NameObject("/Type"): NameObject("/Pages"),
                      NameObject("/Count"): NumberObject(0),
                      NameObject("/Kids"): ArrayObject(),})
        self._pages = self._add_object(pages)

        info = DictionaryObject()
        info.update({NameObject("/Producer"): create_string_object(
            codecs.BOM_UTF16_BE + pypdfUnicode("pypdf").encode("utf-16be"))})
        self._info = self._add_object(info)

        root = DictionaryObject()
        root.update({NameObject("/Type"): NameObject("/Catalog"),
                     NameObject("/Pages"): self._pages,})
        self._root = self._add_object(root)

    def __repr__(self):
        return "<%s.%s _stream=%s, _header=%s, is_closed=%s, debug=%s>" % (
            self.__class__.__module__, self.__class__.__name__,
            self._stream, self._header.decode(), self.is_closed, self.debug,)

    def __del__(self):
        self.close()
        for a__ in ("_objects", "_stream", "_pages", "_info", "root_object", "_root"):
            if hasattr(self, a__):
                delattr(self, a__)

    def close(self):
        """
        Deallocates file-system resources associated with this
        ``PdfFileWriter`` instance.
        """
        try:
            self._stream.flush()
            self._stream.close()
        except:                             #pylint: disable=bare-except
            pass

    def clone(self, pdf_source): #ppZZ
                                            #pylint: disable=protected-access
        """ clone document """
        #we reset the _object
        self._objects = []  # array of indirect objects
        self._id_translated = {}
        if hasattr(pdf_source, "_trailer"): # in this case this is a PdfFileReader
            _ = pdf_source._trailer["/Root"]["/Pages"].clone(self)
            tr_ = pdf_source._trailer.clone(self)
            self._add_object(tr_)		#PPzz must have trailer in _objects???
            self._root = tr_.rawGet("/Root")
            self._pages = tr_["/Root"].rawGet("/Pages")
            self._info = tr_.rawGet("/Info") if pdf_source._info is not None else None
        else:
            self._root = pdf_source._root.clone(self)
            self._pages = self.root_object.rawGet("/Pages")
            self._info = pdf_source._info.clone(self)
            i__, j__ = len(self._objects), len(pdf_source._objects)
            if i__ != j__:
                warnings.warn("Number of cloned objects is not matching (%d vs %d), may be normal"%
                              (i__, j__))
        self.get_outlines_root()        # in order to change type of "/Outlines"

    def reset_cloning(self):
        """ reset the translation table. to be done before cloning from an other document """
        self._id_translated = {}

    def _add_object(self, obj):
        self._objects.append(obj)
        return IndirectObject(len(self._objects), 0, self)

    def get_object(self, ido):               #pylint: too hudge change for the moment disable=invalid-name
        """ return the object which is pointed by the indirectObject ido """
        if ido.pdf is not self:
            raise ValueError("ido.pdf must be self")

        return self._objects[ido.idnum - 1]
    getObject = get_object

    def _insert_page(self, page, page_number):
        self._reset_pageid_to_num()      #page reference table has to be regenerated
        if not isinstance(page, IndirectObject):
            assert page["/Type"] == "/Page"
            page = self._add_object(page)
        else:
            assert page.getObject()["/Type"] == "/Page"
            if page.pdf != self:   # ensure the page does not require cloning
                page = page.clone(self)

        pn_ = self._pages.getObject()["/Count"]
        if pn_ == 0:
            pp_ = self._pages
            pages = pp_.getObject()
            first_pagenum = 0
        else:
            if page_number >= pn_:
                next_page, first_pagenum = self._get_page(pn_-1, self._pages, 0)
                page_number = pn_
            else:
                next_page, first_pagenum = self._get_page(page_number, self._pages, 0)
            next_page = next_page.getObject()
            pages = next_page["/Parent"]
            pp_ = next_page.rawGet("/Parent")
        page.getObject()[NameObject("/Parent")] = pp_
        pages["/Kids"].insert(page_number-first_pagenum, page)
        while True:
            pp1 = pp_.getObject()
            pp1[NameObject("/Count")] = NumberObject(pp1["/Count"] + 1)
            try:
                pp_ = pp1.rawGet("/Parent")
            except KeyError:
                break
        return page

    def add_page(self, page):                            #pylint: too hudge change for the moment disable=invalid-name
        """
        Adds a page to this PDF file.  The page is usually acquired from a
        :class:`PdfFileReader<PdfFileReader>` instance.

        :param PageObject page: The page to add to the document. Should be
            an instance of :class:`PageObject<pypdf.pdf.PageObject>`
        """
        return self.insert_page(page, self._pages.getObject()["/Count"])
    addPage = add_page

    def insert_page(self, page, index=0):                #pylint: too hudge change for the moment disable=invalid-name
        """
        Insert a page in this PDF file. The page is usually acquired from a
        :class:`PdfFileReader<PdfFileReader>` instance.

        :param PageObject page: The page to add to the document.  This argument
            should be an instance of :class:`PageObject<pdf.PageObject>`.
        :param int index: Position at which the page will be inserted.
        """
        assert 0 <= index <= self._pages.getObject()["/Count"]
        return self._insert_page(page, index)
    insertPage = insert_page

    def _get_page(self, page_num, node, first_pagenum): #ppZZ
        """
        internal
        :param int page_num: page searched for
        :param IndirectObject node: point to a page or pages within the page tree
        :param int first_pagenum: page number of the first page of the tree below
        """
        if node.getObject()["/Type"] == "/Page":   # it is only one page we have to check
            if page_num == first_pagenum:
                return node, -1  #One Page is not a group, we have to return -1
                                 # in order to return the 1st page number of the group
            return first_pagenum+1, -1   # return next first page number
        if first_pagenum <= page_num < first_pagenum+node.getObject()["/Count"]:
                                         # the page is within the kids or subkids
            ret = first_pagenum  #init loop
            node = node.getObject()
            for k__ in node["/Kids"]:
                ret, ret2 = self._get_page(page_num, k__, ret)
                if isinstance(ret, IndirectObject): # page found
                    if ret2 < 0:
                        ret2 = first_pagenum
                    return ret, ret2  # we have the result and push-it up in the recursive call
            raise Exception("nb of pages not iaw count")
        return first_pagenum+node.getObject()["/Count"], -1
                                           #not found, provide first_pagenum for next possible group


    def get_page(self, page_number, ref=False):
        """
        Retrieves a page by number from this PDF file.

        :param int page_number: The page number to retrieve
            (pages begin at zero).
        :param boolean ref: return IndirectObject if True else the object (default: False)
        :return: the page at the index given by *page_number* or if not foudn the number of pages
        :rtype: :class:`PageObject<pdf.PageObject>`
        """
        assert 0 <= page_number < self.num_pages,\
                       "PageNumber(%d) Out of pages range [0-%d]"%(page_number, self.num_pages-1)
        t__ = self._get_page(page_number, self._pages.getObject(), 0)[0]
        if isinstance(t__, int): #not found return the number of pages...
            return t__
        if ref:
            return t__
        return t__.getObject()
    getPage = get_page
    pages = property(
        lambda self: ConvertFunctionsToVirtualList(lambda: self.num_pages, self.get_page)
    )

    def remove_page(self, page_num): #pylint: too hudge change for the moment disable=invalid-name
        """ remove page from table; return indirect_object to the removed page """
        def _remove_page(self, page_num, node, first_pagenum):
            """
            :param int page_num: page searched for
            :param IndirectObject node: point to a page or pages within the page tree
            :param int first_pagenum: page number of the first page of the tree below
            returns : node,nextpage_or_result    result = -1 => remove node => -2 => decrease count
            """
            if node.getObject()["/Type"] == "/Page":   # it is only one page we have to check
                if page_num == first_pagenum:
                    return node, -1            # it is the page to be removed => return -1
                return None, first_pagenum+1   # return next first page number
            if first_pagenum <= page_num < first_pagenum+node.getObject()["/Count"]:
                                              # the page is within the kids or subkids
                ret = first_pagenum  #init loop
                node = node.getObject()
                for i__, k__ in enumerate(node["/Kids"]):
                    node2, ret = _remove_page(self, page_num, k__, ret)
                    if ret == -1: # page found
                        del node["/Kids"][i__]
                        node[NameObject("/Count")] = NumberObject(node["/Count"]-1)
                        return node2, -1 if node["/Count"] == 0 else -2
                    if ret == -2: # page found at a lower level
                        node[NameObject("/Count")] = NumberObject(node["/Count"]-1)
                        return node2, -2 # we have the result and push-it up in the recursive call
                raise Exception("nb of pages not iaw count")
            return None, first_pagenum+node.getObject()["/Count"]
                                    #not found, provide first_pagenum for next possible group
        if not 0 <= page_num < self.num_pages:
            return None
        self._reset_pageid_to_num()      #page reference table has to be regenerated
        return _remove_page(self, page_num, self._pages, 0)[0]
    removePage = remove_page

    def get_num_pages(self):
        """
        :return: the number of pages.
        :rtype: int
        """
        return int(self._pages.getObject()[NameObject("/Count")])
    getNumPages = get_num_pages
    numPages = num_pages = property(get_num_pages)

    def add_blank_page(self, width=None, height=None):            #pylint: too hudge change for the moment disable=invalid-name
        """
        Appends a blank page to this PDF file and returns it. If no page size
        is specified, use the size of the last page.

        :param float width: The width of the new page expressed in default user
            space units.
        :param float height: The height of the new page expressed in default
            user space units.
        :return: the newly appended page
        :rtype: :class:`PageObject<pypdf.pdf.PageObject>`
        :raises PageSizeNotDefinedError: if width and height are not defined
            and previous page does not exist.
        """
        self._reset_pageid_to_num()      #page reference table has to be regenerated
        page = PageObject.createBlankPage(self, width, height)
        self.add_page(page)

        return page
    addBlankPage = add_blank_page

    def insert_blank_page(self, width=None, height=None, index=0):#pylint: too hudge change for the moment disable=invalid-name
        """
        Inserts a blank page to this PDF file and returns it. If no page size
        is specified, use the size of the last page.

        :param float width: The width of the new page expressed in default user
            space units.
        :param float height: The height of the new page expressed in default
            user space units.
        :param int index: Position to add the page.
        :return: the newly appended page
        :rtype: :class:`PageObject<pypdf.pdf.PageObject>`
        :raises PageSizeNotDefinedError: if width and height are not defined
            and previous page does not exist.
        """
        if width is None or height is None and (self.num_pages - 1) >= index:
            oldpage = self.get_page(index)
            width = oldpage.mediaBox.get_width()
            height = oldpage.mediaBox.get_height()
        self._reset_pageid_to_num()      #page reference table has to be regenerated

        page = PageObject.createBlankPage(self, width, height)
        self.insert_page(page, index)

        return page
    insertBlankPage = insert_blank_page

    def add_js(self, javascript):                                #pylint: too hudge change for the moment disable=invalid-name
        """
        Add a Javascript code snippet to be launched upon this PDF opening.\n
        As an example, this will launch the print window when the PDF is
        opened:\n
        writer.add_js(\
            "this.print({bUI:true,bSilent:false,bShrinkToFit:true});"\\
        )\

        :param str javascript: Javascript code.
        """
        js_ = DictionaryObject()
        js_.update(
            {
                NameObject("/Type"): NameObject("/Action"),
                NameObject("/S"): NameObject("/JavaScript"),
                NameObject("/JS"): create_string_object(javascript),
            }
        )
        js_indirect_object = self._add_object(js_)

        # We need a name for parameterized javascript in the pdf file, but it
        # can be anything.
        js_string_name = str(uuid.uuid4())

        js_name_tree = DictionaryObject()
        js_name_tree.update(
            {
                NameObject("/JavaScript"): DictionaryObject(
                    {
                        NameObject("/Names"): ArrayObject(
                            [create_string_object(js_string_name), js_indirect_object]
                        )
                    }
                )
            }
        )
        self._add_object(js_name_tree)

        self.root_object.update(
            {
                NameObject("/JavaScript"): js_indirect_object,
                NameObject("/Names"): js_name_tree,
            }
        )
    addJS = add_js

    def add_attachment(self, fname, fdata):              #pylint: too hudge change for the moment disable=invalid-name
        """
        Embed a file inside the PDF.

        :param str fname: The filename to display.
        :param str fdata: The data in the file.

        Reference:
        https://www.adobe.com/content/dam/Adobe/en/devnet/acrobat/pdfs/PDF32000_2008.pdf
        Section 7.11.3
        """
        # We need three entries:
        # * The file's data
        # * The /Filespec entry
        # * The file's name, which goes in the Catalog

        # The entry for the file
        """ Sample:
        8 0 obj
        <<
            /Length 12
            /Type /EmbeddedFile
        >>
        stream
        Hello world!
        endstream
        endobj
        """
        file_entry = DecodedStreamObject()
        file_entry.set_data(fdata)
        file_entry.update({NameObject("/Type"): NameObject("/EmbeddedFile")})

        # The Filespec entry
        """Sample:
        7 0 obj
        <<
         /Type /Filespec
         /F (hello.txt)
         /EF << /F 8 0 R >>
        >>
        """
        ef_entry = DictionaryObject()
        ef_entry.update({NameObject("/F"): file_entry})

        filespec = DictionaryObject()
        filespec.update(
            {
                NameObject("/Type"): NameObject("/Filespec"),
                # Perhaps also try TextStringObject
                NameObject("/F"): create_string_object(fname),
                NameObject("/EF"): ef_entry,
            }
        )

        # Then create the entry for the root, as it needs a reference to the
        # Filespec
        """Sample:
        1 0 obj
        <<
            /Type /Catalog
            /Outlines 2 0 R
            /Pages 3 0 R
            /Names << /EmbeddedFiles << /Names [(hello.txt) 7 0 R] >> >>
        >>
        endobj

        """
        embedded_filenames_dict = DictionaryObject()
        embedded_filenames_dict.update(
            {NameObject("/Names"): ArrayObject([create_string_object(fname), filespec])}
        )

        embbedded_files_dict = DictionaryObject()
        embbedded_files_dict.update(
            {NameObject("/EmbeddedFiles"): embedded_filenames_dict}
        )
        # Update the root
        self.root_object.update({NameObject("/Names"): embbedded_files_dict})
    addAttachement = add_attachment

    def attach_files(self, files, cut_paths=True):       #pylint: too hudge change for the moment disable=invalid-name
        """
        Embed multiple files inside the PDF.
        Similar to add_attachment but receives a file path or a list of file paths.
        Allows attaching more than one file.

        :param files: Single file path (string) or multiple file paths (list of strings).
        :param cut_paths: Display file name only in PDF if True,
                        else display full parameter string or list entry.
        """
        if not isinstance(files, list):
            files = [files]
        files_array = ArrayObject()

        for file in files:
            fname = file
            if cut_paths:
                fname = os.path.basename(fname)
            fdata = open(file, "rb").read()

            # The entry for the file
            file_entry = DecodedStreamObject()
            file_entry.set_data(fdata)
            file_entry.update({NameObject("/Type"): NameObject("/EmbeddedFile")})

            # The Filespec entry
            ef_entry = DictionaryObject()
            ef_entry.update({NameObject("/F"): file_entry})

            filespec = DictionaryObject()
            filespec.update(
                {
                    NameObject("/Type"): NameObject("/Filespec"),
                    NameObject("/F"): create_string_object(fname),
                    NameObject("/EF"): ef_entry,
                }
            )

            files_array.extend([create_string_object(fname), filespec])

        # The entry for the root
        embedded_filenames_dict = DictionaryObject()
        embedded_filenames_dict.update({NameObject("/Names"): files_array})

        embbedded_files_dict = DictionaryObject()
        embbedded_files_dict.update(
            {NameObject("/EmbeddedFiles"): embedded_filenames_dict}
        )

        # Update the root
        self.root_object.update({NameObject("/Names"): embbedded_files_dict})
    attachFiles = attach_files

    def append_page_from_reader(self, reader, after_page_append=None):      #pylint: too hudge change for the moment disable=invalid-name
        """
         Copy pages from reader to writer. Includes an optional callback
         parameter which is invoked after pages are appended to the writer.

         :param reader: a PdfFileReader object from which to copy page
             annotations to this writer object.  The writer's annots will then
             be updated.
         :param after_page_append: Callback function that is invoked after each
             page is appended to the writer. Takes a ``writerPageref`` argument
             that references to the page appended to the writer.
         """
        self._reset_pageid_to_num()      #page reference table has to be regenerated
        # Get page count from writer and reader
        reader_numpages = reader.num_pages
        writer_numpages = self.num_pages

        # Copy pages from reader to writer
        for rpagenum in range(reader_numpages):
            self.add_page(reader.get_page(rpagenum))
            writer_page = self.get_page(writer_numpages + rpagenum)

            # Trigger callback, pass writer page as parameter
            if callable(after_page_append):
                after_page_append(writer_page)
    appendPagesFromReader = append_page_from_reader

    @staticmethod
    def update_page_form_field_values(page, fields):                        #pylint: too hudge change for the moment disable=invalid-name
        """
        Update the form field values for a given page from a fields dictionary.
        Copy field texts and values from fields to page.

        :param page: Page reference from PDF writer where the annotations and
            field data will be updated.
        :param fields: a Python dictionary of field names (/T) and text values
            (/V).
        """
        # Iterate through the pages and update field values
        for j__ in range(len(page["/Annots"])):
            writer_annot = page["/Annots"][j__].getObject()

            for field, value in fields.items():
                if writer_annot.get("/T") == field:
                    writer_annot.update({NameObject("/V"): TextStringObject(value)})
    updatePageFormFieldValues = update_page_form_field_values

    def cloneReaderDocumentRoot(self, reader):                          #pylint: too hudge change for the moment disable=invalid-name
        """
        Copy the reader document root to the writer.

        :param reader: ``PdfFileReader`` from the document root that should be
            copied.
        """
        #analysed, seems not very clever with now clone function
        #self._root = reader._trailer.rawGet("/Root")
        self._root = reader._root                                               #pylint: disable=protected-access

    def clone_document_from_reader(self, reader, after_page_append=None):       #pylint: too hudge change for the moment disable=invalid-name
        """
        Create a clone of a document from a PDF file reader.

        :param reader: PDF file reader instance from which the clone
            should be created.
        :param after_page_append: Callback function that is invoked after each
            page is appended to the writer. Takes as a single argument a
            reference to the page appended.
        """
        #self.cloneReaderDocumentRoot(reader)
        #self.appendPagesFromReader(reader, after_page_append)
        self.clone(reader)
        self._reset_pageid_to_num()      #page reference table has to be regenerated
        if after_page_append is not None:
            for i__ in range(self.num_pages):
                # it is no exactly after each append, but the way things are done,...
                after_page_append(self.get_page(i__))
    cloneDocumentFromReader = clone_document_from_reader

    def encrypt(self, user_pwd, owner_pwd=None, use128bits=True, permits=None,             #pylint: too hudge change for the moment disable=invalid-name
                can_print=True, can_modify=True, can_copy=True, can_annotate=True,
                can_fill=True, can_extract=True, can_assemble=True, print_fullquality=True):
        """
        Encrypt this PDF file with the PDF Standard encryption handler.

        :param str userPwd: The "user password", which allows for opening and
            reading the PDF file with the restrictions provided.
        :param str ownerPwd: The "owner password", which allows for opening the
            PDF files without any restrictions.  By default, the owner password
            is the same as the user password.
        :param bool use128bits: flag as to whether to use 128bit encryption.
            When false, 40bit encryption will be used.  By default, this flag
            is on.
        """
        # TO-DO Clean this method's code, as it fires up many code linting
        # warnings
        if owner_pwd is None:
            owner_pwd = user_pwd
        if use128bits:
            v__ = 2
            rev = 3
            keylen = int(128 / 8)
        else:
            v__ = 1
            rev = 2
            keylen = int(40 / 8)
        # Permit : cf PDF32000 Table 22
        if permits:
            p__ = permits
        else:
            p__ = -(4 +(0 if can_print else (1<<2))
                    +(0 if can_modify else (1<<3))
                    +(0 if can_copy else (1<<4))
                    +(0 if can_annotate else (1<<5))
                    +(0 if can_fill else (1<<8))
                    +(0 if can_extract else (1<<9))
                    +(0 if can_assemble else (1<<10))
                    +(0 if print_fullquality else (1<<11)))
        o__ = ByteStringObject(_alg33(owner_pwd, user_pwd, rev, keylen))
        id_1 = ByteStringObject(md5(by_(repr(time.time()))).digest())
        id_2 = ByteStringObject(md5(by_(repr(random.random()))).digest())
        self._id = ArrayObject((id_1, id_2))

        if rev == 2:
            u__, key = _alg34(user_pwd, o__, p__, id_1)
        else:
            assert rev == 3
            u__, key = _alg35(user_pwd, rev, keylen, o__, p__, id_1, False)

        encrypt = DictionaryObject()
        encrypt[NameObject("/Filter")] = NameObject("/Standard")
        encrypt[NameObject("/V")] = NumberObject(v__)

        if v__ == 2:
            encrypt[NameObject("/Length")] = NumberObject(keylen * 8)

        encrypt[NameObject("/R")] = NumberObject(rev)
        encrypt[NameObject("/O")] = ByteStringObject(o__)
        encrypt[NameObject("/U")] = ByteStringObject(u__)
        encrypt[NameObject("/P")] = NumberObject(p__)
        self._encrypt = self._add_object(encrypt)
        self._encrypt_key = key

    def write(self, stream=None):
        #pylint: already validated api/code disable=too-many-locals,too-many-branches,too-many-statements
        """
        Writes the collection of pages added to this object out as a PDF file.

        :param stream: An object to write the file to.  The object must support
            the write method and the tell method, similar to a file object.
            if empty use the parameter passed through __init__
        """
        if isinstance(stream, str): #ppZZ
            with open(stream, "wb") as f__:
                self.write(f__)
            return

        if hasattr(stream, "mode") and "b" not in stream.mode:
            warnings.warn(("File <%s> to write to is not in binary mode. "
                           "It may not be written to correctly.")%(stream.name,))

        if stream is not None:
            saved_stream = self._stream
            self._stream = stream
            try:
                self.write()
            finally:
                self._stream = saved_stream
            return

        #seems now useless cas root_object is computed from _root
        #if not self._root:
        #    self._root = self._add_object(self.root_object)

        external_ref_map = {}

        # PDF objects sometimes have circular references to their /Page objects
        # inside their object tree (for example, annotations).  Those will be
        # indirect references to objects that we've recreated in this PDF.  To
        # address this problem, PageObject's store their original object
        # reference number, and we add it to the external reference map before
        # we sweep for indirect references.  This forces self-page-referencing
        # trees to reference the correct new object location, rather than
        # copying in a new copy of the page object.
        for obj_idx in range(len(self._objects)):
            obj = self._objects[obj_idx]

            if isinstance(obj, PageObject) and obj.indirectRef is not None:
                data = obj.indirectRef

                if data.pdf not in external_ref_map:
                    external_ref_map[data.pdf] = {}
                if data.generation not in external_ref_map[data.pdf]:
                    external_ref_map[data.pdf][data.generation] = {}
                external_ref_map[data.pdf][data.generation][data.idnum] = \
                    IndirectObject(obj_idx + 1, 0, self)

        # TO-DO Instance attribute defined outside __init__(). Carefully move
        # it out of here
        self.stack = []
        self._sweepIndirectReferences(external_ref_map, self._root)
        del self.stack

        # Begin writing:
        object_positions = []
        self._stream.write(self._header + by_("\n"))
        self._stream.write(by_("%\xE2\xE3\xCF\xD3\n"))

        for i in range(len(self._objects)):
            idnum = i + 1
            obj = self._objects[i]
            object_positions.append(self._stream.tell())
            self._stream.write(by_(str(idnum) + " 0 obj\n"))
            key = None

            if (hasattr(self, "_encrypt") and self._encrypt is not None
                    and idnum != self._encrypt.idnum):
                pack1 = struct.pack("<i", i + 1)[:3]
                pack2 = struct.pack("<i", 0)[:2]
                key = self._encrypt_key + pack1 + pack2
                assert len(key) == (len(self._encrypt_key) + 5)
                md5_hash = md5(key).digest()
                key = md5_hash[: min(16, len(self._encrypt_key) + 5)]
            obj.writeToStream(self._stream, key)
            self._stream.write(by_("\nendobj\n"))

        # xref table
        xref_location = self._stream.tell()
        self._stream.write(by_("xref\n"))
        self._stream.write(by_("0 %s\n" % (len(self._objects) + 1)))
        self._stream.write(by_("%010d %05d f \n" % (0, 65535)))

        for offset in object_positions:
            self._stream.write(by_("%010d %05d n \n" % (offset, 0)))

        self._stream.write(by_("trailer\n"))
        trailer = DictionaryObject()
        trailer.update(
            {
                NameObject("/Size"): NumberObject(len(self._objects) + 1),
                NameObject("/Root"): self._root,
                NameObject("/Info"): self._info,
            }
        )

        if hasattr(self, "_id") and self._id is not None:
            trailer[NameObject("/ID")] = self._id
        if hasattr(self, "_encrypt") and self._encrypt is not None:
            trailer[NameObject("/Encrypt")] = self._encrypt

        trailer.writeToStream(self._stream, None)

        # EOF
        self._stream.write(by_("\nstartxref\n%s\n%%%%EOF\n" % xref_location))

    def add_metadata(self, infos):                               #pylint: too hudge change for the moment disable=invalid-name
        """
        Add custom metadata to the output.

        :param dict infos: a Python dictionary where each key is a field
            and each value is your new metadata.
        """
        if isinstance(infos, DictionaryObject):
            args = DictionaryObject()
            for key, value in list(infos.items()):
                args[NameObject(key)] = create_string_object(value)

        self._info.getObject().update(args)
    addMetadata = add_metadata

    def _sweepIndirectReferences(self, extern_map, data):        #pylint: too hudge change for the moment disable=invalid-name
        #pylint:  already validated code disable=too-many-return-statements,too-many-branches
        if self.debug:
            print(data, "TYPE", data.__class__.__name__)

        if isinstance(data, DictionaryObject):
            for key, value in data.items():
                value = self._sweepIndirectReferences(extern_map, value)

                if isinstance(value, StreamObject):
                    # a dictionary value is a stream.  streams must be indirect
                    # objects, so we need to change this value.
                    value = self._add_object(value)
                data[key] = value

            return data
        if isinstance(data, ArrayObject):
            for i__, v__ in enumerate(data):
                value = self._sweepIndirectReferences(extern_map, v__)
                if isinstance(value, StreamObject):
                    # An array value is a stream.  streams must be indirect
                    # objects, so we need to change this value
                    value = self._add_object(value)
                data[i__] = value
            return data
        if isinstance(data, IndirectObject):
            # Internal indirect references are fine
            if data.pdf == self:
                if data.idnum in self.stack:
                    return data
                self.stack.append(data.idnum)
                realdata = self.getObject(data)
                self._sweepIndirectReferences(extern_map, realdata)
                return data
            if data.pdf.isClosed:
                raise ValueError("I/O operation on closed file: %s" % (data.pdf._stream.name,))
            newobj = extern_map.get(data.pdf, {}).get(data.generation, {}).get(data.idnum, None)

            if newobj is None:
                try:
                    newobj = data.pdf.getObject(data)
                    self._objects.append(None)  # placeholder
                    idnum = len(self._objects)
                    newobj_ido = IndirectObject(idnum, 0, self)

                    if data.pdf not in extern_map:
                        extern_map[data.pdf] = {}
                    if data.generation not in extern_map[data.pdf]:
                        extern_map[data.pdf][data.generation] = {}

                        extern_map[data.pdf][data.generation][data.idnum] = newobj_ido
                        newobj = self._sweepIndirectReferences(extern_map, newobj)
                        self._objects[idnum - 1] = newobj

                        return newobj_ido
                except (ValueError, PyPdfError):
                    # Unable to resolve the Object, returning NullObject
                    # instead.
                    warnings.warn(
                        "Unable to resolve [{}: {}], returning NullObject instead".format(
                            data.__class__.__name__, data)
                    )
                    return NullObject()
                return newobj
        return data

    def get_reference(self, obj):                       #pylint: too hudge change for the moment disable=invalid-name
        """
        return the indirect object pointing to obj;
        remember that a ValueError is raised when obj does not belong to the object
        """
        idnum = self._objects.index(obj) + 1
        ref = IndirectObject(idnum, 0, self)

        assert ref.getObject() == obj

        return ref
    getReference = get_reference

    def get_outlines_root(self):                           #pylint: too hudge change for the moment disable=invalid-name
        """ return the root of the outlines """
        if ("/Outlines" in self.root_object
                and not isinstance(self.root_object["/Outlines"], NullObject)):
            _outlines = self.root_object["/Outlines"]
            if not isinstance(_outlines, TreeObject):
                new_o = TreeObject()
                new_o.update(_outlines)
                outlines_ref = self.get_reference(_outlines)
                _outlines = self._objects[outlines_ref.idnum-1] = new_o
        else:
            _outlines = TreeObject()
            _outlines.update({NameObject("/Type"):NameObject("/Outlines")})
            outlines_ref = self._add_object(_outlines)
            self.root_object[NameObject("/Outlines")] = outlines_ref

        return _outlines

    #Copied from Reader
    @staticmethod
    def _build_destination(title, array):
        if isinstance(array, Destination):
            return array
        return Destination(title, page_or_dest_or_array=array[0], typ=array[1], zargs=array[2:])

    def get_named_destinations(self, tree=None, retval=None):             #pylint: too hudge change for the moment disable=invalid-name
        #pylint: already validated code disable=too-many-branches
        """
        Retrieves the named destinations present in the document.

        :return: a dictionary which maps names to
            :class:`Destinations<pypdf.generic.Destination>`.
        :rtype: dict
        """
        if retval is None:
            retval = {}
            catalog = self.root_object

            # get the name tree
            if "/Dests" in catalog:
                tree = catalog["/Dests"]
            elif "/Names" in catalog:
                names = catalog["/Names"]
                if "/Dests" in names:
                    tree = names["/Dests"]

        if tree is None:
            return retval

        if "/Kids" in tree:
            # recurse down the tree
            for kid in tree["/Kids"]:
                self.get_named_destinations(kid.getObject(), retval)

        elif "/Names" in tree: #ppZZ if => elif
            names = tree["/Names"]
            for i in range(0, len(names), 2):
                key = names[i].getObject()
                val = names[i+1].getObject()

                if isinstance(val, DictionaryObject) and "/D" in val:
                    val = val["/D"]

                dest = self._build_destination(key, val)
                if dest is not None:
                    retval[key] = dest
        else:  # case where Dests is in root catalog
            for k__, v__ in tree.items():
                val = v__.getObject()
                if isinstance(val, DictionaryObject) and "/D" in val:
                    val = val["/D"]
                dest = self._build_destination(k__, val)
                if dest is not None:
                    retval[k__] = dest

        return retval
    getNamedDestinations = get_named_destinations
    namedDestinations = named_destinations = property(get_named_destinations)

    def convert_to_bookmarks(self, node=None):
        """ convert the outlines dictionnaries to bookmark objects """
        #if not isinstance(node, IndirectObject):
        #    node = self.get_reference(node)
        if node is None:
            if "/Outlines" not in self.root_object:
                return
            node = self.root_object["/Outlines"]
        else:
            if not isinstance(node.getObject(), Bookmark):
                self._objects[node.idnum-1] = Bookmark("", self._objects[node.idnum-1])
            node = node.getObject()
        if "/First" in node:
            cur_ = node.rawGet("/First")
            while True:
                self.convert_to_bookmarks(cur_)
                try:
                    cur_ = cur_.getObject().rawGet("/Next")
                except KeyError:
                    break

    def add_bookmark_from_dict(self, bookmark, parent=None, before=None):
        """ add a bookmark destination defined by a dictionnary ("""
        bookmark_obj = Bookmark()

        for k__, v__ in list(bookmark.items()):
            bookmark_obj[NameObject(str(k__))] = v__
        bookmark_obj.update(bookmark)

        if "/A" in bookmark:
            action = DictionaryObject()
            for k__, v__ in list(bookmark["/A"].items()):
                action[NameObject(str(k__))] = v__
            action_ref = self._add_object(action)
            bookmark_obj[NameObject("/A")] = action_ref

        bookmark_ref = self._add_object(bookmark_obj)
        outline_ref = self.get_outlines_root()

        if parent is None:
            parent = outline_ref

        parent = parent.getObject()
        parent.add_child(bookmark_ref, self, before)

        return bookmark_ref
    add_outline_from_dict = addBookmarkDict = add_bookmark_from_dict

    #bookmarks are added in
    def add_bookmark_object(self, bookmark, parent=None, before=None):
        """
        add a prebuilt bookmark destination below parent(None meant to)
        and set before(None means at the end)
        """
        bm_ref = self._add_object(bookmark.getObject()) # I prefer to always add a new object
        if "/Dest" not in bookmark:
            bookmark[NameObject("/Dest")] = Destination(bookmark.title, bookmark)

        if parent is None:
            parent = self.get_outlines_root()

        parent = parent.getObject()
        parent.add_child(bm_ref, self, before)

        return bm_ref
    add_outline_from_bookmark = addBookmarkObject = add_bookmark_object

    def add_bookmark(self, title, pagenum, parent=None, before=None,                            #pylint: too hudge change for the moment disable=too-many-arguments
                     color=None, bold=False, italic=False, fit="/Fit", zoom_args=()):
        """
        Add a bookmark to this PDF file.

        :param str title: Title to use for this bookmark.
        :param int pagenum: Page number this bookmark will point to.
        :param parent: A reference to a parent bookmark to create nested bookmarks.
        :param tuple color: Color of the bookmark as a RGB tuple from 0.0 to 1.0
        :param bool bold: Bookmark is bold
        :param bool italic: Bookmark is italic
        :param str fit: The fit of the destination page.
                        See :meth:`add_link()<add_link>` for details.
        :param args : The zoom arg
        """
        def build_bm():
            zoom_a = [NumberObject(x) for x in zoom_args]
            return Bookmark(create_string_object(title),
                            page_or_dest_or_array=page_ref, typ=NameObject(fit), zargs=zoom_a)

        page_ref = self.get_page(pagenum, True)

        if parent is None:
            parent = self.get_outlines_root()

        bookmark = build_bm()

        if color is not None:
            bookmark.update(
                {NameObject("/C"): ArrayObject([FloatObject(c) for c in color])}
            )

        if italic or bold:
            bookmark.update({NameObject("/F"): NumberObject(1*italic+2*bold)})

        bookmark_ref = self._add_object(bookmark)

        parent = parent.getObject()
        parent.add_child(bookmark_ref, self, before)

        return bookmark_ref
    add_outline = addBookmark = add_bookmark

    def add_named_destination_object(self, dest, title=None):                  #pylint: too hudge change for the moment disable=invalid-name
        """ add a named destination object """
        def _get_min_or_max_key(node, _min=True):
            if "/Names" in node:
                return node["/Names"][0 if _min else -2]
            if "/Kids" in node:
                return _get_min_or_max_key(node["/Kids"][0 if _min else -1].getObject(), _min)
            raise Exception("_get_min_or_max_key abnormal")

        def _insert_nameddest(title, dest, node, force=0):
            if "/Limits" in node:
                mi_, ma_ = node["/Limits"][0:2]
            elif ("/Kids" in node and len(node["/Kids"]) == 0):
                raise Exception("Kids list empty ???")
            elif ("/Names" in node and len(node["/Names"]) == 0):
                title = TextStringObject(title)
                node["/Names"].append(title)
                node["/Names"].append(dest)
                node.update({NameObject("/Limits"):ArrayObject([title, title])})
                return node["/Limits"]
            else:  #there is some data but no Limits(it should not exists
                mi_, ma_ = _get_min_or_max_key(node, True), _get_min_or_max_key(node, False)

            if "/Names" in node:  #it is a list of names
                if title < ma_ or force != 0:
                    if force == -1:
                        i = 0
                    else:
                        for i in range(len(node["/Names"])//2):
                            if title < node["/Names"][i*2]:
                                break
                    title = TextStringObject(title)
                    if force == +1:
                        node["/Names"].append(title)
                        node["/Names"].append(dest)
                    else:
                        node["/Names"].insert(i*2, dest)
                        node["/Names"].insert(i*2, title)
                    if "/Limits" not in node:
                        node.update({NameObject("/Limits"):ArrayObject([title, title])})
                    if title < node["/Limits"][0]:
                        node["/Limits"][0] = title
                    if title > node["/Limits"][1]:
                        node["/Limits"][1] = title
                    return node["/Limits"]
                return None
            if "/Kids" in node:     #need to process one level down
                if force == 1:
                    lim = _insert_nameddest(title, dest, node["/Kids"][-1].getObject(), +1)
                    if "/Limits" not in node:
                        node.update({NameObject("/Limits"):ArrayObject([mi_, lim[1]])})
                    node["/Limits"][1] = lim[1]
                    return node["/Limits"]
                if title < mi_ or force == -1:
                    lim = _insert_nameddest(title, dest, node["/Kids"][0].getObject(), -1)
                    if "/Limits" not in node:
                        node.update({NameObject("/Limits"):ArrayObject([lim[0], ma_])})
                    node["/Limits"][0] = lim[0]
                    return node["/Limits"]
                if title < ma_:
                    for k__ in node["/Kids"]:
                        lim = _insert_nameddest(title, dest, k__.getObject())
                        if lim is None:
                            continue
                        if lim[0] < mi_:
                            node["/Limits"][0] = TextStringObject(mi_)
                        if ma_ < lim[1]:
                            node["/Limits"][1] = TextStringObject(ma_)
                        return node["/Limits"]
                    raise Exception("no Kids Found ????")
                return None
            raise Exception("no Kids and no names????", node)

        def title_defaults(title):
            if title is None:
                if "/Title" in dest:
                    title = dest["/Title"]
                else:
                    title = "_"+"".join(random.choices(
                        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
                        k=10))
            assert title not in self.get_named_destinations(), \
                "Named Destination '%s' already defined"%(title,)
            return title

        dest = dest.getObject() #ensure to get the object in case of IndirectObject

        title = title_defaults(title)

        try:
            dests = self.root_object.rawGet("/Dests").getObject()
        except:                                                         #pylint: disable=bare-except
            dests = None
        assert isinstance(dests, (type(None), DictionaryObject)), "Dests in Root not a dictionnary"

        try:
            dests2 = self.root_object["/Names"].rawGet("/Dests").getObject()
        except:                                                         #pylint: disable=bare-except
            dests2 = None

        if dests is not None and dests2 is not None:
            raise PdfStreamError("/Dest exists both in Root catalog and in Names section")

        if dests is None and dests2 is None: #note : we used PDF 1.1 solution (simpler)
            #dests = DictionaryObject()
            #self.root_object.update({NameObject("/Dests"):self._add_object(dests)})
            if not "/Names" in self.root_object:
                self.root_object[NameObject("/Names")] = self._add_object(DictionaryObject())
            self.root_object["/Names"].update({NameObject("/Dests"):DictionaryObject()})
            dests2 = self.root_object["/Names"]["/Dests"]
            dests2.update({NameObject("/Names"):ArrayObject()})

        dest_ref = self._add_object(dest)

        if dests is not None:           # i.e PDF1.1 format
            dests.update({NameObject(title):dest_ref})
            return title, dest_ref
        #if dests2:         # i.e PDF1.2+ format
        assert (isinstance(dests2, DictionaryObject) and
                ("/Kids" in dests2 or "/Names" in dests2)), "Dests in Names not a names tree"
        lim = _insert_nameddest(title, dest_ref, dests2)
        if lim is None:
            lim = _insert_nameddest(title, dest_ref, dests2, +1)
                                         # we force object to be created at the end of the list
        return title, dest_ref
    addNamedDestinationObject = add_named_destination_object

    def add_named_destination(self, title, pagenum, top=None, left=None, zoom=0.0):                  #pylint: too hudge change for the moment disable=invalid-name,too-many-arguments
        """ add a named destination """
        page_ref = self.get_page(pagenum, ref=True)
        dest = DictionaryObject()
        try:
            if top <= 1.0:
                top = float(page_ref.getObject()["/MediaBox"][3])*(1-top)
        except:                                                                                #pylint: disable=bare-except
            top = None      # if we arrive here, top should be None but in other cases...
        try:
            if left <= 1.0:  #top est en % de la page
                left = float(page_ref.getObject()["/MediaBox"][2])*(left)
        except:                                                                                 #pylint: disable=bare-except
            left = None      # if we arrive here, top should be None but in other cases...

        if top is None and left is None:
            d__ = ArrayObject([page_ref, NameObject("/Fit")])
        elif left is None:
            d__ = ArrayObject([page_ref, NameObject("/FitH"), NumberObject(top)])
        elif top is None:
            d__ = ArrayObject([page_ref, NameObject("/FitV"), NumberObject(left)])
        else:
            d__ = ArrayObject([page_ref, NameObject("/XYZ"), NumberObject(left),
                               NumberObject(top), FloatObject(zoom)])

        dest.update({
            NameObject("/D"): d__,
            NameObject("/S"): NameObject("/GoTo")
        })

        return self.add_named_destination_object(dest, title)
    addNamedDestination = add_named_destination

    def remove_named_destination(self, title):
        """ delete the named destination identified with title """
        def _get_min_or_max_key(node, _min=True):
            if "/Names" in node:
                return node["/Names"][0 if _min else -2]
            if "/Kids" in node:
                return _get_min_or_max_key(node["/Kids"][0 if _min else -1].getObject(), _min)
            raise Exception("_get_min_or_max_key abnormal")

        def _del_nameddest(title, node, top=True):
            if "/Limits" in node:
                mi_, ma_ = node["/Limits"][0:2]
            elif ("/Kids" in node and len(node["/Kids"]) == 0):
                try:
                    del node["/Kids"]
                except:                                             #pylint: disable=bare-except
                    pass
                try:
                    del node["/Limits"]
                except:                                             #pylint: disable=bare-except
                    pass
                node.update({NameObject("/Names"):ArrayObject()})
                return False
            elif ("/Names" in node and len(node["/Names"]) == 0):
                try:
                    del node["/Limits"]
                except:                                             #pylint: disable=bare-except
                    pass
                return False
            else:
                mi_, ma_ = _get_min_or_max_key(node, True), _get_min_or_max_key(node, False)

            if "/Names" in node:  #it is a list of names
                if not mi_ <= title <= ma_:
                    return -2 # not within the range
                for i in range(len(node["/Names"])//2):
                    if title == node["/Names"][i*2]:
                        del node["/Names"][i*2+1]
                        del node["/Names"][i*2]
                        if len(node["/Names"]) == 0:
                            del node["/Limits"]
                        else:
                            node["/Limits"][0] = node["/Names"][0]
                            node["/Limits"][1] = node["/Names"][-2]
                        return len(node["/Names"])//2
                return -1 # nothing has not been found but it should have been there
            if "/Kids" in node:     #need to process one level down
                if not mi_ <= title <= ma_:
                    return -2
                for i__, k__ in enumerate(node["/Kids"]):
                    ret = _del_nameddest(title, k__.getObject(), False)
                    if ret == -2:
                        continue
                    if ret == -1:
                        return -1
                    if ret == 0:
                        del node["/Kids"][i__]
                        if len(node["/Kids"]) == 0:
                            del node["/Limits"]
                            if top:  #no empty kids at root
                                del node["/Kids"]
                                node.update({NameObject("/Names"):ArrayObject()})
                            return 0
                    node["/Limits"] = (_get_min_or_max_key(node, True),
                                       _get_min_or_max_key(node, False))
                    return len(node["/Kids"])
            raise Exception("no Kids nor name Found ????", node)

        assert title is not None

        try:
            dests = self.root_object.rawGet("/Dests").getObject()
        except:                                                             #pylint: disable=bare-except
            dests = None
        assert isinstance(dests, (type(None), DictionaryObject)),\
                "Dests in Root Catalog not a dictionnary"

        try:
            dests2 = self.root_object["/Names"].rawGet("/Dests").getObject()
        except:                                                             #pylint: disable=bare-except
            dests2 = None

        if dests is not None and dests2 is not None:
            raise PdfStreamError("/Dest exists both in Root catalog and in Names section")

        if dests is None and dests2 is None:
            #note : we are currently using the PDF 1.1 solution to simplify implementation
            dests = DictionaryObject()
            self.root_object.update({NameObject("/Dests"):self._add_object(dests)})

        if dests:
            for k__ in dests:
                if title == k__:
                    del dests[k__]
                    return True
            return False

        if dests2:
            assert (isinstance(dests2, DictionaryObject)
                    and ("/Kids" in dests2)), "Dests in Names not a names tree"
            return _del_nameddest(title, dests2) >= 0

    removeNamedDestination = remove_named_destination

    def remove_annots(self, page_set=None, links=False, comments=False, attachments=False,                 #pylint: too hudge change for the moment disable=invalid-name,too-many-arguments
                      prints=False, _3d=False):
        """ Removes different annotations from this output.  """
        if page_set is None:
            page_set = range(self.num_pages)

        #if all are false, for compatibility, they should be all deleted
        if not(links or comments or attachments or prints or _3d):
            links = True
            comments = True
            attachments = True
            prints = True
            _3d = True
        sub_types = []
        if links:
            sub_types.extend(["/Link",])
        if comments:
            sub_types.extend(["/Text", "/FreeText", "/Line", "/Square", "/Circle", "/Polygon",
                              "/PolyLine", "/Highlight", "/Underline", "/Squiggly", "/StrikeOut",
                              "/Stamp", "/Caret", "/Ink", "/Popup",])
        if attachments:
            sub_types.extend(["/FileAttachment", "/Sound", "/Movie", "/Widget", "/Screen",])
        if prints:
            sub_types.extend(["/PrinterMark", "/TrapNet", "/Watermark",])
        if _3d:
            sub_types.extend(["/3D"])

        for i in page_set:
            page = self.get_page(i)
            if "/Annots" in page:
                ik_ = 0
                while ik_ < len(page["/Annots"]):
                    annot = page["/Annots"][ik_].getObject()
                    if annot["/Subtype"] in sub_types:
                        del page["/Annots"][ik_]
                    else:
                        ik_ += 1
                if len(page["/Annots"]) == 0:
                    del page["/Annots"]
    removeAnnots = remove_annots

    def remove_links(self):                                                          #pylint: too hudge change for the moment disable=invalid-name
        """
        Removes All annotations from all pages. Kept for compatibility with old api
        """
        self.remove_annots()
    removeLinks = remove_links

    def remove_images(self, page_set=None, ignore_bytestring_obj=False):                           #pylint: too hudge change for the moment disable=invalid-name
        """
        Removes images from this output.

        :param bool ignore_bytestring_obj: optional parameter to ignore
            ByteString Objects.
        """
        for j__ in page_set:
            page_ref = self.get_page(j__, True)
            page = page_ref.getObject()
            content = page["/Contents"].getObject()

            if not isinstance(content, ContentStream):
                content = ContentStream(content, page_ref.pdf)

            _operations = []
            seq_graphics = False

            for operands, operator in content.operations:
                if operator == by_("Tj"):
                    text = operands[0]
                    if ignore_bytestring_obj and not isinstance(text, TextStringObject):
                        operands[0] = TextStringObject()
                elif operator == by_("\'"):
                    text = operands[0]
                    if ignore_bytestring_obj and not isinstance(text, TextStringObject):
                        operands[0] = TextStringObject()
                elif operator == by_("\""):
                    text = operands[2]
                    if ignore_bytestring_obj and not isinstance(text, TextStringObject):
                        operands[2] = TextStringObject()
                elif operator == by_("TJ"):
                    for i in range(len(operands[0])):
                        if (ignore_bytestring_obj and
                                not isinstance(operands[0][i], TextStringObject)):
                            operands[0][i] = TextStringObject()

                if operator == by_("q"):
                    seq_graphics = True
                if operator == by_("Q"):
                    seq_graphics = False
                if seq_graphics:
                    if operator in [by_("cm"), by_("w"), by_("J"), by_("j"), by_("M"), by_("d"),
                                    by_("ri"), by_("i"), by_("gs"), by_("W"), by_("b"), by_("s"),
                                    by_("S"), by_("f"), by_("F"), by_("n"), by_("m"), by_("l"),
                                    by_("c"), by_("v"), by_("y"), by_("h"), by_("B"), by_("Do"),
                                    by_("sh"), ]:
                        continue
                if operator == by_("re"):
                    continue
                _operations.append((operands, operator))

            content.operations = _operations
            page.__setitem__(NameObject("/Contents"), content)
    removeImages = remove_images

    def remove_text(self, page_set=None, ignore_bytestring_obj=False):                      #pylint: too hudge change for the moment disable=invalid-name
        """
        Removes text from this output.

        :param bool ignore_bytestring_obj: optional parameter to ignore
            ByteString Objects.
        """
        if page_set is None:
            page_set = range(self.num_pages)
        if ignore_bytestring_obj:
            types_ = (TextStringObject, ByteStringObject)
        else:
            types_ = (TextStringObject,)
        for j__ in page_set:   #they may be multiple nodes in the tree
            page_ref = self.get_page(j__, True)
            page = page_ref.getObject()
            content = page["/Contents"].getObject()

            if not isinstance(content, ContentStream):
                content = ContentStream(content, page_ref.pdf)
            for operands, operator in content.operations:
                if operator == by_("Tj"):
                    if isinstance(operands[0], types_):
                        operands[0] = TextStringObject()
                elif operator == by_("\'"):
                    if isinstance(operands[0], types_):
                        operands[0] = TextStringObject()
                elif operator == by_("\""):
                    if isinstance(operands[2], types_):
                        operands[2] = TextStringObject()
                elif operator == by_("TJ"):
                    for i in range(len(operands[0])):
                        if isinstance(operands[0][i], types_):
                            operands[0][i] = TextStringObject()

            page.__setitem__(NameObject("/Contents"), content)
    removeText = remove_text

    def add_page_label(self, pn_, pagelbl):                               #pylint: too hudge change for the moment disable=invalid-name
        """
        if pagelbl is None, we remove the definition from the nums tree
        """
        def _get_min_or_max_key(node, _min=True):
            if "/Nums" in node:
                return node["/Nums"][0 if _min else -2]
            if "/Kids" in node:
                return _get_min_or_max_key(node["/Kids"][0 if _min else -1].getObject(), _min)
            raise Exception("_get_min_or_max_key abnormal")

        def _insert_pagelabel(pn_, pagelbl, node, force=0):
            if "/Limits" in node:
                mi_, ma_ = node["/Limits"][0:2]
            elif ("/Kids" in node and len(node["/Kids"]) == 0):
                raise Exception("Kids list empty ???")
            elif ("/Nums" in node and len(node["/Nums"]) == 0):
                pn_ = NumberObject(pn_)
                node["/Nums"].append(pn_)
                node["/Nums"].append(pagelbl)
                node.update({NameObject("/Limits"):ArrayObject([pn_, pn_])})
                return node["/Limits"]
            else:
                mi_ = _get_min_or_max_key(node, True)   # for tests...
                ma_ = _get_min_or_max_key(node, False)   # for tests...

            if "/Nums" in node:  #it is a list of names
                #first the case where the entry already exists.
                try:
                    idx = node["/Nums"].index(pn_)
                    if pagelbl is not None:
                        node["/Nums"][idx+1] = pagelbl
                    else:
                        del node["/Nums"][idx+1]
                        del node["/Nums"][idx]
                    if len(node["/Nums"]) == 0:
                        try:
                            del node["/Limits"]
                        except:                                                     #pylint: disable=bare-except
                            pass
                        return -1
                    if "/Limits" not in node:
                        node.update({NameObject("/Limits"):
                                         ArrayObject([node["/Nums"][0], node["/Nums"][-2]])})
                    node["/Limits"][0] = node["/Nums"][0]
                    node["/Limits"][1] = node["/Nums"][-2]
                    return node["/Limits"]
                except:                                                             #pylint: disable=bare-except
                    pass

                if mi_ <= pn_ < ma_ or force != 0:
                    if force == -1:
                        i = 0
                    else:
                        for i in range(len(node["/Nums"])//2):
                            if pn_ < node["/Nums"][i*2]:
                                break
                    pn_ = NumberObject(pn_)
                    if force == +1:
                        node["/Nums"].append(pn_)
                        node["/Nums"].append(pagelbl)
                    else:
                        node["/Nums"].insert(i*2, pagelbl)
                        node["/Nums"].insert(i*2, pn_)
                    if "/Limits" not in node:
                        node.update({NameObject("/Limits"):
                                     ArrayObject([min(pn_, mi_), max(pn_, ma_)])})
                    if pn_ < node["/Limits"][0]:
                        node["/Limits"][0] = pn_
                    if pn_ > node["/Limits"][1]:
                        node["/Limits"][1] = pn_
                    return node["/Limits"]
                return None
            if "/Kids" in node:     #need to process one level down
                if force == 1:
                    lim = _insert_pagelabel(pn_, pagelbl, node["/Kids"][-1].getObject(), +1)
                    if "/Limits" not in node:
                        node.update({NameObject("/Limits"):ArrayObject([mi_, lim[1]])})
                    node["/Limits"][1] = lim[1]
                    return node["/Limits"]
                if pn_ < mi_ or force == -1:
                    lim = _insert_pagelabel(pn_, pagelbl, node["/Kids"][0].getObject(), -1)
                    if "/Limits" not in node:
                        node.update({NameObject("/Limits"):ArrayObject([lim[0], ma_])})
                    node["/Limits"][0] = lim[0]
                    return node["/Limits"]
                if pn_ <= ma_:
                    for k__ in node["/Kids"]:
                        lim = _insert_pagelabel(pn_, pagelbl, k__.getObject())
                        if lim is None:
                            continue
                        if lim is -1: #The call indicates the sub node is empty
                            del node["/Kids"][node["/Kids"].index(k__)]
                        if lim[0] < mi_:
                            node["/Limits"][0] = TextStringObject(lim[0])
                        if ma_ < lim[1]:
                            node["/Limits"][1] = TextStringObject(lim[1])
                        return node["/Limits"]
                    raise Exception("no Kids Found ????")
                return None

        self.get_page_label(pn_)    #initialise flattenPageLabel                    #pylint: imported function disable=not-callable
        try:
            dests = self.root_object.rawGet("/PageLabels").getObject()
        except:                                                                     #pylint: disable=bare-except
            dests = DictionaryObject()
            dests.update({NameObject("/Nums"):ArrayObject()})
            self.root_object.update({NameObject("/PageLabels"):self._add_object(dests)})

        if isinstance(pagelbl, PageLabel):
            pagelbl_ref = self._add_object(pagelbl.buildDefinition())
        elif pagelbl is None:
            if pn_ not in self._flatten_page_labels:                                #pylint: it has been already check disable=unsupported-membership-test,access-member-before-definition
                return pn_, False
            pagelbl_ref = pagelbl
        elif isinstance(pagelbl, IndirectObject):
            pagelbl_ref = pagelbl
        elif isinstance(pagelbl, DictionaryObject):
            pagelbl_ref = self._add_object(pagelbl)
        else:
            raise Exception("PageLabel type incorrect")

        assert (isinstance(dests, DictionaryObject)
                and ("/Kids" in dests or "/Nums" in dests)), "PageLbl root has Kids and  Nums"
        lim = _insert_pagelabel(pn_, pagelbl_ref, dests)
        if lim is None:
            # we force object to be created at the end of the list
            lim = _insert_pagelabel(pn_, pagelbl_ref, dests, +1)
        self._flatten_page_labels = None                                            #pylint: variable initialised in parent class disable=attribute-defined-outside-init
        self.get_page_label(pn_) # to regenerate _flatten_page_labels               #pylint: imported function disable=not-callable
        return pn_, pagelbl_ref
    addPageLabel = add_page_label

    def remove_page_label(self, pn_):                                                 #pylint: too hudge change for the moment disable=invalid-name
        """
        to provide a clear call to the adequate function
        return true is deletion occured else return False
        """
        return self.add_page_label(pn_, None)[-1] is None
    removePageLabel = remove_page_label

    def add_uri(self, pagenum, uri, rect, border=None):                              #pylint: too hudge change for the moment disable=invalid-name
        """
        Add an URI from a rectangular area to the specified page. This uses the
        basic structure of add_link.

        :param int pagenum: index of the page on which to place the URI action.
        :param int uri: string -- uri of resource to link to.
        :param rect: :class:`RectangleObject<pypdf.generic.RectangleObject>`
            or array of four integers specifying the clickable rectangular area
            ``[xLL, yLL, xUR, yUR]``, or string in the form
            ``"[ xLL yLL xUR yUR ]"``.
        :param border: if provided, an array describing border-drawing
            properties. See the PDF spec for details. No border will be drawn
            if this argument is omitted.
        """
        page_link = self.getObject(self._pages)["/Kids"][pagenum]
        page_ref = self.getObject(page_link)

        if border is not None:
            border_arr = [NameObject(n) for n in border[:3]]
            if len(border) == 4:
                dash_pattern = ArrayObject([NameObject(n) for n in border[3]])
                border_arr.append(dash_pattern)
        else:
            border_arr = [NumberObject(2)] * 3

        if is_string(rect):
            rect = NameObject(rect)
        elif not isinstance(rect, RectangleObject):
            rect = RectangleObject(rect)

        lnk2 = DictionaryObject()
        lnk2.update(
            {
                NameObject("/S"): NameObject("/URI"),
                NameObject("/URI"): TextStringObject(uri),
            }
        )

        lnk = DictionaryObject()
        lnk.update(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Link"),
                NameObject("/P"): page_link,
                NameObject("/Rect"): rect,
                NameObject("/H"): NameObject("/I"),
                NameObject("/Border"): ArrayObject(border_arr),
                NameObject("/A"): lnk2,
            }
        )
        lnk_ref = self._add_object(lnk)

        if "/Annots" in page_ref:
            page_ref["/Annots"].append(lnk_ref)
        else:
            page_ref[NameObject("/Annots")] = ArrayObject([lnk_ref])
    addURI = add_uri

    def add_link(self, pagenum, pagedest, rect, border=None, fit="/Fit", * zoom_args):                #pylint: too hudge change for the moment disable=invalid-name,keyword-arg-before-vararg,too-many-arguments
        """
        Add an internal link from a rectangular area to the specified page.

        :param int pagenum: index of the page on which to place the link.
        :param int pagedest: index of the page to which the link should go.
        :param rect: :class:`RectangleObject<pypdf.generic.RectangleObject>`
            or array of four integers specifying the clickable rectangular area
            ``[xLL, yLL, xUR, yUR]``, or string in the form
            ``"[ xLL yLL xUR yUR ]"``.
        :param border: if provided, an array describing border-drawing
            properties. See the PDF spec for details. No border will be drawn
            if this argument is omitted.
        :param str fit: Page fit or 'zoom' option (see below). Additional
            arguments may need to be supplied. Passing ``None`` will be read as
            a null value for that coordinate.

        Valid zoom arguments (see Table 8.2 of the PDF 1.7 reference for
        details):
             /Fit       No additional arguments
             /XYZ       [left] [top] [zoomFactor]
             /FitH      [top]
             /FitV      [left]
             /FitR      [left] [bottom] [right] [top]
             /FitB      No additional arguments
             /FitBH     [top]
             /FitBV     [left]
        """
        page_link = self.getObject(self._pages)["/Kids"][pagenum]
        # TO-DO: switch for external link
        page_dest_obj = self.getObject(self._pages)["/Kids"][pagedest]
        page_ref = self.getObject(page_link)

        if border is not None:
            border_arr = [NameObject(n) for n in border[:3]]
            if len(border) == 4:
                dash_pattern = ArrayObject([NameObject(n) for n in border[3]])
                border_arr.append(dash_pattern)
        else:
            border_arr = [NumberObject(0)] * 3

        if is_string(rect):
            rect = NameObject(rect)
        elif isinstance(rect, RectangleObject):
            pass
        else:
            rect = RectangleObject(rect)

        zoom_a = []
        for a__ in zoom_args:
            if a__ is not None:
                zoom_a.append(NumberObject(a__))
            else:
                zoom_a.append(NullObject())
        # TO-DO: create a better name for the link
        dest = Destination(NameObject("/LinkName"),
                           page_or_dest_or_array=page_dest_obj, typ=NameObject(fit), args=zoom_a)
        dest_array = dest.getDestArray()

        lnk = DictionaryObject()
        lnk.update(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Link"),
                NameObject("/P"): page_link,
                NameObject("/Rect"): rect,
                NameObject("/Border"): ArrayObject(border_arr),
                NameObject("/Dest"): dest_array,
            }
        )
        lnk_ref = self._add_object(lnk)

        if "/Annots" in page_ref:
            page_ref["/Annots"].append(lnk_ref)
        else:
            page_ref[NameObject("/Annots")] = ArrayObject([lnk_ref])
    addLink = add_link

    def add_comment_object(self, page_num, comment, irtSubstitute=None):                 #pylint: too hudge change for the moment disable=invalid-name
        """ 
        add comment(obj) on page_num(integer) with  irtSubstitute 
        irtSubstitute can be set to :
                an Indirect Object(force substitution),
                True to clone the object,if required
                False to remove IRT
                None do not change the original IRT
        """
        comment_i = None
        if isinstance(comment, IndirectObject):
            comment_i = comment.idnum
            comment = comment.getObject()
        try:
            #remember that irt is in the response
            irt = comment.rawGet("/IRT")
            if irtSubstitute is True:
                irt = irt.clone(self) # if object has been already cloned, it will be returned
            elif irtSubstitute is False:
                irt = None
            elif irtSubstitute is not None:
                irt = irtSubstitute

        except KeyError:
            irt = None
        #if comment.get("/Subtype")=="/Text":
        #    try:
        #        state = comment["/State"]
        #    except:                                     #pylint: disable=bare-except
        #        state = None
        #    rgb = comment["/C"]
        #    try:
        #        co_ = comment["/Contents"]
        #        co_ = co_.decode("unicode_escape")
        #    except:                                     #pylint: disable=bare-except
        #        pass
        #    try:
        #        auth = comment["/T"]
        #        auth = auth.decode("unicode_escape")
        #    except:                                     #pylint: disable=bare-except
        #        pass
        #    return self.add_comment(page_num, co_, auth, comment["/CreationDate"], irt, state,
        #                        comment["/Rect"][1], comment["/Rect"][0], rgb)
        #else:
        if True: # to keep indentation unchanged
            co2=DictionaryObject()
            co2_=self._add_object(co2)
            if comment_i:
                self._id_translated[comment_i]=co2_.idnum
            for k,v in comment.items():
                if k=="/IRT":
                    co2.update({NameObject("/IRT") : irt })
                elif k=="/AP":  #TODO : reintroduce AP field cloning
                    pass;
                elif k=="/P":
                    co2.update({k : self.get_page(page_num,True)})
                else: #if k=="/ExData":
                    co2.update({k : v.clone(self)})
            self.get_page(page_num)["/Annots"].append(co2_)
            return co2_
                
                    
    addCommentObject = add_comment_object

    def add_comment(self, page_num, text, author="Unindentified", creation_date=None, irt=None,
                    state=None, top=0, left=0, rgb=(1.0, 0.81961, 0.0)):
        """ add comment """
        page = self.get_page(page_num)
        if creation_date is None:
            creation_date = datetime.datetime.now()
        if isinstance(creation_date, datetime.datetime):
            creation_date = creation_date.strftime("D:%Y%m%d%H%M%S%z")

        if top <= 1.0:  #top est en % de la page
            top = float(page["/MediaBox"][3])*(1-top)
        if left <= 1.0:  #top est en % de la page
            left = float(page["/MediaBox"][2])*(left)

        ano = DictionaryObject()
        ano.update({NameObject("/Type"):NameObject("/Annot"),
                    NameObject("/Subtype"):NameObject("/Text"),
                    NameObject("/Name"):NameObject("/Comment"),
                    NameObject("/F"):NumberObject(4),
                    NameObject("/Open"): BooleanObject(False),
                    NameObject("/Subj"):TextStringObject("Note"),
                    NameObject("/C"):ArrayObject([FloatObject(rgb[0]), FloatObject(rgb[1]),
                                                  FloatObject(rgb[2])]),

                    NameObject("/T"):TextStringObject(author),
                    NameObject("/Contents") : TextStringObject(text),

                    NameObject("/CreationDate"):TextStringObject(creation_date),
                    NameObject("/M"):TextStringObject(creation_date),

                    NameObject("/Rect"): ArrayObject([FloatObject(left),
                                                      FloatObject(top),
                                                      FloatObject(float(left)+24.0),
                                                      FloatObject(float(top)+24.0)])})
        if irt is not None:
            ano.update({NameObject("/IRT"):irt,
                        NameObject("/Rect"):irt.getObject()["/Rect"],
                       })
        if state is not None:
            ano.update({NameObject("/State"):TextStringObject(state),
                        NameObject("/StateModel"):TextStringObject("Review")})
        if not "/Annots" in page:
            page.update({NameObject("/Annots"):ArrayObject(), })
        ano = self._add_object(ano)
        page["/Annots"].append(ano)
        return ano
    addComment = add_comment

    def add_comments_from_page(self, page_num, page):      #pylint: too hudge change for the moment disable=invalid-name
        """
        copy all comments (text comments currently) from a page (from another document)
        onto the designated page
        """
        page = page.getObject()
        try:
            mem_translation = self._id_translated[page.idnum]
        except:
            mem_translation = None
        self._id_translated[page.idnum]=self.getPage(page_num,True).idnum # we set translation to this page
        ret = []
        tr_ = {}
        try:
            for c__ in page["/Annots"]:
                co_ = c__.getObject()
                if co_["/Subtype"] in ["/Text", "/FreeText", "/Line", "/Square", "/Circle", "/Polygon",
                              "/PolyLine", "/Highlight", "/Underline", "/Squiggly", "/StrikeOut",
                              "/Stamp", "/Caret", "/Ink", "/Popup",]:
                    try:
                        irt = co_.rawGet("/IRT")
                        irt = tr_[irt.idnum]
                    except:                             #pylint: disable=bare-except
                        irt = None
                    r__ = self.add_comment_object(page_num, c__, True)
                    tr_[c__.idnum] = r__
                    self._id_translated[c__.idnum] = r__.idnum
                    ret.append(r__)
        finally:
            if mem_translation:
                self._id_translated[page.idnum]=mem_translation
            else:
                del self._id_translated[page.idnum]
            return ret
    addCommentsFromPage = add_comments_from_page

    _VALID_LAYOUTS = ["/NoLayout", "/SinglePage", "/OneColumn", "/TwoColumnLeft", "/TwoColumnRight",
                      "/TwoPageLeft", "/TwoPageRight", ]

    def set_page_layout(self, layout):                                                #pylint: too hudge change for the moment disable=invalid-name
        """
        Set the page layout.

        :param str layout: The page layout to be used.

        Valid layouts are:
             /NoLayout        Layout explicitly not specified
             /SinglePage      Show one page at a time
             /OneColumn       Show one column at a time
             /TwoColumnLeft   Show pages in two columns, odd-numbered pages on
                 the left
             /TwoColumnRight  Show pages in two columns, odd-numbered pages on
                 the right
             /TwoPageLeft     Show two pages at a time, odd-numbered pages on
                 the left
             /TwoPageRight    Show two pages at a time, odd-numbered pages on
                 the right
        """
        if not isinstance(layout, NameObject):
            if layout not in self._VALID_LAYOUTS:
                warnings.warn(
                    "Layout should be one of: {}".format(", ".join(self._VALID_LAYOUTS))
                )
            layout = NameObject(layout)
        self.root_object.update({NameObject("/PageLayout"): layout})
    setPageLayout = set_page_layout
    pageLayout = page_layout = property(PdfDocument.pageLayout.fget, set_page_layout)
    """
    Read and write property accessing the
    :meth:`getPageLayout()<PdfFileWriter.get_page_layout>` and
    :meth:`setPageLayout()<PdfFileWriter.set_page_layout>` methods.
    """
    _VALID_MODES = ["/UseNone", "/UseOutlines", "/UseThumbs",
                    "/FullScreen", "/UseOC", "/UseAttachments",]

    def set_page_mode(self, mode):                                                    #pylint: too hudge change for the moment disable=invalid-name
        """
        Set the page mode.

        :param str mode: The page mode to use.

        Valid modes are:
            /UseNone         Do not show outlines or thumbnails panels
            /UseOutlines     Show outlines (aka bookmarks) panel
            /UseThumbs       Show page thumbnails panel
            /FullScreen      Fullscreen view
            /UseOC           Show Optional Content Group (OCG) panel
            /UseAttachments  Show attachments panel
        """
        if not isinstance(mode, NameObject):
            if mode not in self._VALID_MODES:
                warnings.warn(
                    "Mode should be one of: {}".format(", ".join(self._VALID_MODES))
                )
            mode = NameObject(mode)
        self.root_object.update({NameObject("/PageMode"): mode})
    setPageMode = set_page_mode
    pageMode = page_mode = property(PdfDocument.pageMode.fget, set_page_mode)
    """
    Read and write property accessing the
    :meth:`getPageMode()<PdfFileWriter.getPageMode>` and
    :meth:`setPageMode()<PdfFileWriter.setPageMode>` methods.
    """
