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
Implementation of generic PDF objects (dictionary, number, string, and so on).
"""

#import math
#import re
import struct
#import uuid
#import warnings
from hashlib import md5

from .utils import (PdfReadError, pypdfBytes as by_, RC4Encrypt, pypdfOrd, is_string, #pylint: disable=relative-beyond-top-level
                    ConvertFunctionsToVirtualList,)
from  .generic1 import (PdfObject, NullObject, BooleanObject, pypdf_str,              #pylint: disable=relative-beyond-top-level,unused-import
                        FloatObject, NumberObject, ByteStringObject, TextStringObject,
                        NameObject, encode_pdf_doc_encoding, decode_pdf_doc_encoding,
                        create_string_object, _pdfDocEncoding, _pdfDocEncoding_rev)
from  .generic import  (DocumentInformation, PageLabel, Destination, ArrayObject,       #pylint: disable=relative-beyond-top-level
                        IndirectObject, DictionaryObject, Bookmark, Field, PdfBaseDocument)

__author__ = "Mathieu Fenniak"
__author_email__ = "biziqe@mathieu.fenniak.net"

class PdfDocument(PdfBaseDocument):                              #pylint: for Py 2.x disable=useless-object-inheritance
    """ abstract/common class for PdfReader/Writer """
    def __init__(self, debug):
        self._root = None
        self._filepath = None
        self._stream = None
        self._info = None
        self._flatten_page_labels = None
        self._named_dests = [] #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        self._pageid_to_num = None
        self.debug = debug

    @property
    def root_object(self):
        """ return the root_object """
        if self._root is None:
            return None
        return self._root.getObject()
    rootObject = root_object

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.is_closed:
            self.close()
        return False

    def __repr__(self):
        return "abstract class %s"%self.__class__

    @property
    def filepath(self):
        """
        :return: The PDF file path read with ``PdfFileReader`` or
                 written(from __init__) in case of ``PdfFileWriter``
                 ``None`` if there isn't such a path.
        """
        try:
            return self._filepath
        except AttributeError:
            pass
        try:
            return self._stream.name
        except AttributeError:
            return None

    @property
    def is_closed(self):
        """
        :return: ``True`` if the IO streams associated with this file have
            been closed, ``False`` otherwise.
        """
        return not bool(self._stream) or self._stream.closed
    isClosed = is_closed

    def close(self):
        """
        Deallocates file-system resources associated with this ``PdfFileReader`` instance.
        """
        try:
            self._stream.close()
        except:                         #pylint: disable=bare-except
            pass

    def get_object(self, ref):
        """ abstract function """
        raise NotImplementedError("Abstract Error")
    getObject = get_object

    def get_indirect_object(self, idnum):
        """ return the indirect object identified by idnum """
        ref = IndirectObject(idnum, 0, self)
        return ref
    getIndirectObject = get_indirect_object

    def get_document_info(self):
        """
        Retrieves the PDF file's document information dictionary, if it exists.
        Note that some PDF files use metadata streams instead of docinfo
        dictionaries, and these metadata streams will not be accessed by this
        function.

        :return: the document information of this PDF file.
        :rtype: :class:`DocumentInformation<pdf.DocumentInformation>` or
            ``None`` if none exists.
        """
        try:
            retval = DocumentInformation()
            retval.update(self._info.getObject())
            return retval
        except (KeyError, AttributeError):
            return None
    getDocumentInfo = get_document_info
    documentInfo = document_info = property(get_document_info)

    def get_num_pages(self):
        """
        Calculates the number of pages in this PDF file.

        :return: number of pages
        :rtype: int
        :raises PdfReadError: if file is encrypted and restrictions prevent
            this action.
        """
        raise NotImplementedError("abstract function")
    getNumPages = get_num_pages
    numPages = num_pages = property(get_num_pages)

    def get_page(self, pn_):
        """ abstract get_page """
        raise NotImplementedError("abstract function")
    getPage = get_page

    def _reset_pageid_to_num(self):
        self._pageid_to_num = None

    def get_pagenumber_by_indirect(self, indirect_ref):
        """Generate _pageid_to_num"""
        if self._pageid_to_num is None:
            id2num = {}

            for i__, x__ in enumerate(self.pages):
                id2num[x__.indirectRef.idnum] = i__

            self._pageid_to_num = id2num

        if isinstance(indirect_ref, int):
            idnum = indirect_ref
        else:
            idnum = indirect_ref.idnum

        ret = self._pageid_to_num.get(idnum, -1)

        return ret

    def get_page_number(self, page):
        """
        Retrieve page number of a given PageObject

        :param PageObject page: The page to get page number. Should be
            an instance of :class:`PageObject<pypdf.pdf.PageObject>`
        :return: the page number or -1 if page not found
        :rtype: int
        """
        indirect_ref = page.indirectRef
        ret = self.get_pagenumber_by_indirect(indirect_ref)
        return ret
    getPageNumber = get_page_number

    def get_destination_page_number(self, destination):
        """
        Retrieves the page number of a given ``Destination`` object

        :param Destination destination: The destination to get page number.
             Should be an instance of
             :class:`Destination<pypdf.pdf.Destination>`
        :return: the page number or ``-1`` if the page was not found.
        :rtype: int
        """
        indirect_ref = destination.page
        ret = self.get_pagenumber_by_indirect(indirect_ref)
        return ret
    getDestinationPageNumber = get_destination_page_number

    def get_page_label(self, num):
        """ return page label """
        def find_pagelbl_entry(num):
            #there will be always 0 that will match...
            for k__ in sorted(self._flatten_page_labels.keys()):
                if k__ > num:
                    break
                k1_ = k__
            return self._flatten_page_labels[k1_].getLabel(num)

        def flatten_pagelbl(node=None):
            flat = {}
            # the default value we use this value in order to have a
            # default value that will be overriden by 0 if provided and
            # if we want to check that there is a definition for page 0
            flat[-0.5] = PageLabel(0, (0, "", "/D"))
            if node is None:
                p1_ = self.root_object
                if "/PageLabels" in p1_:
                    node = p1_["/PageLabels"]
                else:
                    return flat
            if "/Nums" in node:
                node = node["/Nums"].getObject()
                for i in range(len(node)//2):
                    o__ = PageLabel(node[2*i], node[2*i+1].getObject())
                    flat[node[2*i]] = o__
            elif "/Kids" in node:
                for k__ in node["/Kids"]:
                    flat.update(flatten_pagelbl(k__.getObject()))
            else:
                raise Exception("issue processing PageLabels")
            return flat

        if self._flatten_page_labels is None:
            self._flatten_page_labels = flatten_pagelbl()
        assert 0 <= num < self.num_pages, "Page Number out of range"
        return find_pagelbl_entry(num)
    getPageLabel = get_page_label

    def get_page_layout(self):
        """
        Get the page layout.
        See :meth:`setPageLayout()<PdfFileWriter.setPageLayout>`
        for a description of valid layouts.

        :return: Page layout currently being used.
        :rtype: ``str``, ``None`` if not specified
        """
        try:
            #return self._trailer["/Root"]["/PageLayout"]
            return self.root_object["/PageLayout"]
        except KeyError:
            return None
    getPageLayout = get_page_layout
    pageLayout = page_layout = property(get_page_layout)

    def get_page_mode(self):
        """
        Get the page mode.
        See :meth:`setPageMode()<PdfFileWriter.setPageMode>`
        for a description of valid modes.

        :return: Page mode currently being used.
        :rtype: ``str``, ``None`` if not specified
        """
        try:
            #return self._trailer["/Root"]["/PageMode"] #!!!! changed to _rootObject
            return self.root_object["/PageMode"]
        except KeyError:
            return None
    getPageMode = get_page_mode
    pageMode = page_mode = property(get_page_mode)

    @staticmethod
    def _build_destination(title, array):
        return Destination(title, page_or_dest_or_array=array[0], typ=array[1], zargs=array[2:])

    def _build_outline(self, node):
        dst, title, outline = None, None, None

        if "/Title" in node:
            title = node["/Title"]
            if "/A" in node:
                # Action, section 8.5 (only type GoTo supported)
                action = node["/A"]
                if action["/S"] == "/GoTo":
                    dst = action["/D"]
            elif "/Dest" in node:
                # Destination, section 8.2.1
                dst = node["/Dest"]

        # if destination found, then create outline
        if dst:
            if is_string(dst) and dst in self._named_dests:
                dst = self._named_dests[dst].get_dest_array()
            if isinstance(dst, (ArrayObject, Destination)):
                outline = Bookmark(title, dst)
                #outline = Bookmark(title, page_or_dest_or_array=dst[0], typ=dst[1], zargs=dst[2:])
            else:
                raise PdfReadError("Unexpected destination %r" % dst)

        try: # TODO :left for the moment to find it but it is not part
            outline[NameObject("/Node")] = self.get_reference(node)
        except AttributeError:
            pass

        if "/F" in node:
            outline[NameObject("/F")] = node["/F"]

        if "/C" in node:
            outline[NameObject("/C")] = node["/C"]

        if "/First" in node:        # we are capturing the whole sub tree
            outline[NameObject("/First")] = node.rawGet("/First")
            outline[NameObject("/Last")] = node.rawGet("/Last")
            outline[NameObject("/Count")] = node["/Count"]

        if "/Parent" in node:
            p__ = node.rawGet("/Parent")
            try:
                #if "/Type" in p__ and p__["/Type"] == "/Outlines":
                #    outline.parent = None
                if "/Title" in p__.getObject():
                    outline[NameObject("/Parent")] = p__
            except:                                 #pylint: disable=bare-except
                pass

        return outline

    pages = property(
        lambda self: ConvertFunctionsToVirtualList(lambda: self.num_pages, self.get_page)
    )
    """
    Read-only property that emulates a list based upon the
    :meth:`num_pages<PdfFileReader.num_pages>` and
    :meth:`get_page()<PdfFileReader.get_page>` methods.
    """

    def get_outlines(self, node=None, _outlines=None):
        """
        Retrieves the document outline present in the document.

        :return: a nested list of
            :class:`Destinations<pypdf.generic.Destination>`.
        """
        if _outlines is None:
            _outlines = []
            catalog = self.root_object

            # get the outline dictionary and named destinations
            if "/Outlines" in catalog:
                try:
                    lines = catalog["/Outlines"]
                except PdfReadError:
                    # This occurs if the /Outlines object reference is
                    # incorrect for an example of such a file, see
                    # https://unglueit-files.s3.amazonaws.com/ebf/7552c42e9280b4476e59e77acc0bc812.pdf
                    # so continue to load the file without the Bookmarks
                    return _outlines

                if "/First" in lines:
                    node = lines["/First"]

            self._named_dests = self.get_named_destinations()

        if node is None:
            return _outlines

        # see if there are any more outlines
        while True:
            outline = self._build_outline(node)
            if outline:
                _outlines.append(outline)

            # check for sub-outlines
            if "/First" in node:
                sub_outlines = []
                self.get_outlines(node["/First"], sub_outlines)
                if sub_outlines:
                    _outlines.append(sub_outlines)

            if "/Next" not in node:
                break
            node = node["/Next"]

        return _outlines
    getOutlines = get_outlines
    outlines = property(get_outlines)

    def get_named_destinations(self, tree=None, retval=None):
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
                val = names[i + 1].getObject()

                if isinstance(val, DictionaryObject) and "/D" in val:
                    val = val["/D"]

                dest = self._build_destination(key, val)
                if dest is not None:
                    retval[key] = dest
        else:  # case where Dests is in root catalog
            for k__, v__ in tree.items():
                val = v__.getObject()
                dest = self._build_destination(k__, val)
                if dest is not None:
                    retval[k__] = dest

        return retval
    getNamedDestinations = get_named_destinations
    NamedDestinations = named_destinations = property(get_named_destinations)

    def get_fields(self, tree=None, retval=None, fileobj=None):              #pylint: too hudge change for the moment disable=invalid-name
        """
        Extracts field data if this PDF contains interactive form fields.
        The ``tree`` and ``retval`` parameters are for recursive use.

        :param retval:
        :param tree:
        :param fileobj: A file object (usually a text file) to write
            a report to on all interactive form fields found.
        :return: A dictionary where each key is a field name, and each
            value is a :class:`Field<pypdf.generic.Field>` object. By
            default, the mapping name is used for keys.
        :rtype: ``dict``, or ``None`` if form data could not be located.
        """
        def _check_kids(tree, retval, fileobj):
            if "/Kids" in tree:
                # Recurse down the tree
                for kid in tree["/Kids"]:
                    self.get_fields(kid.getObject(), retval, fileobj)
        def _write_field(fileobj, field, field_attributes):
            order = ["/TM", "/T", "/FT", "/Parent", "/TU", "/Ff", "/V", "/DV"]

            for attr in order:
                attr_name = field_attributes[attr]

                try:
                    if attr == "/FT":
                        # Make the field type value more clear
                        types_ = {"/Btn": "Button", "/Tx": "Text",
                                  "/Ch": "Choice", "/Sig": "Signature"}
                        if field[attr] in types_:
                            fileobj.write(attr_name + ": " + types_[field[attr]] + "\n")
                    elif attr == "/Parent":
                        # Let's just write the name of the parent
                        try:
                            name = field["/Parent"]["/TM"]
                        except KeyError:
                            name = field["/Parent"]["/T"]
                        fileobj.write(attr_name + ": " + name + "\n")
                    else:
                        fileobj.write(attr_name + ": " + str(field[attr]) + "\n")
                except KeyError:
                    # Field attribute is N/A or unknown, so don't write anything
                    pass
        def _build_field(field, retval, fileobj, field_attributes):
            _check_kids(field, retval, fileobj)
            try:
                key = field["/TM"]
            except KeyError:
                try:
                    key = field["/T"]
                except KeyError:
                    # Ignore no-name field for now
                    return
            if fileobj:
                _write_field(fileobj, field, field_attributes)
                fileobj.write("\n")
            retval[key] = Field(field)
        field_attributes = {"/FT": "Field Type", "/Parent": "Parent", "/T": "Field Name",
                            "/TU": "Alternate Field Name", "/TM": "Mapping Name",
                            "/Ff": "Field Flags", "/V": "Value", "/DV": "Default Value", }
        if retval is None:
            retval = {}
            catalog = self.root_object

            # Get the AcroForm tree
            if "/AcroForm" in catalog:
                tree = catalog["/AcroForm"]
            else:
                return None
        if tree is None:
            return retval

        _check_kids(tree, retval, fileobj)
        for attr in field_attributes:
            if attr in tree:
                # Tree is a field
                _build_field(tree, retval, fileobj, field_attributes)
                break

        if "/Fields" in tree:
            fields = tree["/Fields"]
            for f__ in fields:
                field = f__.getObject()
                _build_field(field, retval, fileobj, field_attributes)

        return retval
    getFields = get_fields

    def get_form_text_fields(self):
        """ Retrieves form fields from the document with textual data (inputs, dropdowns).  """
        formfields = self.get_fields()

        return dict(
            (formfields[field]["/T"], formfields[field].get("/V"))
            for field in formfields
            if formfields[field].get("/FT") == "/Tx"
        )
    getFormTextFields = get_form_text_fields
    formTextFields = form_text_fields = property(get_form_text_fields)

################################# end of class ####################################################

def _convert_to_int(d__, size):
    if size > 8:
        raise PdfReadError("Invalid size in _convert_to_int")

    d__ = by_("\x00\x00\x00\x00\x00\x00\x00\x00") + by_(d__)
    d__ = d__[-8:]

    return struct.unpack(">q", d__)[0]


# TO-DO Refactor the code pertaining to these _algX() functions, as they do not
# seem to conform with OOP and local project conventions.
# ref: pdf1.8 spec section 3.5.2 algorithm 3.2
_ENCRYPTION_PADDING = (
    by_("\x28\xbf\x4e\x5e\x4e\x75\x8a\x41\x64\x00\x4e\x56")
    + by_("\xff\xfa\x01\x08\x2e\x2e\x00\xb6\xd0\x68\x3e\x80\x2f\x0c")
    + by_("\xa9\xfe\x64\x53\x69\x7a")
)


def _alg32(password, rev, keylen, owner_entry, p_entry, id1_entry, metadata_encrypt=True):          #pylint: too hudge change for the moment disable=too-many-arguments
    """
    Implementation of algorithm 3.2 of the PDF standard security handler,
    section 3.5.2 of the PDF 1.6 reference.
    """
    # 1. Pad or truncate the password string to exactly 32 bytes.  If the
    # password string is more than 32 bytes long, use only its first 32 bytes;
    # if it is less than 32 bytes long, pad it by appending the required number
    # of additional bytes from the beginning of the padding string
    # (_ENCRYPTION_PADDING).
    password = by_((pypdf_str(password) + pypdf_str(_ENCRYPTION_PADDING))[:32])
    # 2. Initialize the MD5 hash function and pass the result of step 1 as
    # input to this function.
    m__ = md5(password)
    # 3. Pass the value of the encryption dictionary's /O entry to the MD5 hash
    # function.
    m__.update(owner_entry.original_bytes)
    # 4. Treat the value of the /P entry as an unsigned 4-byte integer and pass
    # these bytes to the MD5 hash function, low-order byte first.
    p_entry = struct.pack("<i", p_entry)
    m__.update(p_entry)
    # 5. Pass the first element of the file's file identifier array to the MD5
    # hash function.
    m__.update(id1_entry.original_bytes)
    # 6. (Revision 3 or greater) If document metadata is not being encrypted,
    # pass 4 bytes with the value 0xFFFFFFFF to the MD5 hash function.
    if rev >= 3 and not metadata_encrypt:
        m__.update(by_("\xff\xff\xff\xff"))
    # 7. Finish the hash.
    md5_hash = m__.digest()
    # 8. (Revision 3 or greater) Do the following 50 times: Take the output
    # from the previous MD5 hash and pass the first n bytes of the output as
    # input into a new MD5 hash, where n is the number of bytes of the
    # encryption key as defined by the value of the encryption dictionary's
    # /Length entry.
    if rev >= 3:
        for _i in range(50):
            md5_hash = md5(md5_hash[:keylen]).digest()
    # 9. Set the encryption key to the first n bytes of the output from the
    # final MD5 hash, where n is always 5 for revision 2 but, for revision 3 or
    # greater, depends on the value of the encryption dictionary's /Length
    # entry.
    return md5_hash[:keylen]


def _alg33(owner_pwd, user_pwd, rev, keylen):
    """
    Implementation of algorithm 3.3 of the PDF standard security handler,
    section 3.5.2 of the PDF 1.6 reference.
    """
    # steps 1 - 4
    key = _alg33_1(owner_pwd, rev, keylen)
    # 5. Pad or truncate the user password string as described in step 1 of
    # algorithm 3.2.
    user_pwd = by_((user_pwd + pypdf_str(_ENCRYPTION_PADDING))[:32])
    # 6. Encrypt the result of step 5, using an RC4 encryption function with
    # the encryption key obtained in step 4.
    val = RC4Encrypt(key, user_pwd)
    # 7. (Revision 3 or greater) Do the following 19 times: Take the output
    # from the previous invocation of the RC4 function and pass it as input to
    # a new invocation of the function; use an encryption key generated by
    # taking each byte of the encryption key obtained in step 4 and performing
    # an XOR operation between that byte and the single-byte value of the
    # iteration counter (from 1 to 19).
    if rev >= 3:
        for i in range(1, 20):
            new_key = ""
            #for l in range(len(key)):
            for k__ in key:
                new_key += chr(pypdfOrd(k__) ^ i)
            val = RC4Encrypt(new_key, val)
    # 8. Store the output from the final invocation of the RC4 as the value of
    # the /O entry in the encryption dictionary.
    return val


def _alg33_1(password, rev, keylen):
    """
    Steps 1-4 of algorithm 3.3.
    """
    # 1. Pad or truncate the owner password string as described in step 1 of
    # algorithm 3.2.  If there is no owner password, use the user password
    # instead.
    password = by_((password + pypdf_str(_ENCRYPTION_PADDING))[:32])
    # 2. Initialize the MD5 hash function and pass the result of step 1 as
    # input to this function.
    m__ = md5(password)
    # 3. (Revision 3 or greater) Do the following 50 times: Take the output
    # from the previous MD5 hash and pass it as input into a new MD5 hash.
    md5_hash = m__.digest()
    if rev >= 3:
        for _i in range(50):
            md5_hash = md5(md5_hash).digest()
    # 4. Create an RC4 encryption key using the first n bytes of the output
    # from the final MD5 hash, where n is always 5 for revision 2 but, for
    # revision 3 or greater, depends on the value of the encryption
    # dictionary's /Length entry.
    key = md5_hash[:keylen]
    return key


def _alg34(password, owner_entry, p_entry, id1_entry):
    """
    Implementation of algorithm 3.4 of the PDF standard security handler,
    section 3.5.2 of the PDF 1.6 reference.
    """
    # 1. Create an encryption key based on the user password string, as
    # described in algorithm 3.2.
    key = _alg32(password, 2, 5, owner_entry, p_entry, id1_entry)
    # 2. Encrypt the 32-byte padding string shown in step 1 of algorithm 3.2,
    # using an RC4 encryption function with the encryption key from the
    # preceding step.
    u__ = RC4Encrypt(key, _ENCRYPTION_PADDING)
    # 3. Store the result of step 2 as the value of the /U entry in the
    # encryption dictionary.
    return u__, key


def _alg35(password, rev, keylen, owner_entry, p_entry, id1_entry, _metadata_encrypt):              #pylint: too hudge change for the moment disable=too-many-arguments
    """
    Implementation of algorithm 3.4 of the PDF standard security handler,
    section 3.5.2 of the PDF 1.6 reference.
    """
    # 1. Create an encryption key based on the user password string, as
    # described in Algorithm 3.2.
    key = _alg32(password, rev, keylen, owner_entry, p_entry, id1_entry)
    # 2. Initialize the MD5 hash function and pass the 32-byte padding string
    # shown in step 1 of Algorithm 3.2 as input to this function.
    m__ = md5()
    m__.update(_ENCRYPTION_PADDING)
    # 3. Pass the first element of the file's file identifier array (the value
    # of the ID entry in the document's trailer dictionary; see Table 3.13 on
    # page 73) to the hash function and finish the hash.  (See implementation
    # note 25 in Appendix H.)
    m__.update(id1_entry.original_bytes)
    md5_hash = m__.digest()
    # 4. Encrypt the 16-byte result of the hash, using an RC4 encryption
    # function with the encryption key from step 1.
    val = RC4Encrypt(key, md5_hash)
    # 5. Do the following 19 times: Take the output from the previous
    # invocation of the RC4 function and pass it as input to a new invocation
    # of the function; use an encryption key generated by taking each byte of
    # the original encryption key (obtained in step 2) and performing an XOR
    # operation between that byte and the single-byte value of the iteration
    # counter (from 1 to 19).
    for i__ in range(1, 20):
        new_key = by_("")
        for k__ in key:
            new_key += by_(chr(pypdfOrd(k__) ^ i__))
        val = RC4Encrypt(new_key, val)
    # 6. Append 16 bytes of arbitrary padding to the output from the final
    # invocation of the RC4 function and store the 32-byte result as the value
    # of the U entry in the encryption dictionary.
    # (implementator note: I don't know what "arbitrary padding" is supposed to
    # mean, so I have used null bytes.  This seems to match a few other
    # people's implementations)
    return val + (by_("\x00") * 16), key
