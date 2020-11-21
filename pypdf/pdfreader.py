#-member-before-definition -*- coding: utf-8 -*-
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
import io
import struct
import sys
import warnings

from .utils import (is_string, pypdfBytes as by_, BytesIO,            #pylint: disable=relative-beyond-top-level
                    PdfStreamError, PdfReadError, PdfReadWarning, ConvertFunctionsToVirtualList,
                    pypdfOrd, readUntilWhitespace, skip_over_whitespace, skip_over_comment,
                    read_non_whitespace, pairs, formatWarning, )
from .generic import (BooleanObject, ArrayObject, IndirectObject,                #pylint: disable=relative-beyond-top-level
                      NumberObject, NameObject, create_string_object, read_object,
                      TextStringObject, DictionaryObject, StreamObject,
                      ByteStringObject, NullObject, PageObject, RC4Encrypt)
from .pdfcommon import (PdfDocument, _convert_to_int, _alg33_1, _alg34, _alg35)       #pylint: disable=relative-beyond-top-level

__author__ = "Mathieu Fenniak"
__author_email__ = "biziqe@mathieu.fenniak.net"
__maintainer__ = "Phaseit, Inc."
__maintainer_email__ = "PyPDF4@phaseit.net"

class PdfFileReader(PdfDocument):                                                 #pylint: for Py 2.x disable=useless-object-inheritance
    """
    PdfFileReader Object
    """
    R_XTABLE, R_XSTREAM, R_BOTH = (1, 2, 3)

    def __init__(self, stream, strict=True, warndest=None, overwrite_warnings=True, debug=False):       #pylint: defined API disable=too-many-arguments
        """
        Initializes a ``PdfFileReader`` instance.  This operation can take some
        time, as the PDF stream's cross-reference tables are read into memory.

        :param stream: A file-like object with ``read()`` and ``seek()``
            methods. Could also be a string representing a path to a PDF file.
        :param bool strict: Determines whether user should be warned of all
            problems and also causes some correctable problems to be fatal.
            Defaults to ``True``.
        :param warndest: Destination for logging warnings (defaults to
            ``sys.stderr``).
        :param bool overwrite_warnings: Determines whether to override Python's
            ``warnings.py`` module with a custom implementation (defaults to
            ``True``).
        :param bool debug: Whether this class should emit debug informations
            (recommended for development). Defaults to ``False``.
        """
        super().__init__(debug)
        self.getObject = self.get_object
        if overwrite_warnings:
            # Have to dynamically override the default showwarning since there
            # are no public methods that specify the 'file' parameter
            def _showwarning(message, category, filename, lineno, file=warndest, line=None):        #pylint: showwarning API disable=too-many-arguments
                if file is None:
                    file = sys.stderr

                try:
                    file.write(formatWarning(message, category, filename, lineno, line))
                except IOError:
                    pass

            warnings.showwarning = _showwarning

        self._xref_table = {}
        """
        Stores the Cross-Reference Table indices. The keys are gen. numbers,
        the values a dict of the form ``{obj. id: (byte offset within file, is
        in free object list)}``.
        """
        self._xref_idx = 0
        self._xref_stm = {}

        """ some attributes now created in constructor """
        self._decryption_key = None
        """
        Stores the Cross-Reference Stream data. The keys are id numbers of
        objects. The values are exactly as in Table 18 of section 7.5.8.3 of
        the ISO 32000 Reference (2008), represented as a tuple of length three.
        """
        self._cached_objs = {}
        self._trailer = DictionaryObject()
        self._flatten_pages = None

        self.strict = strict
        self._override_encryption = False

        if isinstance(stream, io.FileIO):
            self._filepath = stream.name
        elif is_string(stream):
            self._filepath = stream
        else:
            self._filepath = None

        if is_string(stream):
            with open(stream, "rb") as fileobj:
                self._stream = BytesIO(fileobj.read())
        else:
            # We rely on duck typing
            self._stream = stream

        if hasattr(self._stream, "mode") and "b" not in self._stream.mode:
            warnings.warn(
                "PdfFileReader stream/file object is not in binary mode. It "
                "may not be read correctly.",
                PdfReadWarning,
            )

        self._parse_pdf_file(self._stream)
        # for homogeneity with Writer
        self._root = self._trailer.rawGet("/Root")
        try:
            self._info = self._trailer.rawGet("/Info")
        except KeyError:
            self._info = None

    @property
    def _encrypt(self):
        """return encrypt dictionnary in a similar manner as writer"""
        try:
            return self._trailer["/Encrypt"]
        except KeyError:
            return {"/P":-1}    #it is not a PDF to be able to distiguish it....

    def __repr__(self):
        return (
            "<%s.%s isClosed=%s, _filepath=%s, _stream=%s, strict=%s, "
            "debug=%s>"
            % (self.__class__.__module__, self.__class__.__name__, self.isClosed,
               self._filepath, self._stream, self.strict, self.debug,))

    def __del__(self):
        self.close()
        for a__ in ("_xref_table", "_xref_stm", "_cached_objs", "_trailer", "_pageid_to_num",
                    "_flatten_pages", "_stream",):
            if hasattr(self, a__):
                delattr(self, a__)

    def get_xmp_metadata(self):                                                  #pylint: too hudge change for the moment disable=invalid-name
        """
        Retrieves XMP (Extensible Metadata Platform) data from the PDF document root.

        :return: a :class:`XmpInformation<xmp.XmpInformation>`
            instance that can be used to access XMP metadata from the document.
        :rtype: :class:`XmpInformation<xmp.XmpInformation>` or
            ``None`` if no metadata was found on the document root.
        """
        try:
            self._override_encryption = True
            return self.root_object.get_xmp_metadata()
        finally:
            self._override_encryption = False
    getXmpMetadata = get_xmp_metadata
    xmpMetadata = xmp_metadata = property(get_xmp_metadata)

    def get_num_pages(self):                                                     #pylint: too hudge change for the moment disable=invalid-name
        """
        Calculates the number of pages in this PDF file.

        :return: number of pages
        :rtype: int
        :raises PdfReadError: if file is encrypted and restrictions prevent
            this action.
        """
        # Flattened pages will not work on an Encrypted PDF
        # the PDF file's page count is used in this case. Otherwise,
        # the original method (flattened page count) is used.
        if self.is_encrypted:
            try:
                self._override_encryption = True
                self.decrypt("")

                return self.root_object["/Pages"]["/Count"]
            except Exception:
                raise PdfReadError("File has not been decrypted")
            finally:
                self._override_encryption = False
        else:
            if self._flatten_pages is None:
                self._flatten()

            return len(self._flatten_pages)
    getNumPages = get_num_pages
    numPages = num_pages = property(get_num_pages)

    def get_page(self, page_number):                                         #pylint: too hudge change for the moment disable=invalid-name
        """
        Retrieves a page by number from this PDF file.

        :param int page_number: The page number to retrieve
            (pages begin at zero)
        :return: a :class:`PageObject<pdf.PageObject>` instance.
        :rtype: :class:`PageObject<pdf.PageObject>`
        """
        # Ensure that we're not trying to access an encrypted PDF
        if self._flatten_pages is None:
            self._flatten()
        return self._flatten_pages[page_number]
    getPage = get_page
    pages = property(
        lambda self: ConvertFunctionsToVirtualList(lambda: self.num_pages, self.get_page)
    )

    def _flatten(self, pages=None, inherit=None, indirect_ref=None):
        inheritable_page_attrs = (NameObject("/Resources"), NameObject("/MediaBox"),
                                  NameObject("/CropBox"), NameObject("/Rotate"),)
        def _defaults(inherit, pages):
            if inherit is None:
                inherit = dict()
            if pages is None:
                self._flatten_pages = []
                pages = self.root_object["/Pages"].getObject()
            return inherit, pages
        inherit, pages = _defaults(inherit, pages)
        try:
            t__ = pages["/Type"]
        except KeyError:
            raise PdfReadError("/Type not found", pages)
        except TypeError:
            raise PdfReadError("Wrong object Type (%s)"%(type(pages),), pages)
        if t__ == "/Pages":
            for attr in inheritable_page_attrs:
                if attr in pages:
                    inherit[attr] = pages[attr]
            for page in pages["/Kids"]:
                if isinstance(page, IndirectObject):
                    self._flatten(page.getObject(), inherit, page)
                else:
                    self._flatten(page, inherit, None)
        elif t__ == "/Page":
            for attr, value in list(inherit.items()):
                # If the page has its own value, it does not inherit the parent's value:
                if attr not in pages:
                    pages[attr] = value
            page_obj = PageObject(self, indirect_ref)
            page_obj.idnum =indirect_ref.idnum          #add to get id_num
            page_obj.update(pages)
            self._flatten_pages.append(page_obj)
        else:
            raise PdfReadError("Unexpected Pdf Type (%s)"%(t__,), pages)

    def _get_object_by_ref(self, ref, source):
        """
        Fetches an indirect object identified by ``ref`` from either the XRef
        Table or the XRef Stream.

        :param ref: an ``IndirectObject`` instance.
        :param source: the source whence the object should be fetched,
            between the XRef Table and the XRef Stream. Accepted values are:\n
            * ``PdfFileReader.R_XTABLE``   XRef Table
            * ``PdfFileReader.R_XSTREAM``    Cross-Reference Stream
        :rtype: PdfObject
        """
        is_xtable, is_xstream = source & self.R_XTABLE, source & self.R_XSTREAM

        if is_xtable:
            if self._xref_table[ref.generation][ref.idnum][1] is True:
                if self.strict:
                    raise PdfReadError("Cannot fetch a free object (id, next gen.) = (%d, %d)"
                                       %(ref.idnum, ref.generation))
                warnings.warn("fetching a free object(%d) => returns NullObject"%ref.idnum,
                              PdfReadWarning,)
                return NullObject()

            offset = self._xref_table[ref.generation][ref.idnum][0]
        elif is_xstream:
            # See ISO 32000 (2008), Table 18 "Entries in a cross-reference stream"
            this_type = self._xref_stm[ref.idnum][0]

            if this_type == 0:
                if self.strict:
                    raise PdfReadError("Cannot fetch a free object (id, next gen.) = (%d, %d)"
                                       %(ref.idnum, ref.generation))
                else:
                    warnings.warn("fetching a free object(%d) => returns NullObject"%ref.idnum,
                                  PdfReadWarning,)
                    return NullObject()
            if this_type == 1:
                offset, generation = self._xref_stm[ref.idnum][1:3]

                if generation != ref.generation:
                    raise ValueError("Generation number given as input (%d) doesn't equal the one "
                                     "stored (%d) in the XRef Stream"%(ref.generation, generation))
            elif this_type == 2:
                return self._get_compressed_object_from_xrefstream(ref)
            else:
                # Â«Any other value shall be interpreted as a reference to the
                # null object, thus permitting new entry types to be defined in
                # the future.Â» Section 7.5.8.3 of ISO 32000 (2008)
                return NullObject()
        else:
            raise ValueError("Unaccepted value of source = %d" % source)

        self._stream.seek(offset, 0)
        actual_id, actual_gen = self._read_object_header(self._stream)

        if is_xtable and self._xref_idx and actual_id != ref.idnum:
            # Xref table probably had bad indexes due to not being
            # zero-indexed
            if self.strict:
                raise PdfReadError("Expected object ID (%d %d) does not match actual "
                                   "(%d %d); xref table not zero-indexed."
                                   %(ref.idnum, ref.generation, actual_id, actual_gen))
            # XRef Table is corrected in non-strict mode
        elif self.strict and (actual_id != ref.idnum or actual_gen != ref.generation):
            # Some other problem
            raise PdfReadError("Expected object ID (%d, %d) does not match actual (%d, %d)."
                               %(ref.idnum, ref.generation, actual_id, actual_gen))

        retval = read_object(self._stream, self)

        # Override encryption is used for the /Encrypt dictionary
        if not self._override_encryption and self.is_encrypted:
            # If we don't have the encryption key:
            if not hasattr(self, "_decryption_key") or self._decryption_key is None:
                raise PdfReadError("file has not been decrypted")

            # otherwise, decrypt here...
            pack1 = struct.pack("<i", ref.idnum)[:3]
            pack2 = struct.pack("<i", ref.generation)[:2]
            key = self._decryption_key + pack1 + pack2
            assert len(key) == (len(self._decryption_key) + 5)
            md5hash = md5(key).digest()
            key = md5hash[: min(16, len(self._decryption_key) + 5)]

            retval = self._decrypt_obj(retval, key)

        return retval

    def _get_compressed_object_from_xrefstream(self, ref):
        """
        Fetches a type 2 compressed object from a Cross-Reference stream.

        :param ref: an ``IndirectObject`` instance.
        :return: a ``PdfObject`` stored into a compressed object stream.
        """
        entry_type, obj_stmid, local_id = self._xref_stm[ref.idnum]

        if entry_type != 2:
            raise PdfReadError(
                "Expected a type 2 (compressed) object but type is %d" % entry_type
            )

        # Object streams always have a generation number of 0
        obj_stm = IndirectObject(obj_stmid, 0, self).getObject()

        if obj_stm["/Type"] != "/ObjStm":
            raise PdfReadError(
                "/Type of object stream expected to be /ObjStm, was %s instead"
                % obj_stm["/Type"]
            )
        if local_id >= obj_stm["/N"]:
            raise PdfStreamError(
                "Local object id is %d, but a maximum of only %d is allowed"
                % (local_id, obj_stm["/N"] - 1)
            )

        stream_data = BytesIO(by_(obj_stm.get_data()))

        for index in range(obj_stm["/N"]):
            read_non_whitespace(stream_data)
            stream_data.seek(-1, 1)
            objnum = NumberObject.readFromStream(stream_data)

            read_non_whitespace(stream_data)
            stream_data.seek(-1, 1)
            offset = NumberObject.readFromStream(stream_data)

            read_non_whitespace(stream_data)
            stream_data.seek(-1, 1)

            if objnum != ref.idnum:
                # We're only interested in one object
                continue
            if self.strict and local_id != index:
                raise PdfReadError("Object is in wrong index.")

            stream_data.seek(obj_stm["/First"] + offset, 0)

            try:
                obj = read_object(stream_data, self)
            except PdfStreamError as e:
                # Stream object cannot be read. Normally, a critical error,
                # but Adobe Reader doesn't complain, so continue (in strict
                # mode?)
                e = sys.exc_info()[1]
                warnings.warn(
                    "Invalid stream (index %d) within object %d %d: %s"
                    % (index, ref.idnum, ref.generation, e),
                    PdfReadWarning,
                )

                if self.strict:
                    raise PdfReadError("Can't read object stream: %s" % e)

                # Replace with null. Hopefully it's nothing important.
                obj = NullObject()

            return obj

        if self.strict:
            raise PdfReadError("This is a fatal error in strict mode.")
        return NullObject()

    def objects(self, select=R_BOTH, free_objects=False):
        """
        Returns an iterable of :class:`IndirectObject<generic.IndirectObject>`
        instances (either by the Cross-Reference Tables or Cross-Reference
        Streams) stored in this PDF file.

        :param select: whether to include items from the XRef Table only, the
            Cross-Reference Stream only or both. Accepted values are:\n
            * PdfFileReader.R_XTABLE   Only items from the XRef Table
            * PdfFileReader.R_XSTREAM    Only items from the
                Cross-Reference Stream
            * PdfFileReader.R_BOTH  The default, selects both of the above
        :param free_objects: whether to include objects from the free entries
            list. Defaults to ``False`` (only objects that can be fetched from
            the File Body are included).
        :return: an unsorted iterable of
            :class:`IndirectObject<generic.IndirectObject>` values.
        """
        if select & self.R_XTABLE:
            # Reverse-sorted list of generation numbers from the XRef Table
            gens = sorted(self._xref_table.keys(), reverse=True)

            # We give the X-Ref Table a higher precedence than the
            # Cross-Reference Stream
            for gen in gens:
                for id_ in self._xref_table[gen]:
                    # "If free_objects or this object is not a free one..."
                    if free_objects or self._xref_table[gen][id_][1] is False:
                        yield IndirectObject(id_, gen, self)
        if select & self.R_XSTREAM:
            # Iterate through the Cross-Reference Stream
            for id_, v__ in self._xref_stm.items():
                if free_objects and v__[0] == 0:
                    yield IndirectObject(id_, v__[2], self)
                elif v__[0] == 1:
                    yield IndirectObject(id_, v__[2], self)
                elif v__[0] == 2:
                    yield IndirectObject(id_, 0, self)

    def get_object(self, ref):                                                       #pylint: too hudge change for the moment disable=invalid-name
        """
        Retrieves an indirect reference object, caching it appropriately, from
        the File Body of the associated PDF file.

        :param IndirectObject ref: an
            :class:`IndirectObject<generic.IndirectObject>` instance
            identifying the indirect object properties (id. and gen. number).
        :return: the :class:`PdfObject<generic.PdfObject` queried for, if
            found.
        :raises PdfReadError: if ``ref`` did not relate to any object.
        """
        if (ref.generation, ref.idnum) in self._cached_objs:
            return self._cached_objs[(ref.generation, ref.idnum)]
        if ref.idnum in self._xref_stm:
            retval = self._get_object_by_ref(ref, self.R_XSTREAM)
        elif (ref.generation in self._xref_table
              and ref.idnum in self._xref_table[ref.generation]):
            retval = self._get_object_by_ref(ref, self.R_XTABLE)
        else:
            warnings.warn(
                "Object %d %d not defined." % (ref.idnum, ref.generation),
                PdfReadWarning,
            )
            raise PdfReadError(
                "Could not find object (%d, %d)" % (ref.idnum, ref.generation)
            )

        self._cache_indirectobj(ref.generation, ref.idnum, retval)

        return retval

    def is_object_free(self, ref):      #used ?????
        """
        :param ref: a :class:`IndirectObject<pypdf.generic.IndirectObject>`
            instance.
        :return: ``True`` if ``ref`` is in the free entries list, ``False``
            otherwise.
        """
        if (ref.generation in self._xref_table
                and ref.idnum in self._xref_table[ref.generation]):
            return self._xref_table[ref.generation][ref.idnum][1]
        if ref.idnum in self._xref_stm:
            return self._xref_stm[ref.idnum][0] == 0

        # Object does not exist
        raise ValueError("%r does not exist in %s" % (str(ref), self._filepath))
    isObjectFree = is_object_free

    def _parse_pdf_file(self, stream):
        def _get_entry(i, stream_data):
            """
            Reads the correct number of bytes for each entry. See the
            discussion of the ``/W`` parameter in ISO 32000, section 7.5.8.2,
            table 17.
            """
            if entry_sizes[i] > 0:
                d__ = stream_data.read(entry_sizes[i])
                return _convert_to_int(d__, entry_sizes[i])

            # PDF Spec Table 17: A value of zero for an element in the
            # W array indicates... the default value shall be used
            if i == 0:
                # First value defaults to 1
                return 1
            return 0

        def _used_before(num, generation):
            # We move backwards through the xrefs, don't replace any.
            return num in self._xref_table.get(generation, []) or num in self._xref_stm

        stream.seek(-1, 2)  # Start at the end:

        if not stream.tell():
            raise PdfReadError("Cannot read an empty file")

        # Offset of last 1024 bytes of stream
        last1k = stream.tell() - 1024 + 1
        line = by_("")

        while line[:5] != by_("%%EOF"):
            if stream.tell() < last1k:
                raise PdfReadError("EOF marker not found")

            line = self._read_next_eol(stream)

        # Find startxref entry - the location of the xref table
        line = self._read_next_eol(stream)
        try:
            startxref = int(line)
        except ValueError:
            # startxref may be on the same line as the location
            if not line.startswith(by_("startxref")):
                raise PdfReadError("startxref not found")

            startxref = int(line[9:].strip())
            warnings.warn("startxref on same line as offset")
        else:
            line = self._read_next_eol(stream)

            if line[:9] != by_("startxref"):
                raise PdfReadError("startxref not found")

        # Read all cross reference tables and their trailers
        while True:
            # Load the xref table
            stream.seek(startxref, 0)
            x__ = stream.read(1)

            if x__ == by_("x"):
                # Standard cross-reference table
                ref = stream.read(4)

                if ref[:3] != by_("ref"):
                    raise PdfReadError("xref table read error")

                read_non_whitespace(stream)
                stream.seek(-1, 1)
                # Check if the first time looking at the xref table
                firsttime = True

                while True:
                    # The current id of this subsection items
                    currid = read_object(stream, self)

                    if firsttime and currid != 0:
                        self._xref_idx = currid

                        if self.strict:
                            warnings.warn(
                                "Xref table not zero-indexed. ID numbers for "
                                "objects will be corrected.",
                                PdfReadWarning,
                            )
                            # If table not zero indexed, could be due to error
                            # from when PDF was created #which will lead to
                            # mismatched indices later on, only warned and
                            # corrected if self.strict=True

                    firsttime = False
                    read_non_whitespace(stream)
                    stream.seek(-1, 1)
                    size = read_object(stream, self)
                    read_non_whitespace(stream)
                    stream.seek(-1, 1)
                    cnt = 0

                    while cnt < size:
                        line = stream.read(20)
                        # It's very clear in section 3.4.3 of the PDF spec
                        # that all cross-reference table lines are a fixed
                        # 20 bytes (as of PDF 1.7). However, some files have
                        # 21-byte entries (or more) due to the use of \r\n
                        # (CRLF) EOL's. Detect that case, and adjust the line
                        # until it does not begin with a \r (CR) or \n (LF).
                        while line[0] in by_("\x0D\x0A"):
                            stream.seek(-20 + 1, 1)
                            line = stream.read(20)

                        # On the other hand, some malformed PDF files
                        # use a single character EOL without a preceeding
                        # space.  Detect that case, and seek the stream
                        # back one character.  (0-9 means we've bled into
                        # the next xref entry, t means we've bled into the
                        # text "trailer"):
                        if line[-1] in by_("0123456789t"):
                            stream.seek(-1, 1)

                        offset, generation = line[:16].split(by_(" "))
                        offset, generation = int(offset), int(generation)
                        # state should be in {"f", "n"}
                        state = line[17]

                        # Probably stream is a byte string and we need to
                        # convert a single line[k] to str
                        if isinstance(state, int):
                            state = chr(state)

                        if state not in "fn":
                            raise PdfReadError(
                                "Error in Cross-Reference table with object "
                                "(%d, %d): third item (18th byte) should be "
                                "either 'n' or 'f', found '%c'"
                                % (currid, offset, state)
                            )

                        if generation not in self._xref_table:
                            self._xref_table[generation] = {}
                        if currid in self._xref_table[generation]:
                            # It really seems like we should allow the last
                            # xref table in the file to override previous
                            # ones. Since we read the file backwards, assume
                            # any existing key is already set correctly.
                            pass
                        else:
                            self._xref_table[generation][currid] = (offset, state == "f")

                        cnt += 1
                        currid += 1

                    read_non_whitespace(stream)
                    stream.seek(-1, 1)
                    trailertag = stream.read(7)

                    if trailertag != by_("trailer"):
                        # More xrefs!
                        stream.seek(-7, 1)
                    else:
                        break

                read_non_whitespace(stream)
                stream.seek(-1, 1)
                new_trailer = read_object(stream, self)

                for key, value in new_trailer.items():
                    if key not in self._trailer:
                        self._trailer[key] = value

                if "/XRefStm" in new_trailer:
                    startxref = new_trailer["/XRefStm"]
                    del self._trailer["/XRefStm"] #to ensure there will be no loops
                elif "/Prev" in new_trailer:
                    startxref = new_trailer["/Prev"]
                    del self._trailer["/Prev"] #to ensure there will be no loops
                else:
                    break
            elif x__.isdigit():  # PDF 1.5+ Cross-Reference Stream
                stream.seek(-1, 1)
                xrefstm_offset = stream.tell()
                xrefstm_id, xrefstm_gen = self._read_object_header(stream)
                xrefstream = read_object(stream, self)

                if xrefstream["/Type"] != "/XRef":
                    raise PdfReadError(
                        "The type of this object should be /XRef, found %s "
                        "instead" % xrefstream["/Type"]
                    )

                self._cache_indirectobj(xrefstm_gen, xrefstm_id, xrefstream)

                stream_data = BytesIO(by_(xrefstream.get_data()))
                # Index pairs specify the subsections in the dictionary. If
                # none create one subsection that spans everything.
                idrange = xrefstream.get("/Index", [0, xrefstream.get("/Size")])

                entry_sizes = xrefstream.get("/W")

                if len(entry_sizes) < 3:
                    raise PdfReadError(
                        "Insufficient number of /W entries: %s" % entry_sizes
                    )
                if self.strict and len(entry_sizes) > 3:
                    raise PdfReadError("Excess number of /W entries: %s" % entry_sizes)

                # Iterate through each subsection
                last_end = 0

                for start, size in pairs(idrange):
                    # The subsections must increase
                    assert start >= last_end
                    last_end = start + size

                    for idnum in range(start, start + size):
                        # The first entry is the type
                        xref_type = _get_entry(0, stream_data)

                        # The rest of the elements depend on the xref_type
                        if xref_type == 0:
                            # Linked list of free objects
                            next_free_object = _get_entry(1, stream_data)
                            next_generation = _get_entry(2, stream_data)

                            self._xref_stm[idnum] = (0, next_free_object, next_generation)
                        elif xref_type == 1:
                            # Objects that are in use but are not compressed
                            byte_offset = _get_entry(1, stream_data)
                            generation = _get_entry(2, stream_data)

                            if not _used_before(idnum, generation):
                                self._xref_stm[idnum] = (1, byte_offset, generation)
                        elif xref_type == 2:
                            # Compressed objects
                            obj_stmid = _get_entry(1, stream_data)
                            local_id = _get_entry(2, stream_data)
                            # According to PDF spec table 18, generation is 0

                            if not _used_before(idnum, 0):
                                self._xref_stm[idnum] = (2, obj_stmid, local_id)
                        elif self.strict:
                            raise PdfReadError("Unknown xref type: %s" % xref_type)

                # As we've seen this happen, if the XRef Stream wasn't indexed
                # in neither the XRef Table or within itself, we artificially
                # add it with a /W type value of 1 (used but uncompressed
                # objects).
                if not _used_before(xrefstm_id, xrefstm_gen):
                    self._xref_stm[xrefstm_id] = (1, xrefstm_offset, xrefstm_gen)

                for key in ("/Root", "/Encrypt", "/Info", "/ID", "/Prev"):
                    if key in xrefstream and key not in self._trailer:
                        self._trailer[NameObject(key)] = xrefstream.rawGet(key)

                #based on other software, the Previous Prev shall also be processed...
                if "/Prev" in self._trailer:  ##ppZZ  : /Prev was collected/updated before
                    startxref = self._trailer["/Prev"]
                    del self._trailer["/Prev"] #to ensure there will be no loops
                else:
                    break
            else:
                # Bad xref character at startxref.  Let's see if we can find
                # the xref table nearby, as we've observed this error with an
                # off-by-one before.
                stream.seek(-11, 1)
                tmp = stream.read(20)
                xref_loc = tmp.find(by_("xref"))

                if xref_loc != -1:
                    startxref -= 10 - xref_loc
                    continue
                # No explicit xref table, try finding a cross-reference stream.
                stream.seek(startxref, 0)
                found = False

                for look in range(5):
                    if stream.read(1).isdigit():
                        # This is not a standard PDF, consider adding a warning
                        startxref += look
                        found = True
                        break
                if found:
                    continue
                # No xref table found at specified location
                raise PdfReadError("Could not find xref table at specified location")

        # If not zero-indexed, verify that the table is correct; change it if
        # necessary
        if self._xref_idx and not self.strict:
            loc = stream.tell()

            for gen in self._xref_table:
                if gen == 65535:
                    continue

                for this_id in self._xref_table[gen]:
                    stream.seek(self._xref_table[gen][this_id][0], 0)

                    try:
                        pid, _pgen = self._read_object_header(stream)
                    except ValueError:
                        break

                    if pid == this_id - self._xref_idx:
                        self._zero_xref(gen)
                        break
                    # If not, then either it's just plain wrong, or the
                    # non-zero-index is actually correct

            # Return to where it was
            stream.seek(loc, 0)

    def _decrypt_obj(self, obj, key):
        if isinstance(obj, (ByteStringObject, TextStringObject)):
            obj = create_string_object(RC4Encrypt(key, obj.original_bytes))
        elif isinstance(obj, StreamObject):
            obj._data = RC4Encrypt(key, obj._data)                              #pylint: already validated disable=protected-access
        elif isinstance(obj, DictionaryObject):
            for dictkey, value in list(obj.items()):
                obj[dictkey] = self._decrypt_obj(value, key)
        elif isinstance(obj, ArrayObject):
            for i__, k__ in enumerate(obj):
                obj[i__] = self._decrypt_obj(k__, key)

        return obj

    def _read_object_header(self, stream):
        # Should never be necessary to read out whitespace, since the
        # cross-reference table should put us in the right spot to read the
        # object header.  In reality... some files have stupid cross reference
        # tables that are off by whitespace bytes.
        extra = False
        skip_over_comment(stream)
        extra |= skip_over_whitespace(stream)
        stream.seek(-1, 1)

        idnum = readUntilWhitespace(stream)
        extra |= skip_over_whitespace(stream)
        stream.seek(-1, 1)

        generation = readUntilWhitespace(stream)
        _obj = stream.read(3)
        read_non_whitespace(stream)
        stream.seek(-1, 1)

        if extra and self.strict:
            # Not a fatal error
            warnings.warn(
                "Superfluous whitespace found in object header %s %s"
                % (idnum, generation),
                PdfReadWarning,
            )

        return int(idnum), int(generation)

    def _cache_indirectobj(self, generation, idnum, obj):
        # Sometimes we want to turn off cache for debugging.
        if (generation, idnum) in self._cached_objs:
            msg = "Overwriting cache for %s %s" % (generation, idnum)

            if self.strict:
                raise PdfReadError(msg)
            warnings.warn(msg)
        self._cached_objs[(generation, idnum)] = obj
        return obj

    def _zero_xref(self, generation):
        self._xref_table[generation] = dict(
            (id - self._xref_idx, v)
            for (id, v) in list(self._xref_table[generation].items())
        )

    @staticmethod
    def _read_next_eol(stream):
        line = by_("")

        while True:
            # Prevent infinite loops in malformed PDFs
            if stream.tell() == 0:
                raise PdfReadError("Could not read malformed PDF file")
            x__ = stream.read(1)

            if stream.tell() < 2:
                raise PdfReadError("EOL marker not found")

            stream.seek(-2, 1)

            if x__ == by_("\n") or x__ == by_("\r"):  # \n = LF; \r = CR
                crlf = False
                while x__ == by_("\n") or x__ == by_("\r"):
                    x__ = stream.read(1)
                    if x__ == by_("\n") or x__ == by_("\r"):  # account for CR+LF
                        stream.seek(-1, 1)
                        crlf = True
                    if stream.tell() < 2:
                        raise PdfReadError("EOL marker not found")
                    stream.seek(-2, 1)
                # If using CR+LF, go back 2 bytes, else 1
                stream.seek(2 if crlf else 1, 1)
                break
            line = x__ + line
        return line

    def decrypt(self, password):
        """
        When using an encrypted/secured PDF file with the PDF Standard
        encryption handler, this function will allow the file to be decrypted.
        It checks the given password against the document's user password and
        owner password, and then stores the resulting decryption key if either
        password is correct.

        It does not matter which password was matched.  Both passwords provide
        the correct decryption key that will allow the document to be used with
        this library.

        :param str password: The password to match.
        :return: ``0`` if the password failed, ``1`` if the password matched
            the user password, and ``2`` if the password matched the owner
            password.
        :rtype: int
        :raises NotImplementedError: if document uses an unsupported encryption
            method.
        """
        self._override_encryption = True
        try:
            return self._decrypt(password)
        finally:
            self._override_encryption = False

    def _decrypt(self, password):
        encrypt = self._trailer["/Encrypt"].getObject()

        if encrypt["/Filter"] != "/Standard":
            raise NotImplementedError(
                "only Standard PDF encryption handler is available"
            )
        if not encrypt["/V"] in (1, 2):
            raise NotImplementedError(
                "only algorithm codes 1 and 2 are supported. This PDF uses "
                "code %s" % encrypt["/V"]
            )
        user_password, key = self._authenticate_user_password(password)

        if user_password:
            self._decryption_key = key
            return 1
        rev = encrypt["/R"].getObject()

        if rev == 2:
            keylen = 5
        else:
            keylen = encrypt["/Length"].getObject() // 8

        key = _alg33_1(password, rev, keylen)
        real_o = encrypt["/O"].getObject()

        if rev == 2:
            userpass = RC4Encrypt(key, real_o)
        else:
            val = real_o
            for i in range(19, -1, -1):
                new_key = by_("")
                for k__ in key:
                    new_key += by_(chr(pypdfOrd(k__) ^ i))
                val = RC4Encrypt(new_key, val)
            userpass = val
        owner_password, key = self._authenticate_user_password(userpass)
        if owner_password:
            self._decryption_key = key
            return 2
        return 0

    def _authenticate_user_password(self, password):
        encrypt = self._trailer["/Encrypt"].getObject()
        rev = encrypt["/R"].getObject()
        owner_entry = encrypt["/O"].getObject()
        p_entry = encrypt["/P"].getObject()
        id_entry = self._trailer["/ID"].getObject()
        id1_entry = id_entry[0].getObject()
        real_u = encrypt["/U"].getObject().original_bytes

        if rev == 2:
            u__, key = _alg34(password, owner_entry, p_entry, id1_entry)
        elif rev >= 3:
            u__, key = _alg35(
                password,
                rev,
                encrypt["/Length"].getObject() // 8,
                owner_entry,
                p_entry,
                id1_entry,
                encrypt.get("/EncryptMetadata", BooleanObject(False)).getObject(),
            )
            u__, real_u = u__[:16], real_u[:16]

        return u__ == real_u, key

    @property
    def is_encrypted(self):                                  #pylint: too hudge change for the moment disable=invalid-name
        """ return True if filed is encrypted """
        return "/Encrypt" in self._trailer
    isEncrypted = is_encrypted
