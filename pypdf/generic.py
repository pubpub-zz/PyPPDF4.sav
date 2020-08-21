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

import math
import re
import uuid
import warnings

from .utils import (PdfStreamError, PageSizeNotDefinedError,                #pylint: disable=relative-beyond-top-level
                    PdfReadError, PdfReadWarning, WHITESPACES, BytesIO,   #version_info,
                    read_non_whitespace, read_until_regex, skip_over_comment, matrixMultiply,
                    pypdfUnicode, pypdfBytes as by_, RC4Encrypt, hexStr, pypdfOrd, is_string)
from  .generic1 import (PdfObject, NullObject, BooleanObject,               #pylint: disable=relative-beyond-top-level,unused-import
                        FloatObject, NumberObject, ByteStringObject, TextStringObject,
                        NameObject, encode_pdf_doc_encoding, decode_pdf_doc_encoding,    #pylint: force decode_pdf_doc_encoding in case of disable=unused-import
                        create_string_object, _pdfDocEncoding, _pdfDocEncoding_rev)
from .filters import decode_stream_data, FlateCodec                         #pylint: disable=relative-beyond-top-level
from . import xmp                                                           #pylint: disable=relative-beyond-top-level


__author__ = "Mathieu Fenniak"
__author_email__ = "biziqe@mathieu.fenniak.net"

ObjectPrefix = by_("/<[tf(n%")
NumberSigns = by_("+-")
IndirectPattern = re.compile(by_(r"[+-]?(\d+)\s+(\d+)\s+R[^a-zA-Z]"))

#alias for previous API
createStringObject = create_string_object

def read_object(stream, pdf):
    """
    TODO : documentation
    """
    #pylint: disable=too-many-return-statements,too-many-branches
    tok = stream.read(1)
    stream.seek(-1, 1)  # reset to start
    idx = ObjectPrefix.find(tok)

    if idx == 0:  # name object
        return NameObject.readFromStream(stream, pdf)
    if idx == 1:  # hexadecimal string OR dictionary
        peek = stream.read(2)
        stream.seek(-2, 1)  # reset to start

        if peek == by_("<<"):
            return DictionaryObject.readFromStream(stream, pdf)
        return read_hexstring_from_stream(stream)
    if idx == 2:  # array object
        return ArrayObject.readFromStream(stream, pdf)
    if idx in (3, 4):  # boolean object
        return BooleanObject.readFromStream(stream)
    if idx == 5:  # string object
        return read_string_from_stream(stream)
    if idx == 6:  # null object
        return NullObject.readFromStream(stream)
    if idx == 7:  # comment
        while tok not in (by_("\r"), by_("\n")):
            tok = stream.read(1)
            # Prevents an infinite loop by raising an error if the stream is at
            # the EOF
            if len(tok) <= 0:
                raise PdfStreamError("File ended unexpectedly.")
        tok = read_non_whitespace(stream)
        stream.seek(-1, 1)

        return read_object(stream, pdf)
    #else:  # number object OR indirect reference
    peek = stream.read(20)
    stream.seek(-len(peek), 1)  # reset to start

    if IndirectPattern.match(peek) is not None:
        return IndirectObject.readFromStream(stream, pdf)
    return NumberObject.readFromStream(stream)


#class PdfObject(object):                    # defined in generic1
#class NullObject(PdfObject):                # defined in generic1
#class BooleanObject(PdfObject):             # defined in generic1

class ArrayObject(list, PdfObject):
    """
    pdf array object
    """
    def __init__(self, arr=None):
        super().__init__(self)
        if arr is not None:
            self.extend(arr)

    def clone(self, pdf_dest):  #PPzz
        """ clone object into pdf_dest """
        arr = ArrayObject()
        for data in self:
            if 'clone' in dir(data):
                arr.append(data.clone(pdf_dest))
            else:
                arr.append(data)
        return arr

    def writeToStream(self, stream, encryption_key):            #pylint: too hudge change for the moment disable=invalid-name
        """ write to stream/file """
        stream.write(by_("["))

        for data in self:
            stream.write(by_(" "))
            data.writeToStream(stream, encryption_key)

        stream.write(by_(" ]"))

    @staticmethod
    def readFromStream(stream, pdf):                            #pylint: too hudge change for the moment disable=invalid-name
        """ read from stream/file """
        arr = ArrayObject()
        tmp = stream.read(1)

        if tmp != by_("["):
            raise PdfReadError("Could not read array")
        while True:
            # skip leading whitespace
            tok = stream.read(1)

            while tok.isspace():
                tok = stream.read(1)

            stream.seek(-1, 1)
            # check for array ending
            peekahead = stream.read(1)

            if peekahead == by_("]"):
                break

            stream.seek(-1, 1)
            # read and append obj
            arr.append(read_object(stream, pdf))

        return arr


class IndirectObject(PdfObject):
    """
    indirect pdf object
    """
    def __init__(self, idnum, generation, pdf):
        """
        Represents an indirect generic object whose declaration in the File
        Body is something like

        ``123 0 obj``\n
        ``...``\n
        ``endobj``

        :param idnum: identifying number of this indirect reference.
        :param generation: generation number, used for marking batch updates.
        :param pdf: the :class:`PdfFileReader<pdf.PdfFileReader>` or
            :class:`PdfFileWriter<pdf.PdfFileWriter>` instance associated with
            this object.
        """
        self.idnum = idnum
        self.generation = generation
        self.pdf = pdf

    def clone(self, pdf_dest):  #PPzz
        """ clone object into pdf_dest """
        #pylint: _id_translated is well protected/hidden but its known disable=protected-access
        try:
            pdf_dest._id_translated
        except:                     #pylint: disable=bare-except
            pdf_dest._id_translated = {}
        try:
            n__ = pdf_dest._id_translated[self.idnum]
        except:                     #pylint: disable=bare-except
            n__ = len(pdf_dest._objects)+1
            pdf_dest._id_translated[self.idnum] = n__
            pdf_dest._objects.append("%d NotInit"%n__)
            if isinstance(self.getObject(), (PdfBaseDocument)):
                print("clone Doc")
                pdf_dest._objects[n__-1] = pdf_dest
            else:
                pdf_dest._objects[n__-1] = self.getObject().clone(pdf_dest)

        return IndirectObject(n__, 0, pdf_dest)

    def getObject(self):                 #pylint: too hudge change for the moment disable=invalid-name
        """ return the pointed object """
        return self.pdf.getObject(self).getObject()

    def __repr__(self):
        return "IndirectObject(%r, %r)" % (self.idnum, self.generation)

    def __eq__(self, other):
        return (
            other is not None
            and isinstance(other, IndirectObject)
            and self.idnum == other.idnum
            and self.generation == other.generation
            and self.pdf is other.pdf
        )

    def __ne__(self, other):
        return not self.__eq__(other)

    def writeToStream(self, stream, encryption_key):        #pylint: too hudge change for the moment disable=invalid-name,unused-argument
        """ write to stream/file """
        stream.write(by_("%s %s R" % (self.idnum, self.generation)))

    @staticmethod
    def readFromStream(stream, pdf):                        #pylint: too hudge change for the moment disable=invalid-name
        """ read from stream/file """
        idnum = by_("")

        while True:
            tok = stream.read(1)
            if not tok:
                # stream has truncated prematurely
                raise PdfStreamError("Stream has ended unexpectedly")
            if tok.isspace():
                break
            idnum += tok

        generation = by_("")

        while True:
            tok = stream.read(1)

            if not tok:
                # stream has truncated prematurely
                raise PdfStreamError("Stream has ended unexpectedly")
            if tok.isspace():
                if not generation:
                    continue
                break

            generation += tok

        if read_non_whitespace(stream) != by_("R"):
            raise PdfReadError(
                "Error reading indirect object reference at byte %s"
                % hexStr(stream.tell())
            )

        return IndirectObject(int(idnum), int(generation), pdf)


#class FloatObject(PdfObject):             # defined in generic1
#class NumberObject(int, PdfObject):       # defined in generic1

def read_hexstring_from_stream(stream):
    """ read hex string data from stream/data """
    stream.read(1)
    txt = ""
    x__ = by_("")

    while True:
        tok = read_non_whitespace(stream)
        if not tok:
            # stream has truncated prematurely
            raise PdfStreamError("Stream has ended unexpectedly")
        if tok == by_(">"):
            break

        x__ += tok

        if len(x__) == 2:
            txt += chr(int(x__, base=16))
            x__ = by_("")

    if len(x__) == 1:
        x__ += by_("0")
    if len(x__) == 2:
        txt += chr(int(x__, base=16))

    return create_string_object(by_(txt))


def read_string_from_stream(stream):
    """
    read string from stream/data
    """
    #pylint: disable=too-many-branches
    tok = stream.read(1)
    parens = 1
    txt = by_("")

    while True:
        tok = stream.read(1)

        if not tok:
            # stream has truncated prematurely
            raise PdfStreamError("Stream has ended unexpectedly")
        if tok == by_("("):
            parens += 1
        elif tok == by_(")"):
            parens -= 1
            if parens == 0:
                break
        elif tok == by_("\\"):
            tok = stream.read(1)
            escape_dict = {
                by_("n"): by_("\n"),
                by_("r"): by_("\r"),
                by_("t"): by_("\t"),
                by_("b"): by_("\b"),
                by_("f"): by_("\f"),
                by_("c"): by_("\c"),          #pylint: disable=anomalous-backslash-in-string
                by_("("): by_("("),
                by_(")"): by_(")"),
                by_("/"): by_("/"),
                by_("\\"): by_("\\"),
                by_(" "): by_(" "),
                by_("/"): by_("/"),
                by_("%"): by_("%"),
                by_("<"): by_("<"),
                by_(">"): by_(">"),
                by_("["): by_("["),
                by_("]"): by_("]"),
                by_("#"): by_("#"),
                by_("_"): by_("_"),
                by_("&"): by_("&"),
                by_("$"): by_("$"),
            }

            try:
                tok = escape_dict[tok]
            except KeyError:
                if tok.isdigit():
                    # "The number ddd may consist of one, two, or three
                    # octal digits; high-order overflow shall be ignored.
                    # Three octal digits shall be used, with leading zeros
                    # as needed, if the next character of the string is also
                    # a digit." (PDF reference 7.3.4.2, p 16)
                    for _ in range(2):
                        ntok = stream.read(1)
                        if ntok.isdigit():
                            tok += ntok
                        else:
                            break
                    tok = by_(chr(int(tok, base=8)))
                elif tok in by_("\n\r"):
                    # This case is  hit when a backslash followed by a line
                    # break occurs.  If it's a multi-char EOL, consume the
                    # second character:
                    tok = stream.read(1)

                    if not tok in by_("\n\r"):
                        stream.seek(-1, 1)
                    # Then don't add anything to the actual string, since this
                    # line break was escaped:
                    tok = by_("")
                else:
                    raise PdfReadError(r"Unexpected escaped string: %s" % tok)
        txt += tok

    return create_string_object(txt)

#class ByteStringObject(bytes_type, PdfObject):             #defined in generic1
#class TextStringObject(string_type, PdfObject):            #defined in generic1
#class NameObject(str, PdfObject):                          #defined in generic1

class DictionaryObject(dict, PdfObject):
    """
    PDF Dictionnary Object
    """
    def clone(self, pdf_dest):  #PPzz
        """ clone object into pdf_dest """
        d__ = self.__class__()
        d__._clone(self, pdf_dest)                          #pylint: disable=protected-access
        return d__

    def _clone(self, src, pdf_dest, ignore_fields=()):
        """ update the object from src """
        for k__, v__ in src.items():
            if not k__ in ignore_fields:
                self.update({(k__.clone(pdf_dest) if 'clone' in dir(k__) else k__):
                             (v__.clone(pdf_dest) if 'clone' in dir(v__) else v__)})

    def rawGet(self, key):                #pylint: too hudge change for the moment disable=invalid-name
        """
        getback the pointed indirect object not the object that is pointed
        """
        return dict.__getitem__(self, key)

    def __setitem__(self, key, value):
        if isinstance(key, str):
            key = NameObject(key)
        if not isinstance(key, PdfObject):
            raise ValueError("key must be PdfObject")
        if not isinstance(value, PdfObject):
            raise ValueError("value must be PdfObject")

        return dict.__setitem__(self, key, value)

    def setdefault(self, key, value=None):
        if not isinstance(key, PdfObject):
            raise ValueError("key must be PdfObject")
        if not isinstance(value, PdfObject):
            raise ValueError("value must be PdfObject")

        return dict.setdefault(self, key, value)

    def __getitem__(self, key):
        return dict.__getitem__(self, key).getObject()

    def get_xmp_metadata(self):           #pylint: too hudge change for the moment disable=invalid-name
        """
        Retrieves XMP (Extensible Metadata Platform) data relevant to this
        object, if available.

        Added in v1.12, will exist for all future v1.x releases.

        :return: a :class:`XmpInformation<xmp.XmpInformation>` instance that
        can be used to access XMP metadata from the document.  Can also return
        ``None`` if no metadata was found on the document root.
        """
        metadata = self.get("/Metadata", None)

        if metadata is None:
            return None

        metadata = metadata.getObject()

        if not isinstance(metadata, xmp.XmpInformation):
            metadata = xmp.XmpInformation(metadata)
            self[NameObject("/Metadata")] = metadata

        return metadata
    getXmpMetadata = get_xmp_metadata
    xmpMetadata = xmp_metadata = property(get_xmp_metadata)
    """
    Read-only property that accesses the
    :meth:`getXmpData<DictionaryObject.getxmpData>` function.

    Added in v1.12, will exist for all future v1.x releases.
    """

    def writeToStream(self, stream, encryption_key):        #pylint: too hudge change for the moment disable=invalid-name
        """ write to stream/file """
        stream.write(by_("<<\n"))

        for key, value in list(self.items()):
            key.writeToStream(stream, encryption_key)
            stream.write(by_(" "))
            value.writeToStream(stream, encryption_key)
            stream.write(by_("\n"))

        stream.write(by_(">>"))

    @staticmethod
    def readFromStream(stream, pdf):                       #pylint: too hudge change for the moment disable=invalid-name
        """ read from stream/file """
        #pylint: already validated code disable=too-many-locals,too-many-branches, too-many-statements
        debug = False
        data = {}
        buff = stream.read(2)

        if buff != by_("<<"):
            raise PdfReadError(
                "Dictionary read error at byte %s: stream must begin with '<<'"
                % hexStr(stream.tell())
            )

        while True:
            tok = read_non_whitespace(stream)

            if tok == by_("\x00"):
                continue
            if tok == by_("%"):
                stream.seek(-1, 1)
                skip_over_comment(stream)
                continue
            if not tok:
                # stream has truncated prematurely
                raise PdfStreamError("Stream has ended unexpectedly")

            if debug:
                print("Tok:", tok)

            if tok == by_(">"):
                stream.read(1)
                break

            stream.seek(-1, 1)
            key = read_object(stream, pdf)
            tok = read_non_whitespace(stream)
            stream.seek(-1, 1)
            value = read_object(stream, pdf)

            if not data.get(key):
                data[key] = value
            elif pdf.strict:
                # multiple definitions of key not permitted
                raise PdfReadError(
                    "Multiple definitions in dictionary at byte %s for key %s"
                    % (hexStr(stream.tell()), key)
                )
            else:
                warnings.warn(
                    "Multiple definitions in dictionary at byte %s for key %s"
                    % (hexStr(stream.tell()), key),
                    PdfReadWarning,
                )

        pos = stream.tell()
        s__ = read_non_whitespace(stream)

        if s__ == by_("s") and stream.read(5) == by_("tream"):
            eol = stream.read(1)
            # Odd PDF file output has spaces after 'stream' keyword but before
            # EOL. Patch provided by Danial Sandler
            while eol == by_(" "):
                eol = stream.read(1)
            assert eol in (by_("\n"), by_("\r"))

            if eol == by_("\r"):
                # read \n after
                if stream.read(1) != by_("\n"):
                    stream.seek(-1, 1)

            # this is a stream object, not a dictionary
            assert "/Length" in data
            length = data["/Length"]

            if debug:
                print(data)
            if isinstance(length, IndirectObject):
                t__ = stream.tell()
                length = pdf.getObject(length)
                stream.seek(t__, 0)
            data["__streamdata__"] = stream.read(length)

            if debug:
                print("here")
            e__ = read_non_whitespace(stream)
            ndstream = stream.read(8)

            if (e__ + ndstream) != by_("endstream"):
                # (sigh) - the odd PDF file has a length that is too long, so
                # we need to read backwards to find the "endstream" ending.
                # ReportLab (unknown version) generates files with this bug,
                # and Python users into PDF files tend to be our audience.
                # we need to do this to correct the streamdata and chop off
                # an extra character.
                pos = stream.tell()
                stream.seek(-10, 1)
                end = stream.read(9)

                if end == by_("endstream"):
                    # we found it by looking back one character further.
                    data["__streamdata__"] = data["__streamdata__"][:-1]
                else:
                    stream.seek(pos, 0)

                    raise PdfReadError(
                        "Unable to find 'endstream' marker after stream at "
                        "byte %s." % hexStr(stream.tell())
                    )
        else:
            stream.seek(pos, 0)
        if "__streamdata__" in data:
            return StreamObject.initialize_from_dictionnary(data)
        retval = DictionaryObject()
        retval.update(data)

        return retval


class TreeObject(DictionaryObject):
    """
    Pdf Tree Object
    """
    def __init__(self):
        DictionaryObject.__init__(self)

    def has_children(self):
        """ return True if has at least one child """
        return "/First" in self

    def __iter__(self):
        return self.children()

    def children(self):
        """ provide an iteratro through the children """
        if not self.has_children():
            return #raise StopIteration

        child = self["/First"]
        while True:
            yield child
            if child == self["/Last"]:
                return #raise StopIteration
            child = child["/Next"]

    def add_child(self, child, pdf, before=None):
        """
        add a child to the tree at the good position,
        apparently this function deals only with outlines
        child:  object to be inserted;
                ensure the object refers to the good pdf
        pdf: PdfFileWriter
        before: the object before which to insert
        """
        child_object = child.getObject()
        if before is not None and not isinstance(before, IndirectObject):
            before = pdf.get_reference(before)

        # if no data in the linked list
        if "/First" not in self:
            self[NameObject("/First")] = child
            self[NameObject("/Last")] = child
            try:
                c__ = abs(child_object["/Count"])
            except KeyError:
                c__ = 1
            self[NameObject("/Count")] = NumberObject(-c__ if "/Parent" in self else c__)
            child_object[NameObject("/Parent")] = pdf.get_reference(self)
            return child

        first_ = self.rawGet("/First")
        next_ = first_
        curr_ = None

        #child has to be append at the end of the list
        if before is None:
            prev_ = self.rawGet("/Last")
            self[NameObject("/Last")] = child
            try:
                del child_object["/Next"]
            except KeyError:
                pass
            child_object[NameObject("/Prev")] = prev_
            prev_.getObject()[NameObject("/Next")] = child
        else: # I prefer to get through the list to
            last_ = self.rawGet("/Last")
            while next_ not in (before, last_):
                curr_ = next_
                next_ = next_.getObject().rawGet('/Next')

            assert next_ == before, ValueError("not found in the list", before, self)

            if curr_ is None: #we insert at the beginning
                self[NameObject("/First")] = child
                try:
                    del child_object["/Prev"]
                except KeyError:
                    pass
            else:           #in the middle of the list
                curr_.get_object()[NameObject("/Next")] = child
                child_object[NameObject("/Prev")] = curr_
            child_object[NameObject("/Next")] = next_
            next_.get_object()[NameObject("/Prev")] = child

        child_object["/Parent"] = pdf.get_reference(self)
#       solution with all outlines folded
        c__ = abs(self["/Count"])+1 if "/Count" in self else 1
        self[NameObject("/Count")] = NumberObject(-c__)
##        p__ = child_object
##        c__ = abs(p__["/Count"]) if "/Count" in p__ else 1
##        c1_ = c__
##        pa_ = True
##        while pa_:
##            p__ = p__["/Parent"].getObject()
##            pa_ = "/Parent" in p__
##            c__ += c1_ #abs(p__["/Count"])
##            p__[NameObject("/Count")] = NumberObject(-c__ if pa_ else c__)

        return child

    def remove_child(self, child):
        """ remove child from tree object """
        child_obj = child.getObject()

        assert "/Parent" in child_obj,\
            ValueError("Removed child does not appear to be a tree item")
        assert child_obj["/Parent"] == self,\
            ValueError("Removed child is not a member of this tree")

        if self["/Count"] == 0:
            return None

        last_ = self.rawGet("/Last")
        if child == last_:
            if child == self.rawGet("/First"):
                #it means that there will be no data left after
                del self["/First"]
                del self["/Last"]
                self[NameObject["/Count"]] = NumberObject(0)
                #no prev/next to delete from child, and we will leave Parent
                return child
            self[NameObject("/Last")] = child_obj.rawGet("/Prev")
        if child == self.rawGet("/First"):
            self[NameObject("/First")] = child.rawGet("/Next")

        try:
            child_obj["/Prev"][NameObject("/Next")] = child_obj.rawGet("/Next")
        except KeyError as e:
            #if "/Prev" does not exist, so nothing to do
            if "/Next" in e.args:   #it means no "/Next" in child
                del child_obj["/Prev"][NameObject("/Next")]
        try:
            child_obj["/Next"][NameObject("/Prev")] = child_obj.rawGet("/Prev")
        except KeyError as e:
            #if "/Next" does not exist, so nothing to do
            if "/Prev" in e.args:   #it means no "/Next" in child
                del child_obj["/Next"][NameObject("/Prev")]

        c__ = abs(child["/Count"]) if "/Count" in child else 1
        p__ = child_obj
        pa_ = True
        while pa_:
            p__ = p__["/Parent"].getObject()
            pa_ = "/Parent" in p__
            c__ = abs(p__["/Count"]) - c__
            p__[NameObject("/Count")] = NumberObject(-c__ if pa_ else c__)

        try:
            del child_obj["/Prev"]
        except KeyError:
            pass
        try:
            del child_obj["/Next"]
        except KeyError:
            pass

        return child
    def _remove_child(self, child):
        """ remove child from tree object """
        #pylint: code already validated disable=too-many-branches,too-many-statements
        child_obj = child.getObject()

        if NameObject("/Parent") not in child_obj:
            raise ValueError("Removed child does not appear to be a tree item")
        if child_obj[NameObject("/Parent")] != self:
            raise ValueError("Removed child is not a member of this tree")

        found = False
        prev_ref = None
        prev_ = None
        cur_ref = self[NameObject("/First")]
        cur = cur_ref.getObject()
        last_ref = self[NameObject("/Last")]
        last_ = last_ref.getObject()

        while cur is not None:
            if cur == child_obj:
                if prev_ is None:
                    if NameObject("/Next") in cur:
                        # Removing first tree node
                        next_ref = cur[NameObject("/Next")]
                        next_ = next_ref.getObject()
                        del next_[NameObject("/Prev")]
                        self[NameObject("/First")] = next_ref
                        self[NameObject("/Count")] = self[NameObject("/Count")] - 1

                    else:
                        # Removing only tree node
                        assert self[NameObject("/Count")] == 1
                        del self[NameObject("/Count")]
                        del self[NameObject("/First")]
                        if NameObject("/Last") in self:
                            del self[NameObject("/Last")]
                else:
                    if NameObject("/Next") in cur:
                        # Removing middle tree node
                        next_ref = cur[NameObject("/Next")]
                        next_ = next_ref.getObject()
                        next_[NameObject("/Prev")] = prev_ref
                        prev_[NameObject("/Next")] = next_ref           #pylint: false-positive ? disable=unsupported-assignment-operation
                        self[NameObject("/Count")] = self[NameObject("/Count")] - 1
                    else:
                        # Removing last tree node
                        assert cur == last_
                        del prev_[NameObject("/Next")]                  #pylint: false-positive ? disable=unsupported-delete-operation
                        self[NameObject("/Last")] = prev_ref
                        self[NameObject("/Count")] = self[NameObject("/Count")] - 1
                found = True
                break

            prev_ref = cur_ref
            prev_ = cur
            if NameObject("/Next") in cur:
                cur_ref = cur[NameObject("/Next")]
                cur = cur_ref.getObject()
            else:
                cur_ref = None
                cur = None

        if not found:
            raise ValueError("Removal couldn't find item in tree")

        del child_obj[NameObject("/Parent")]
        if NameObject("/Next") in child_obj:
            del child_obj[NameObject("/Next")]
        if NameObject("/Prev") in child_obj:
            del child_obj[NameObject("/Prev")]

    def empty_tree(self):
        """ remove all children objects """
        for child in self:
            child_obj = child.getObject()
            del child_obj[NameObject("/Parent")]
            if NameObject("/Next") in child_obj:
                del child_obj[NameObject("/Next")]
            if NameObject("/Prev") in child_obj:
                del child_obj[NameObject("/Prev")]

        if NameObject("/Count") in self:
            del self[NameObject("/Count")]
        if NameObject("/First") in self:
            del self[NameObject("/First")]
        if NameObject("/Last") in self:
            del self[NameObject("/Last")]


class StreamObject(DictionaryObject):
    """
    pdf stream object
    """
    def __init__(self):
        super(StreamObject, self).__init__()
        self._data = None
        self.decoded_self = None

    def clone(self, pdf_dest):  #PPzz
        """ clone object into pdf_dest """
        #pylint: acceptable disable=protected-access
        st_ = self.__class__()
        st_._data = self._data
        st_.decoded_self = self.decoded_self
        st_._clone(self, pdf_dest)
        return st_

    def writeToStream(self, stream, encryption_key):
        self[NameObject("/Length")] = NumberObject(len(self._data))
        DictionaryObject.writeToStream(self, stream, encryption_key)
        del self["/Length"]
        stream.write(by_("\nstream\n"))
        data = self._data

        if encryption_key:
            data = RC4Encrypt(encryption_key, data)

        stream.write(data)
        stream.write(by_("\nendstream"))

    @staticmethod
    def initialize_from_dictionnary(data):
        """ initialize object from dictionnary """
        if "/Filter" in data:
            if data.get("/Type") == "/ObjStm":
                retval = ObjectStream()
            else:
                retval = EncodedStreamObject()
        else:
            retval = DecodedStreamObject()

        retval._data = data["__streamdata__"]           #pylint: acceptable disable=protected-access
        del data["__streamdata__"]
        del data["/Length"]
        retval.update(data)

        return retval

    def flate_encode(self):
        """
        TODO : documentation
        """
        if "/Filter" in self:
            f__ = self["/Filter"]

            if isinstance(f__, ArrayObject):
                f__.insert(0, NameObject("/FlateDecode"))
            else:
                newf = ArrayObject()
                newf.append(NameObject("/FlateDecode"))
                newf.append(f__)
                f__ = newf
        else:
            f__ = NameObject("/FlateDecode")

        retval = EncodedStreamObject()
        retval[NameObject("/Filter")] = f__
        retval._data = FlateCodec.encode(self._data)                #pylint: acceptable disable=protected-access

        return retval


class EncodedStreamObject(StreamObject):
    """
    Encoded Stream Pdf Object ????
    """
    def __init__(self):
        super().__init__()
        self.decoded_self = None

    def get_data(self):
        """ TODO : documentation """

        if self.decoded_self:
            # Cached version of decoded object
            return self.decoded_self.get_data()
        # Create decoded object
        decoded = DecodedStreamObject()
        decoded._data = decode_stream_data(self)                #pylint: acceptable disable=protected-access

        for key, value in list(self.items()):
            if not key in ("/Length", "/Filter", "/DecodeParms"):
                decoded[key] = value

        self.decoded_self = decoded

        return decoded._data                                    #pylint: acceptable disable=protected-access 

    def set_data(self, data):
        """ TODO : documentation """
        raise NotImplementedError(
            "Creating EncodedStreamObject is not currently supported"
        )


class DecodedStreamObject(StreamObject):
    """
    Decoded Stream Pdf Object ?????
    """
    def __init__(self):             #pylint: prefered to be explicit disable=useless-super-delegation
        super().__init__()

    def get_data(self):
        """ TODO : documentation """
        return self._data

    def set_data(self, data):
        """ TODO : documentation """
        self._data = data


class ContentStream(DecodedStreamObject):
    """
    TODO : documentation
    """
    def __init__(self, stream, pdf):
        super().__init__()
        self.pdf = pdf
        self.operations = []
        # stream may be a StreamObject or an ArrayObject containing
        # multiple StreamObjects to be cat'd together.
        stream = stream.getObject()

        if isinstance(stream, ArrayObject):
            data = by_("")
            for s__ in stream:
                data += by_(s__.getObject().get_data())
            stream = BytesIO(by_(data))
        else:
            stream = BytesIO(by_(stream.get_data()))

        self.parse_content_stream(stream)

    def parse_content_stream(self, stream):
        """ TODO : documentation """
        stream.seek(0, 0)
        operands = []

        while True:
            peek = read_non_whitespace(stream)

            if peek == by_("") or pypdfOrd(peek) == 0:
                break

            stream.seek(-1, 1)
            if peek.isalpha() or peek == by_("'") or peek == by_('"'):
                operator = read_until_regex(stream, NameObject.delimiterPattern, True)
                if operator == by_("BI"):
                    # Begin inline image - a completely different parsing
                    # mechanism is required
                    assert operands == []
                    ii_ = self._read_inline_image(stream)
                    self.operations.append((ii_, by_("INLINE IMAGE")))
                else:
                    self.operations.append((operands, operator))
                    operands = []
            elif peek == by_("%"):
                # If we encounter a comment in the content stream, we have to
                # handle it here.  Typically, read_object will handle
                # encountering a comment -- but read_object assumes that
                # following the comment must be the object we're trying to
                # read.  In this case, it could be an operator instead.
                while peek not in (by_("\r"), by_("\n")):
                    peek = stream.read(1)
            else:
                operands.append(read_object(stream, None))

    def _read_inline_image(self, stream):
        # Begin reading just after the "BI" - begin image
        # First read the dictionary of settings.
        settings = DictionaryObject()

        while True:
            tok = read_non_whitespace(stream)
            stream.seek(-1, 1)

            if tok == by_("I"):
                # "ID" - begin of image data
                break

            key = read_object(stream, self.pdf)
            tok = read_non_whitespace(stream)
            stream.seek(-1, 1)
            value = read_object(stream, self.pdf)
            settings[key] = value

        # Left at beginning of ID
        tmp = stream.read(3)
        assert tmp[:2] == by_("ID")
        data = by_("")

        while True:
            # Read the inline image, while checking for EI (End Image) operator
            tok = stream.read(1)

            if tok == by_("E"):
                # Check for End Image
                tok2 = stream.read(1)
                if tok2 == by_("I"):
                    # Data can contain EI, so check for the Q operator.
                    tok3 = stream.read(1)
                    info = tok + tok2
                    # We need to find whitespace between EI and Q.
                    has_q_whitespace = False

                    while tok3 in WHITESPACES:
                        has_q_whitespace = True
                        info += tok3
                        tok3 = stream.read(1)
                    if tok3 == by_("Q") and has_q_whitespace:
                        stream.seek(-1, 1)
                        break
                    stream.seek(-1, 1)
                    data += info
                else:
                    stream.seek(-1, 1)
                    data += tok
            else:
                data += tok

        return {"settings": settings, "data": data}

    def _get_data(self):
        newdata = BytesIO()

        for operands, operator in self.operations:
            if operator == by_("INLINE IMAGE"):
                newdata.write(by_("BI"))
                dicttext = BytesIO()
                operands["settings"].writeToStream(dicttext, None)
                newdata.write(dicttext.getvalue()[2:-2])
                newdata.write(by_("ID "))
                newdata.write(operands["data"])
                newdata.write(by_("EI"))
            else:
                for op_ in operands:
                    op_.writeToStream(newdata, None)
                    newdata.write(by_(" "))

                newdata.write(by_(operator))

            newdata.write(by_("\n"))

        return newdata.getvalue()

    def _set_data(self, value):
        if value:
            self.parse_content_stream(BytesIO(by_(value)))

    _data = property(_get_data, _set_data)


class ObjectStream(EncodedStreamObject):
    """
    Class intended to provide simplified access to some of object streams'
    properties.
    """
    #pylint: set_data not overriden disable=abstract-method
    DATA_HEADER_RE = re.compile(b"(?:\d+\s)+")              #pylint: disable=anomalous-backslash-in-string
    """
    Regex to match pairs of ids and offset numbers in the first part of an
    object stream data.
    """

    def __init__(self):                 #pylint: prefered to be explicit disable=useless-super-delegation
        super().__init__()

    @property
    def object_ids(self):
        """
        :return: an iterable containing a sequence of object ids sorted
            according to their appearance order, stored in the object stream
            header.
        """
        match = self.DATA_HEADER_RE.match(self.get_data())
        output = [int(n) for n in match.group().split()]

        if (len(output) % 2) != 0:
            raise PdfReadError(
                "Object stream header must contain an even list of numbers"
            )

        return tuple(output[i] for i in range(0, len(output), 2))


class DocumentInformation(DictionaryObject):
    """
    A class representing the basic document metadata provided in a PDF File.
    This class is accessible through
    :meth:`documentInfo()<pypdf.PdfFileReader.documentInfo()>`

    All text properties of the document metadata have
    *two* properties, e.g. author and author_raw. The non-raw property will
    always return a ``TextStringObject``, making it ideal for a case where
    the metadata is being displayed. The raw property can sometimes return
    a ``ByteStringObject``, if PyPDF was unable to decode the string's
    text encoding; this requires additional safety in the caller and
    therefore is not as commonly accessed.
    """

    def __init__(self):
        DictionaryObject.__init__(self)

    def get_text(self, key):
        """ TODO : documentation """
        retval = self.get(key, None)

        if isinstance(retval, TextStringObject):
            return retval

        return None

    title = property(lambda self: self.get_text("/Title"))
    """
    Read-only property accessing the document's **title**.
    Returns a unicode string (``TextStringObject``) or ``None``
    if the title is not specified.
    """

    title_raw = property(lambda self: self.get("/Title"))
    """The "raw" version of title; can return a ``ByteStringObject``."""

    author = property(lambda self: self.get_text("/Author"))
    """
    Read-only property accessing the document's **author**.
    Returns a unicode string (``TextStringObject``) or ``None``
    if the author is not specified.
    """

    author_raw = property(lambda self: self.get("/Author"))
    """The "raw" version of author; can return a ``ByteStringObject``."""

    subject = property(lambda self: self.get_text("/Subject"))
    """
    Read-only property accessing the document's **subject**.
    Returns a unicode string (``TextStringObject``) or ``None``
    if the subject is not specified.
    """

    subject_raw = property(lambda self: self.get("/Subject"))
    """The "raw" version of subject; can return a ``ByteStringObject``."""

    creator = property(lambda self: self.get_text("/Creator"))
    """
    Read-only property accessing the document's **creator**. If the
    document was converted to PDF from another format, this is the name of the
    application (e.g. OpenOffice) that created the original document from
    which it was converted. Returns a unicode string (``TextStringObject``)
    or ``None`` if the creator is not specified.
    """

    creator_raw = property(lambda self: self.get("/Creator"))
    """The "raw" version of creator; can return a ``ByteStringObject``."""

    producer = property(lambda self: self.get_text("/Producer"))
    """
    Read-only property accessing the document's **producer**.
    If the document was converted to PDF from another format, this is
    the name of the application (for example, OSX Quartz) that converted
    it to PDF. Returns a unicode string (``TextStringObject``)
    or ``None`` if the producer is not specified.
    """

    producer_raw = property(lambda self: self.get("/Producer"))
    """The "raw" version of producer; can return a ``ByteStringObject``."""

    keywords = property(lambda self: self.get_text("/Keywords"))
    """
    Read-only property accessing the document's **keywords**.
    Returns a unicode string (``TextStringObject``) or ``None``
    if the keywords are not specified.
    """

    keywords_raw = property(lambda self: self.get("/Keywords"))
    """The "raw" version of keywords; can return a ``ByteStringObject``."""


class RectangleObject(ArrayObject):
    """
    This class is used to represent *page boxes* in PyPDF. These boxes
    include:

        * :attr:`art_box<pypdf.generic.PageObject.art_box>`
        * :attr:`bleed_box<pypdf.generic.PageObject.bleed_box>`
        * :attr:`crop_box<pypdf.generic.PageObject.crop_box>`
        * :attr:`media_box<pypdf.generic.PageObject.media_box>`
        * :attr:`trim_box<pypdf.generic.PageObject.trim_box>`
    """

    def __init__(self, arr):
        # Must have four points
        assert len(arr) == 4
        # Automatically convert arr[x] into NumberObject(arr[x]) if necessary
        ArrayObject.__init__(self, [self.ensure_is_number(x) for x in arr])

    @staticmethod
    def ensure_is_number(value):
        """ return value  as a FloatObject """
        if not isinstance(value, (NumberObject, FloatObject)):
            value = FloatObject(value)
        return value

    def __repr__(self):
        return "RectangleObject(%s)" % repr(list(self))

    def get_lowerleft_x(self):
        """ return Lower Left X """
        return self[0]

    def get_lowerleft_y(self):
        """ return Lower Left Y """
        return self[1]

    def get_upperright_x(self):
        """ return Upper Right X """
        return self[2]

    def get_upperright_y(self):
        """ return Upper Right Y """
        return self[3]

    def get_upperleft_x(self):
        """ guess :) """
        return self.get_lowerleft_x()

    def get_upperleft_y(self):
        """ guess :) """
        return self.get_upperright_y()

    def get_lowerright_x(self):
        """ guess :) """
        return self.get_upperright_x()

    def get_lowerright_y(self):
        """ guess :) """
        return self.get_lowerleft_y()

    def get_lowerleft(self):
        """ guess :) """
        return self.get_lowerleft_x(), self.get_lowerleft_y()

    def get_lowerright(self):
        """ guess :) """
        return self.get_lowerright_x(), self.get_lowerright_y()

    def get_upperleft(self):
        """ guess :) """
        return self.get_upperleft_x(), self.get_upperleft_y()

    def get_upperright(self):
        """ guess :) """
        return self.get_upperright_x(), self.get_upperright_y()

    def set_lowerleft(self, value):
        """ guess :) """
        self[0], self[1] = [self.ensure_is_number(x) for x in value]

    def set_lowerright(self, value):
        """ guess :) """
        self[2], self[1] = [self.ensure_is_number(x) for x in value]

    def set_upperleft(self, value):
        """ guess :) """
        self[0], self[3] = [self.ensure_is_number(x) for x in value]

    def set_upperright(self, value):
        """ guess :) """
        self[2], self[3] = [self.ensure_is_number(x) for x in value]

    def get_width(self):
        """ guess :) """
        return self.get_upperright_x() - self.get_lowerleft_x()

    def get_height(self):
        """ guess :) """
        return self.get_upperright_y() - self.get_lowerleft_y()

    lower_left = property(get_lowerleft, set_lowerleft)
    """
    Property to read and modify the lower left coordinate of this box in (x,y) form.
    """

    lower_right = property(get_lowerright, set_lowerright)
    """
    Property to read and modify the lower right coordinate of this box in (x,y) form.
    """

    upper_left = property(get_upperleft, set_upperleft)
    """
    Property to read and modify the upper left coordinate of this box in (x,y) form.
    """

    upper_right = property(get_upperright, set_upperright)
    """
    Property to read and modify the upper right coordinate of this box in (x,y) form.
    """


def get_rectangle(self, name, defaults):
    """ TODO : documentation """
    retval = self.get(name)

    if isinstance(retval, RectangleObject):
        return retval
    if retval is None:
        for d__ in defaults:
            retval = self.get(d__)
            if retval is not None:
                break
    if isinstance(retval, IndirectObject):
        retval = self.pdf.getObject(retval)

    retval = RectangleObject(retval)
    set_rectangle(self, name, retval)

    return retval


def set_rectangle(self, name, value):
    """ TODO : documentation """
    if not isinstance(name, NameObject):
        name = NameObject(name)
    self[name] = value


def delete_rectangle(self, name):
    """ TODO : documentation """
    del self[name]


def _create_rectangle_accessor(name, fallback):
    return property(
        lambda self: get_rectangle(self, name, fallback),
        lambda self, value: set_rectangle(self, name, value),
        lambda self: delete_rectangle(self, name),
    )


class PageObject(DictionaryObject):
    """
    This class represents a single page within a PDF file.  Typically this
    object will be created by accessing the
    :meth:`getPage()<pypdf.PdfFileReader.getPage>` method of the
    :class:`PdfFileReader<pypdf.PdfFileReader>` class, but it is
    also possible to create an empty page with the
    :meth:`creator_blank_page()<PageObject.creator_blank_page>` static method.

    """

    def __init__(self, pdf=None, indirectRef=None):
        """
        :param pdf: PDF file the page belongs to.
        :param indirectRef: Stores the original indirect reference to
            this object in its source PDF
        """
        DictionaryObject.__init__(self)
        self.pdf = pdf
        self.indirectRef = indirectRef                          #pylint: too hudge change for the moment disable=invalid-name

    def clone(self, pdf_dest):  #PPzz
        """ clone object into pdf_dest """
        d__ = self.__class__(pdf=pdf_dest, indirectRef=None)
        d__._clone(self, pdf_dest, ("/Parent",))                          #pylint: disable=protected-access
        return d__

    @staticmethod
    def creator_blank_page(pdf=None, width=None, height=None):     #pylint: too hudge change for the moment disable=invalid-name
        """
        Returns a new blank page.
        If ``width`` or ``height`` is ``None``, try to get the page size from
        the last page of *pdf*.

        :param pdf: PDF file the page belongs to
        :param float width: The width of the new page expressed in default user
            space units.
        :param float height: The height of the new page expressed in default
            user space units.
        :return: the new blank page:
        :rtype: :class:`PageObject<PageObject>`
        :raises PageSizeNotDefinedError: if ``pdf`` is ``None`` or contains
            no page
        """
        page = PageObject(pdf)

        # Creates a new page (cnf. PDF Reference 7.7.3.3)
        page.__setitem__(NameObject("/Type"), NameObject("/Page"))
        page.__setitem__(NameObject("/Parent"), NullObject())
        page.__setitem__(NameObject("/Resources"), DictionaryObject())

        if width is None or height is None:
            if pdf is not None and pdf.numPages > 0:
                lastpage = pdf.getPage(pdf.numPages - 1)
                width = lastpage.mediaBox.get_width()
                height = lastpage.mediaBox.getHeight()
            else:
                raise PageSizeNotDefinedError()
        page.__setitem__(
            NameObject("/MediaBox"), RectangleObject([0, 0, width, height])
        )

        return page
    createBlankPage = creator_blank_page

    def rotate_clockwise(self, angle):                       #pylint: too hudge change for the moment disable=invalid-name
        """
        Rotates a page clockwise by increments of 90 degrees.

        :param int angle: Angle to rotate the page.  Must be an increment of 90
            deg.
        """
        assert angle % 90 == 0
        self._rotate(angle)
        return self
    rotateClockwise = rotate_clockwise

    def rotate_counter_clockwise(self, angle):                #pylint: too hudge change for the moment disable=invalid-name
        """
        Rotates a page counter-clockwise by increments of 90 degrees.

        :param int angle: Angle to rotate the page.  Must be an increment
            of 90 deg.
        """
        assert angle % 90 == 0
        self._rotate(-angle)
        return self
    rotateCounterClockwise = rotate_counter_clockwise

    def _rotate(self, angle):
        rotate_obj = self.get("/Rotate", 0)
        current_angle = (
            rotate_obj if isinstance(rotate_obj, int) else rotate_obj.getObject()
        )
        self[NameObject("/Rotate")] = NumberObject(current_angle + angle)

    @staticmethod
    def _merge_resources(res1, res2, resource):
        """
        TODO : documentation
        """
        new_res = DictionaryObject()
        new_res.update(res1.get(resource, DictionaryObject()).getObject())
        page2_res = res2.get(resource, DictionaryObject()).getObject()
        rename_res = {}

        for key in list(page2_res.keys()):
            if key in new_res and new_res.rawGet(key) != page2_res.rawGet(key):
                newname = NameObject(key + str(uuid.uuid4()))
                rename_res[key] = newname
                new_res[newname] = page2_res[key]
            elif key not in new_res:
                new_res[key] = page2_res.rawGet(key)

        return new_res, rename_res

    @staticmethod
    def _content_stream_rename(stream, rename, pdf):
        if not rename:
            return stream

        stream = ContentStream(stream, pdf)

        for operands, _ in stream.operations:
            for i__, op_ in enumerate(operands):
                if isinstance(op_, NameObject):
                    operands[i__] = rename.get(op_, op_)

        return stream

    @staticmethod
    def _pushpop_gs(contents, pdf):
        # Adds a graphics state "push" and "pop" to the beginning and end of a
        # content stream.  This isolates it from changes such as transformation
        # matrices.
        stream = ContentStream(contents, pdf)
        stream.operations.insert(0, [[], "q"])
        stream.operations.append([[], "Q"])

        return stream

    @staticmethod
    def _add_transformation_matrix(contents, pdf, ctm):
        # Adds transformation matrix at the beginning of the given contents
        # stream.
        a__, b__, c__, d__, e__, f__ = ctm
        contents = ContentStream(contents, pdf)
        contents.operations.insert(
            0,
            [
                [
                    FloatObject(a__),
                    FloatObject(b__),
                    FloatObject(c__),
                    FloatObject(d__),
                    FloatObject(e__),
                    FloatObject(f__),
                ],
                " cm",
            ],
        )

        return contents

    def get_contents(self):
        """
        Accesses the page contents.

        :return: the ``/Contents`` object, or ``None`` if it doesn't exist.
            ``/Contents`` is optional, as described in PDF Reference  7.7.3.3
        """
        if "/Contents" in self:
            return self["/Contents"].getObject()
        return None
    getContents = get_contents

    def merge_page(self, page2):
        """
        Merges the content streams of two pages into one.  Resource references
        (i.e. fonts) are maintained from both pages.  The mediabox/cropbox/etc
        of this page are not altered.  The parameter page's content stream will
        be added to the end of this page's content stream, meaning that it will
        be drawn after, or "on top" of this page.

        :param PageObject page2: The page to be merged into this one. Should be
            an instance of :class:`PageObject<PageObject>`.
        """
        self._merge_page(page2)
    mergePage = merge_page

    def _merge_page(self, page2, page2transformation=None, ctm=None, expand=False):
        #pylint:  already validated function disable=too-many-locals
        # First we work on merging the resource dictionaries.  This allows us
        # to find out what symbols in the content streams we might need to
        # rename.
        new_resources = DictionaryObject()
        rename = {}
        original_resources = self["/Resources"].getObject()
        page2_resources = page2["/Resources"].getObject()
        new_annots = ArrayObject()

        for page in (self, page2):
            if "/Annots" in page:
                annots = page["/Annots"]
                if isinstance(annots, ArrayObject):
                    for ref in annots:
                        new_annots.append(ref)

        for res in ("/ExtGState", "/Font", "/XObject", "/ColorSpace", "/Pattern", "/Shading",
                    "/Properties"):
            new, newrename = PageObject._merge_resources(
                original_resources, page2_resources, res
            )
            if new:
                new_resources[NameObject(res)] = new
                rename.update(newrename)

        # Combine /ProcSet sets.
        new_resources[NameObject("/ProcSet")] = ArrayObject(
            frozenset(
                original_resources.get("/ProcSet", ArrayObject()).getObject()
            ).union(
                frozenset(page2_resources.get("/ProcSet", ArrayObject()).getObject())
            )
        )

        new_content_array = ArrayObject()

        original_content = self.get_contents()

        if original_content is not None:
            new_content_array.append(PageObject._pushpop_gs(original_content, self.pdf))

        page2_content = page2.get_contents()

        if page2_content is not None:
            if page2transformation is not None:
                page2_content = page2transformation(page2_content)
            page2_content = PageObject._content_stream_rename(
                page2_content, rename, self.pdf
            )
            page2_content = PageObject._pushpop_gs(page2_content, self.pdf)
            new_content_array.append(page2_content)

        # If expanding the page to fit a new page, calculate the new media box
        # size
        if expand:
            corners1 = [
                self.mediaBox.get_lowerleft_x().as_numeric(),
                self.mediaBox.get_lowerleft_y().as_numeric(),
                self.mediaBox.get_upperright_x().as_numeric(),
                self.mediaBox.get_upperright_y().as_numeric(),
            ]
            corners2 = [
                page2.mediaBox.get_lowerleft_x().as_numeric(),
                page2.mediaBox.get_lowerleft_y().as_numeric(),
                page2.mediaBox.get_upperleft_x().as_numeric(),
                page2.mediaBox.get_upperleft_y().as_numeric(),
                page2.mediaBox.get_upperright_x().as_numeric(),
                page2.mediaBox.get_upperright_y().as_numeric(),
                page2.mediaBox.get_lowerright_x().as_numeric(),
                page2.mediaBox.get_lowerright_y().as_numeric(),
            ]
            if ctm is not None:
                ctm = [float(x) for x in ctm]
                new_x = [
                    ctm[0] * corners2[i] + ctm[2] * corners2[i + 1] + ctm[4]
                    for i in range(0, 8, 2)
                ]
                new_y = [
                    ctm[1] * corners2[i] + ctm[3] * corners2[i + 1] + ctm[5]
                    for i in range(0, 8, 2)
                ]
            else:
                new_x = corners2[0:8:2]
                new_y = corners2[1:8:2]

            lowerleft = [min(new_x), min(new_y)]
            upperright = [max(new_x), max(new_y)]
            lowerleft = [min(corners1[0], lowerleft[0]), min(corners1[1], lowerleft[1])]
            upperright = [
                max(corners1[2], upperright[0]),
                max(corners1[3], upperright[1]),
            ]

            self.mediaBox.set_lowerleft(lowerleft)
            self.mediaBox.set_upperright(upperright)

        self[NameObject("/Contents")] = ContentStream(new_content_array, self.pdf)
        self[NameObject("/Resources")] = new_resources
        self[NameObject("/Annots")] = new_annots

    def merge_transformed_page(self, page2, ctm, expand=False):
        """
        This is similar to mergePage, but a transformation matrix is
        applied to the merged stream.

        :param PageObject page2: The page to be merged into this one. Should be
            an instance of :class:`PageObject<PageObject>`.
        :param tuple ctm: a 6-element tuple containing the operands of the
            transformation matrix
        :param bool expand: Whether the page should be expanded to fit the
            dimensions of the page to be merged.
        """
        self._merge_page(
            page2,
            lambda page2_content: PageObject._add_transformation_matrix(
                page2_content, page2.pdf, ctm
            ),
            ctm,
            expand,
        )
    mergeTransformedPage = merge_transformed_page

    def merge_scaled_page(self, page2, scale, expand=False):
        """
        This is similar to mergePage, but the stream to be merged is scaled
        by appling a transformation matrix.

        :param PageObject page2: The page to be merged into this one. Should be
            an instance of :class:`PageObject<PageObject>`.
        :param float scale: The scaling factor
        :param bool expand: Whether the page should be expanded to fit the
            dimensions of the page to be merged.
        """
        # CTM to scale : [ sx 0 0 sy 0 0 ]
        return self.merge_transformed_page(page2, (scale, 0, 0, scale, 0, 0), expand)
    mergeScaledPage = merge_scaled_page

    def merge_rotated_page(self, page2, rotation, expand=False):
        """
        This is similar to mergePage, but the stream to be merged is rotated
        by appling a transformation matrix.

        :param PageObject page2: the page to be merged into this one. Should be
            an instance of :class:`PageObject<PageObject>`.
        :param float rotation: The angle of the rotation, in degrees
        :param bool expand: Whether the page should be expanded to fit the
            dimensions of the page to be merged.
        """
        rotation = math.radians(rotation)

        return self.merge_transformed_page(
            page2,
            (
                math.cos(rotation),
                math.sin(rotation),
                -math.sin(rotation),
                math.cos(rotation),
                0,
                0,
            ),
            expand,
        )
    mergeRotatedPage = merge_rotated_page

    def merge_translated_page(self, page2, tx_, ty_, expand=False):
        """
        This is similar to ``mergePage``, but the stream to be merged is
        translated by appling a transformation matrix.

        :param PageObject page2: the page to be merged into this one. Should be
            an instance of :class:`PageObject<PageObject>`.
        :param float tx_: The translation on X axis.
        :param float ty_: The translation on Y axis.
        :param bool expand: Whether the page should be expanded to fit the
            dimensions of the page to be merged.
        """
        return self.merge_transformed_page(page2, (1, 0, 0, 1, tx_, ty_), expand)
    mergeTranslatedPage = merge_translated_page

    def merge_rotated_translated_page(self, page2, rotation, tx_, ty_, expand=False):           #pylint: defined API disable=too-many-arguments
        """
        This is similar to mergePage, but the stream to be merged is rotated
        and translated by appling a transformation matrix.

        :param PageObject page2: the page to be merged into this one. Should be
            an instance of :class:`PageObject<PageObject>`.
        :param float tx_: The translation on X axis.
        :param float ty_: The translation on Y axis.
        :param float rotation: The angle of the rotation, in degrees.
        :param bool expand: Whether the page should be expanded to fit the
            dimensions of the page to be merged.
        """

        translation = [[1, 0, 0], [0, 1, 0], [-tx_, -ty_, 1]]
        rotation = math.radians(rotation)
        rotating = [
            [math.cos(rotation), math.sin(rotation), 0],
            [-math.sin(rotation), math.cos(rotation), 0],
            [0, 0, 1],
        ]
        rtranslation = [[1, 0, 0], [0, 1, 0], [tx_, ty_, 1]]
        ctm = matrixMultiply(translation, rotating)
        ctm = matrixMultiply(ctm, rtranslation)

        return self.merge_transformed_page(
            page2,
            (ctm[0][0], ctm[0][1], ctm[1][0], ctm[1][1], ctm[2][0], ctm[2][1]),
            expand,
        )
    mergeRotatedTranslatedPage = merge_rotated_translated_page

    def merge_rotated_scaled_page(self, page2, rotation, scale, expand=False):
        """
        This is similar to mergePage, but the stream to be merged is rotated
        and scaled by appling a transformation matrix.

        :param PageObject page2: the page to be merged into this one. Should be
            an instance of :class:`PageObject<PageObject>`.
        :param float rotation: The angle of the rotation, in degrees.
        :param float scale: The scaling factor.
        :param bool expand: Whether the page should be expanded to fit the
            dimensions of the page to be merged.
        """
        rotation = math.radians(rotation)
        rotating = [
            [math.cos(rotation), math.sin(rotation), 0],
            [-math.sin(rotation), math.cos(rotation), 0],
            [0, 0, 1],
        ]
        scaling = [[scale, 0, 0], [0, scale, 0], [0, 0, 1]]
        ctm = matrixMultiply(rotating, scaling)

        return self.merge_transformed_page(
            page2,
            (ctm[0][0], ctm[0][1], ctm[1][0], ctm[1][1], ctm[2][0], ctm[2][1]),
            expand,
        )
    mergeRotatedScaledPage = merge_rotated_scaled_page

    def merge_scaled_translated_page(self, page2, scale, tx_, ty_, expand=False):           #pylint: defined API disable=too-many-arguments
        """
        This is similar to mergePage, but the stream to be merged is translated
        and scaled by appling a transformation matrix.

        :param PageObject page2: the page to be merged into this one. Should be
            an instance of :class:`PageObject<PageObject>`.
        :param float scale: The scaling factor.
        :param float tx_: The translation on X axis.
        :param float ty_: The translation on Y axis.
        :param bool expand: Whether the page should be expanded to fit the
            dimensions of the page to be merged.
        """

        translation = [[1, 0, 0], [0, 1, 0], [tx_, ty_, 1]]
        scaling = [[scale, 0, 0], [0, scale, 0], [0, 0, 1]]
        ctm = matrixMultiply(scaling, translation)

        return self.merge_transformed_page(
            page2,
            (ctm[0][0], ctm[0][1], ctm[1][0], ctm[1][1], ctm[2][0], ctm[2][1]),
            expand,
        )
    mergeScaledTranslatedPage = merge_scaled_translated_page

    def merge_rotated_scaled_translated_page(               #pylint: defined API disable=too-many-arguments
            self, page2, rotation, scale, tx_, ty_, expand=False
    ):
        """
        This is similar to mergePage, but the stream to be merged is
        translated, rotated and scaled by appling a transformation matrix.

        :param PageObject page2: the page to be merged into this one. Should be
            an instance of :class:`PageObject<PageObject>`.
        :param float tx_: The translation on X axis.
        :param float ty_: The translation on Y axis.
        :param float rotation: The angle of the rotation, in degrees.
        :param float scale: The scaling factor.
        :param bool expand: Whether the page should be expanded to fit the
            dimensions of the page to be merged.
        """
        translation = [[1, 0, 0], [0, 1, 0], [tx_, ty_, 1]]
        rotation = math.radians(rotation)
        rotating = [
            [math.cos(rotation), math.sin(rotation), 0],
            [-math.sin(rotation), math.cos(rotation), 0],
            [0, 0, 1],
        ]
        scaling = [[scale, 0, 0], [0, scale, 0], [0, 0, 1]]
        ctm = matrixMultiply(rotating, scaling)
        ctm = matrixMultiply(ctm, translation)

        return self.merge_transformed_page(
            page2,
            (ctm[0][0], ctm[0][1], ctm[1][0], ctm[1][1], ctm[2][0], ctm[2][1]),
            expand,
        )
    mergeRotatedScaledTranslatedPage = merge_rotated_scaled_translated_page

    def add_transformation(self, ctm):
        """
        Applies a transformation matrix to the page.

        :param tuple ctm: A 6-element tuple containing the operands of the
            transformation matrix.
        """
        original_content = self.get_contents()

        if original_content is not None:
            new_content = PageObject._add_transformation_matrix(
                original_content, self.pdf, ctm
            )
            new_content = PageObject._pushpop_gs(new_content, self.pdf)
            self[NameObject("/Contents")] = new_content
    addTransformation = add_transformation

    def scale(self, sx_, sy_):
        """
        Scales a page by the given factors by appling a transformation
        matrix to its content and updating the page size.

        :param float sx_: The scaling factor on horizontal axis.
        :param float sy_: The scaling factor on vertical axis.
        """
        self.add_transformation((sx_, 0, 0, sy_, 0, 0))
        self.mediaBox = RectangleObject(                            #pylint: defined API disable=invalid-name
            [
                float(self.mediaBox.get_lowerleft_x()) * sx_,
                float(self.mediaBox.get_lowerleft_y()) * sy_,
                float(self.mediaBox.get_upperright_x()) * sx_,
                float(self.mediaBox.get_upperright_y()) * sy_,
            ]
        )

        if "/VP" in self:
            viewport = self["/VP"]

            if isinstance(viewport, ArrayObject):
                bbox = viewport[0]["/BBox"]
            else:
                bbox = viewport["/BBox"]

            scaled_bbox = RectangleObject(
                [
                    float(bbox[0]) * sx_,
                    float(bbox[1]) * sy_,
                    float(bbox[2]) * sx_,
                    float(bbox[3]) * sy_,
                ]
            )

            if isinstance(viewport, ArrayObject):
                self[NameObject("/VP")][NumberObject(0)][
                    NameObject("/BBox")
                ] = scaled_bbox
            else:
                self[NameObject("/VP")][NameObject("/BBox")] = scaled_bbox

    def scale_by(self, factor):
        """
        Scales a page by the given factor by appling a transformation
        matrix to its content and updating the page size.

        :param float factor: The scaling factor (for both X and Y axis).
        """
        self.scale(factor, factor)
    scaleBy = scale_by

    def scale_to(self, width, height):
        """
        Scales a page to the specified dimentions by appling a
        transformation matrix to its content and updating the page size.

        :param float width: The new width.
        :param float height: The new heigth.
        """
        sx_ = width / float(
            self.mediaBox.get_upperright_x() - self.mediaBox.get_lowerleft_x()
        )
        sy_ = height / float(
            self.mediaBox.get_upperright_y() - self.mediaBox.get_lowerleft_y()
        )
        self.scale(sx_, sy_)
    scaleTo = scale_to

    def compress_content_streams(self):
        """
        Compresses the size of this page by joining all content streams and
        applying a FlateDecode filter.

        However, it is possible that this function will perform no action if
        content stream compression becomes "automatic" for some reason.
        """
        content = self.get_contents()

        if content is not None:
            if not isinstance(content, ContentStream):
                content = ContentStream(content, self.pdf)
            self[NameObject("/Contents")] = content.flate_encode()
    compressContentStreams = compress_content_streams

    def extract_text(self):
        """
        Locate all text drawing commands, in the order they are provided in the
        content stream, and extract the text.  This works well for some PDF
        files, but poorly for others, depending on the generator used.  This
        will be refined in the future.  Do not rely on the order of text coming
        out of this function, as it will change if this function is made more
        sophisticated.

        :return: a unicode string object.
        """
        text = pypdfUnicode("")
        content = self["/Contents"].getObject()

        if not isinstance(content, ContentStream):
            content = ContentStream(content, self.pdf)

        # Note: we check all strings are TextStringObjects.  ByteStringObjects
        # are strings where the byte->string encoding was unknown, so adding
        # them to the text here would be gibberish.
        for operands, operator in content.operations:
            if operator == by_("Tj"):
                _text = operands[0]

                if isinstance(_text, TextStringObject):
                    text += _text
                    text += "\n"
            elif operator == by_("T*"):
                text += "\n"
            elif operator == by_("'"):
                text += "\n"
                _text = operands[0]
                if isinstance(_text, TextStringObject):
                    text += operands[0]
            elif operator == by_('"'):
                _text = operands[2]
                if isinstance(_text, TextStringObject):
                    text += "\n"
                    text += _text
            elif operator == by_("TJ"):
                for i__ in operands[0]:
                    if isinstance(i__, TextStringObject):
                        text += i__
                text += "\n"

        return text
    extractText = extract_text


    media_box = _create_rectangle_accessor("/MediaBox", ())
    """
    A :class:`RectangleObject<pypdf.generic.RectangleObject>`, expressed in
    default user space units, defining the boundaries of the physical medium on
    which the page is intended to be displayed or printed.
    """

    crop_box = _create_rectangle_accessor("/CropBox", ("/MediaBox",))
    """
    A :class:`RectangleObject<pypdf.generic.RectangleObject>`, expressed in
    default user space units, defining the visible region of default user
    space.  When the page is displayed or printed, its contents are to be
    clipped (cropped) to this rectangle and then imposed on the output medium
    in some implementation-defined manner.  Default value: same as
    :attr:`mediaBox<mediaBox>`.
    """

    bleed_box = _create_rectangle_accessor("/BleedBox", ("/CropBox", "/MediaBox"))
    """
    A :class:`RectangleObject<pypdf.generic.RectangleObject>`, expressed in
    default user space units, defining the region to which the contents of the
    page should be clipped when output in a production enviroment.
    """

    trim_box = _create_rectangle_accessor("/TrimBox", ("/CropBox", "/MediaBox"))
    """
    A :class:`RectangleObject<pypdf.generic.RectangleObject>`, expressed in
    default user space units, defining the intended dimensions of the finished
    page after trimming.
    """

    art_box = _create_rectangle_accessor("/ArtBox", ("/CropBox", "/MediaBox"))
    """
    A :class:`RectangleObject<pypdf.generic.RectangleObject>`, expressed in
    default user space units, defining the extent of the page's meaningful
    content as intended by the page's creator.
    """


class Field(TreeObject):
    """
    A class representing a field dictionary. This class is accessed through
    :meth:`getFields()<pypdf.PdfFileReader.getFields>`
    """

    def __init__(self, data):
        TreeObject.__init__(self)
        attributes = ("/FT", "/Parent", "/Kids", "/T", "/TU",
                      "/TM", "/Ff", "/V", "/DV", "/AA",
                     )
        for attr in attributes:
            try:
                self[NameObject(attr)] = data[attr]
            except KeyError:
                pass

    fieldType = property(lambda self: self.get("/FT"))
    """
    Read-only property accessing the type of this field.
    """

    parent = property(lambda self: self.get("/Parent"))
    """
    Read-only property accessing the parent of this field.
    """

    kids = property(lambda self: self.get("/Kids"))
    """
    Read-only property accessing the kids of this field.
    """

    name = property(lambda self: self.get("/T"))
    """
    Read-only property accessing the name of this field.
    """

    altName = property(lambda self: self.get("/TU"))
    """
    Read-only property accessing the alternate name of this field.
    """

    mappingName = property(lambda self: self.get("/TM"))
    """
    Read-only property accessing the mapping name of this field. This
    name is used by PyPDF as a key in the dictionary returned by
    :meth:`getFields<pypdf.PdfFileReader.getFields>`.
    """

    flags = property(lambda self: self.get("/Ff"))
    """
    Read-only property accessing the field flags, specifying various
    characteristics of the field (see Table 8.70 of the PDF 1.7 reference).
    """

    value = property(lambda self: self.get("/V"))
    """
    Read-only property accessing the value of this field. Format
    varies based on field type.
    """

    defaultValue = property(lambda self: self.get("/DV"))
    """
    Read-only property accessing the default value of this field.
    """

    additionalActions = property(lambda self: self.get("/AA"))
    """
    Read-only property accessing the additional actions dictionary.
    This dictionary defines the field's behavior in response to trigger events.
    See Section 8.5.2 of the PDF 1.7 reference.
    """


class Destination(TreeObject):
    """
    A class representing a destination within a PDF file.
    See section 8.2.1 of the PDF 1.6 reference.
    """

    def __init__(self, title, page_or_dest_or_array, typ="/Fit", zargs=()):
        """
        :param str title: Title of this destination.
        :param page_or_dest_or_array:
            (PageObject )Page of this destination
            or
            (Destination) destination
            or
            (DictionaryObject) dictionary
            or
            (Array) Array generated by get_dest_array
        :param str flag: Flag (Italic/Bold).
        :param str typ: How the destination is displayed.
        :param zargs: Additional arguments may be necessary depending on the type.
        :raises PdfReadError: If destination type is invalid.

        Valid ``typ`` arguments (see PDF spec for details):
                 /Fit       No additional arguments
                 /XYZ       [left] [top] [zoomFactor]
                 /FitH      [top]
                 /FitV      [left]
                 /FitR      [left] [bottom] [right] [top]
                 /FitB      No additional arguments
                 /FitBH     [top]
                 /FitBV     [left]
        """
        def build_typ_zargs(typ, zargs):
            self[NameObject("/Type")] = NameObject(typ)
            if typ == "/XYZ":
                (self[NameObject("/Left")], self[NameObject("/Top")],
                 self[NameObject("/Zoom")],) = zargs
            elif typ == "/FitR":
                (self[NameObject("/Left")], self[NameObject("/Bottom")],
                 self[NameObject("/Right")], self[NameObject("/Top")],) = zargs
            elif typ in ["/FitH", "/FitBH"]:
                (self[NameObject("/Top")],) = zargs
            elif typ in ["/FitV", "/FitBV"]:
                (self[NameObject("/Left")],) = zargs
            elif typ in ["/Fit", "/FitB"]:
                pass
            else:
                raise PdfReadError("Unknown Destination Type: %r" % typ)

        TreeObject.__init__(self)
        if isinstance(page_or_dest_or_array, Destination):
            page_or_dest_or_array = page_or_dest_or_array.get_dest_array()
        if isinstance(page_or_dest_or_array, DictionaryObject):
            pdf = page_or_dest_or_array.rawGet("/Parent").pdf
            if "/A" in page_or_dest_or_array:
                page_or_dest_or_array = page_or_dest_or_array["/A"]
            elif "/Dest" in page_or_dest_or_array:
                page_or_dest_or_array = page_or_dest_or_array["/Dest"]
            if "/D" in page_or_dest_or_array:
                page_or_dest_or_array = page_or_dest_or_array["/D"]
            if is_string(page_or_dest_or_array):
                page_or_dest_or_array = \
                        pdf.get_named_destinations()[page_or_dest_or_array].get_dest_array()
            if "/D" in page_or_dest_or_array:
                page_or_dest_or_array = page_or_dest_or_array["/D"]
        if isinstance(page_or_dest_or_array, ArrayObject):
            page, typ, *zargs = page_or_dest_or_array
        else:
            page = page_or_dest_or_array

        self[NameObject("/Title")] = create_string_object(title)
        self[NameObject("/Page")] = page


        # from table 8.2 of the PDF 1.7 reference.
        build_typ_zargs(typ, zargs)

    def clone(self, pdf_dest):  #PPzz
        """ clone object into pdf_dest """
        #we start getting the page: an error will be raised if not get it
        try:
            p__ = pdf_dest.get_indirect_object(pdf_dest._id_translated[self.rawGet('/Page').idnum])         #pylint: acceptable disable=protected-access
        except:                                                                                             #pylint: disable=bare-except
            raise Exception("destination page not found in destination document", self)

        # juste to create the object: data will be filled through _clone
        ar_ = self.get_dest_array()
        d__ = self.__class__(self.title, p__, ar_[1], ar_[2:])
        #d__._clone(self, pdf_dest, ("/Parent", "/Page"))                                                    #pylint: disable=protected-access
        #d__["/Page"] = p__
        #try:
        #    d__["/Parent"] = pdf_dest.get_indirect_object(
        #        pdf_dest._id_translated[self.rawGet('/Parent').idnum])                                      #pylint: acceptable disable=protected-access
        #except:                                                                                             #pylint: disable=bare-except
        #    warnings.warn("Outline Parent not found, set to default", d__)
        #    d__["/Parent"] = pdf_dest.get_outlines_root()
        return d__

    def get_dest_array(self):
        """ TODO : documentation """
        return ArrayObject(
            [x for x in (self.page, self.typ, self.left, self.bottom,
                         self.right, self.top, self.zoom) if x is not None])
#            [self.rawGet("/Page"), self["/Type"]]
#            + [
#                self[x]
#                for x in ["/Left", "/Bottom", "/Right", "/Top", "/Zoom"]
#                if x in self
#            ]
#        )

    def write_to_stream(self, stream, encryption_key):
        """ write to stream/file """
        stream.write(by_("<<\n"))
        key = NameObject("/D")
        key.writeToStream(stream, encryption_key)
        stream.write(by_(" "))
        value = self.getDestArray()
        value.writeToStream(stream, encryption_key)

        key = NameObject("/S")
        key.writeToStream(stream, encryption_key)
        stream.write(by_(" "))
        value = NameObject("/GoTo")
        value.writeToStream(stream, encryption_key)

        stream.write(by_("\n"))
        stream.write(by_(">>"))

    #Add the aliases that are respecting the snake not compliant api
    getDestArray = get_dest_array
    writeToStream = write_to_stream

    title = property(lambda self: self.get("/Title"))
    """
    Read-only property accessing the destination title.
    :rtype: ``str``
    """

    parent = property(lambda self: self.get("/Parent"))
    """
    Read-only property accessing the destination page number.
    :rtype: ``int``
    """
    page = property(lambda self: self.get("/Page"))
    """
    Read-only property accessing the destination page number.
    :rtype: ``int``
    """

    pageref = property(lambda self: self.rawGet("/Page"))
    """
    Read-only property accessing the destination page indirectObject.
    :rtype: ``int``
    """

    typ = property(lambda self: self.get("/Type"))
    """
    Read-only property accessing the destination type.
    :rtype: ``str``
    """

    zoom = property(lambda self: self.get("/Zoom", None))
    """
    Read-only property accessing the zoom factor.
    :rtype: ``int``, or ``None`` if not available.
    """

    left = property(lambda self: self.get("/Left", None))
    """
    Read-only property accessing the left horizontal coordinate.
    :rtype: ``int``, or ``None`` if not available.
    """

    right = property(lambda self: self.get("/Right", None))
    """
    Read-only property accessing the right horizontal coordinate.
    :rtype: ``int``, or ``None`` if not available.
    """

    top = property(lambda self: self.get("/Top", None))
    """
    Read-only property accessing the top vertical coordinate.
    :rtype: ``int``, or ``None`` if not available.
    """

    bottom = property(lambda self: self.get("/Bottom", None))
    """
    Read-only property accessing the bottom vertical coordinate.
    :rtype: ``int``, or ``None`` if not available.
    """

class PageLabel():
    """
    Page Label Object ; this is not a proper Pdf Object but an internal representation
    """
    def __init__(self, pn=0, defObject=None):
        """
        :param
        integer pn: 1st Page of the group
        defObject: tuple (1stPage,prefix,increment) or DictionnaryObject from the file
        """
        if defObject is None:
            defObject = DictionaryObject()

        try:
            if not isinstance(defObject, tuple):
                self.prefix = defObject['/P']
            else:
                self.prefix = defObject[1]+""#None will induce and error
        except:                                         #pylint: disable=bare-except
            self.prefix = ''

        try:
            if not isinstance(defObject, tuple):
                self.numbering = defObject['/S']
            else:
                self.numbering = defObject[2]+""#None will induce and error
        except:                                         #pylint: disable=bare-except
            self.numbering = '/D' if self.prefix == "" else ""

        self.page_number = pn  #1st page of the range
        try:
            if not isinstance(defObject, tuple):
                self.first = int(defObject['/St']) - pn
            else:
                self.first = max(1, int(defObject[0])) - pn   #None will induce and error
        except:                                         #pylint: disable=bare-except
            self.first = 1-pn

    def __repr__(self):
        return "PageLabel Obj(@%r :%s-%s)" % (self.first, self.prefix, self.numbering)

    def build_definition(self, page_number=None):
        """
        build the DictionnaryObject to inject into the PDF
        """
        o__ = DictionaryObject()
        if self.numbering != '/D' or self.prefix != '':
            o__.update({NameObject("/S"):NameObject(self.numbering)})
        if self.prefix != '':
            o__.update({NameObject("/P"):NameObject(self.prefix)})
        if page_number is None:
            o__.update({NameObject("/St"):NumberObject(self.first+self.page_number)})
        elif page_number == 0:
            pass  #No start value
        else:
            o__.update({NameObject("/St"):NumberObject(page_number)})
        return o__

    def get_label(self, page_number):
        """ return the label of the page as a string
        params:
            page_number : page number starting at 0
        """
        def int_to_roman(num):
            val = [
                1000, 900, 500, 400,
                100, 90, 50, 40,
                10, 9, 5, 4,
                1
                ]
            syb = [
                "M", "CM", "D", "CD",
                "C", "XC", "L", "XL",
                "X", "IX", "V", "IV",
                "I"
                ]
            roman_num = ''
            i__ = 0
            while  num > 0:
                for _ in range(num // val[i__]):
                    roman_num += syb[i__]
                    num -= val[i__]
                i__ += 1
            return roman_num

        def int_to_alpha(num):
            t__ = ""
            while num > 0:
                num = num-1
                t__ = chr(num%26+65)+t__
                num = num//26
            return t__
        if self.numbering == '/D':
            st_ = str(page_number+self.first)
        elif self.numbering == '/R':
            st_ = int_to_roman(page_number+self.first)
        elif self.numbering == '/r':
            st_ = int_to_roman(page_number+self.first).lower()
        elif self.numbering == '/A':
            st_ = int_to_alpha(page_number+self.first)
        elif self.numbering == '/a':
            st_ = int_to_alpha(page_number+self.first).lower()
        else:
            st_ = ''
        return self.prefix + st_
    getLabel = get_label


class Bookmark(TreeObject):
    """
    Bookmarks object
    """
    def __init__(self, title, page_or_dest_or_array, flag=None, color=None, typ="/Fit", zargs=()):
        """
        :param str title: Title of this destination.
        :param page_or_dest_or_array:
            (PageObject )Page of this destination
            or
            (Destination) destination
            or
            (Array) Array generated by get_dest_array
        :param str flag: Flag (Italic/Bold).
        :param str typ: How the destination is displayed.
        :param zargs: Additional arguments may be necessary depending on the type.
        :raises PdfReadError: If destination type is invalid.

        Valid ``typ`` arguments (see PDF spec for details):
                 /Fit       No additional arguments
                 /XYZ       [left] [top] [zoomFactor]
                 /FitH      [top]
                 /FitV      [left]
                 /FitR      [left] [bottom] [right] [top]
                 /FitB      No additional arguments
                 /FitBH     [top]
                 /FitBV     [left]
        """
        TreeObject.__init__(self)
        if isinstance(page_or_dest_or_array, (DictionaryObject, Bookmark)):
            if title == "":
                if "/First" in page_or_dest_or_array:
                    self[NameObject("/First")] = page_or_dest_or_array.rawGet("/First")
                    self[NameObject("/Last")] = page_or_dest_or_array.rawGet("/Last")
                    self[NameObject("/Count")] = page_or_dest_or_array["/Count"]
                if "/Next" in page_or_dest_or_array:
                    self[NameObject("/Next")] = page_or_dest_or_array.rawGet("/Next")
                if "/Prev" in page_or_dest_or_array:
                    self[NameObject("/Prev")] = page_or_dest_or_array.rawGet("/Prev")
                if "/Parent" in page_or_dest_or_array:
                    self[NameObject("/Parent")] = page_or_dest_or_array.rawGet("/Parent")
            if not title  and "/Title" in page_or_dest_or_array: #title != None,"",0,False
                title = page_or_dest_or_array["/Title"]
            if flag is None and "/F" in page_or_dest_or_array:
                flag = page_or_dest_or_array["/F"]
            if flag is None and "/C" in page_or_dest_or_array:
                color = page_or_dest_or_array["/C"]
        self[NameObject("/Title")] = create_string_object(title)
        self[NameObject("/Dest")] = Destination(title, page_or_dest_or_array, typ, zargs)
        if flag is not None:
            self[NameObject("/F")] = NumberObject(flag)
        if color is not None and color is tuple:
            self[NameObject("/C")] = ArrayObject(
                [NumberObject(color[0]), NumberObject(color[1]), NumberObject(color[2])])

    def clone(self, pdf_dest):  #PPzz
        """ clone bookmark into pdf_dest """
        #note:  when a full (reader) document is cloned, it is treeObjects' clone that will be used
        # clone the object
        d__ = self.__class__(self.title, self.dest.clone(pdf_dest), self.flag, self.color)
        dref = pdf_dest._add_object(d__)
        d__[NameObject("/Count")] = NumberObject(self["/Count"])
        # clone children
        if "/First" in self:
            nprev = None
            cur_ = self.rawGet("/First")
            while True:
                ncur_ = cur_.clone(pdf_dest)
                ncur_.getObject()[NameObject("/Parent")] = dref
                d__.add_child(ncur_, pdf_dest)
                if nprev is not None:
                    nprev.getObject()[NameObject("/Next")] = ncur_
                    ncur_.getObject()[NameObject("/Prev")] = nprev
                else:
                    d__[NameObject("/First")] = ncur_
                nprev = ncur_
                if "/Next"  in cur_:
                    cur_ = cur_["/Next"]
                else:
                    break
            d__[NameObject("/Last")] = ncur_
        # the Prev/Next are left unfilled. They can be set if there is a parent that is calling

    def get_dest_array(self):
        """ TODO : documentation """
        return ArrayObject(
            [x for x in (self.page, self.typ, self.left, self.bottom,
                         self.right, self.top, self.zoom) if x is not None])

    def writeToStream(self, stream, encryption_key):
        """ write to stream/file """
        stream.write(by_("<<\n"))
        for key in [NameObject(x)
                    for x in ["/Title", "/Parent", "/First", "/Last", "/Count", "/Next", "/Prev"]
                    if x in self]:
            key.writeToStream(stream, encryption_key)
            stream.write(by_(" "))
            value = self.rawGet(key)
            value.writeToStream(stream, encryption_key)
            stream.write(by_("\n"))

        key = NameObject("/Dest")
        key.writeToStream(stream, encryption_key)
        stream.write(by_(" "))
        value = self.dest.getDestArray()
        value.writeToStream(stream, encryption_key)
        if "/F" in self:
            key = NameObject("/F")
            key.writeToStream(stream, encryption_key)
            stream.write(by_(" "))
            value = NumberObject(self["/F"])
            value.writeToStream(stream, encryption_key)
            stream.write(by_(" "))
        if "/C" in self:
            key = NameObject("/C")
            key.writeToStream(stream, encryption_key)
            stream.write(by_(" "))
            value = self["/C"]
            value.writeToStream(stream, encryption_key)
        stream.write(by_("\n"))
        stream.write(by_(">>"))

    title = property(lambda self: self.get("/Title"))
    dest = property(lambda self: self.get("/Dest"))
    parent = property(lambda self: self.get("/Parent"))
    flag = property(lambda self: self.get("/F"))
    color = property(lambda self: self.get("/C"))
    page = property(lambda self: self["/Dest"].get("/Page"))
    pageref = property(lambda self: self["/Dest"].rawGet("/Page"))
    typ = property(lambda self: self["/Dest"].get("/Type"))
    left = property(lambda self: self["/Dest"].get("/Left", None))
    bottom = property(lambda self: self["/Dest"].get("/Bottom", None))
    right = property(lambda self: self["/Dest"].get("/Right", None))
    top = property(lambda self: self["/Dest"].get("/Top", None))
    zoom = property(lambda self: self["/Dest"].get("/Zoom", None))

class PdfBaseDocument(object):                              #pylint: for Py 2.x disable=useless-object-inheritance
    """ abstract class for PdfReader/Writer """
    pass

_pdfDocEncoding = (
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u02d8"),
    pypdfUnicode("\u02c7"),
    pypdfUnicode("\u02c6"),
    pypdfUnicode("\u02d9"),
    pypdfUnicode("\u02dd"),
    pypdfUnicode("\u02db"),
    pypdfUnicode("\u02da"),
    pypdfUnicode("\u02dc"),
    pypdfUnicode("\u0020"),
    pypdfUnicode("\u0021"),
    pypdfUnicode("\u0022"),
    pypdfUnicode("\u0023"),
    pypdfUnicode("\u0024"),
    pypdfUnicode("\u0025"),
    pypdfUnicode("\u0026"),
    pypdfUnicode("\u0027"),
    pypdfUnicode("\u0028"),
    pypdfUnicode("\u0029"),
    pypdfUnicode("\u002a"),
    pypdfUnicode("\u002b"),
    pypdfUnicode("\u002c"),
    pypdfUnicode("\u002d"),
    pypdfUnicode("\u002e"),
    pypdfUnicode("\u002f"),
    pypdfUnicode("\u0030"),
    pypdfUnicode("\u0031"),
    pypdfUnicode("\u0032"),
    pypdfUnicode("\u0033"),
    pypdfUnicode("\u0034"),
    pypdfUnicode("\u0035"),
    pypdfUnicode("\u0036"),
    pypdfUnicode("\u0037"),
    pypdfUnicode("\u0038"),
    pypdfUnicode("\u0039"),
    pypdfUnicode("\u003a"),
    pypdfUnicode("\u003b"),
    pypdfUnicode("\u003c"),
    pypdfUnicode("\u003d"),
    pypdfUnicode("\u003e"),
    pypdfUnicode("\u003f"),
    pypdfUnicode("\u0040"),
    pypdfUnicode("\u0041"),
    pypdfUnicode("\u0042"),
    pypdfUnicode("\u0043"),
    pypdfUnicode("\u0044"),
    pypdfUnicode("\u0045"),
    pypdfUnicode("\u0046"),
    pypdfUnicode("\u0047"),
    pypdfUnicode("\u0048"),
    pypdfUnicode("\u0049"),
    pypdfUnicode("\u004a"),
    pypdfUnicode("\u004b"),
    pypdfUnicode("\u004c"),
    pypdfUnicode("\u004d"),
    pypdfUnicode("\u004e"),
    pypdfUnicode("\u004f"),
    pypdfUnicode("\u0050"),
    pypdfUnicode("\u0051"),
    pypdfUnicode("\u0052"),
    pypdfUnicode("\u0053"),
    pypdfUnicode("\u0054"),
    pypdfUnicode("\u0055"),
    pypdfUnicode("\u0056"),
    pypdfUnicode("\u0057"),
    pypdfUnicode("\u0058"),
    pypdfUnicode("\u0059"),
    pypdfUnicode("\u005a"),
    pypdfUnicode("\u005b"),
    pypdfUnicode("\u005c"),
    pypdfUnicode("\u005d"),
    pypdfUnicode("\u005e"),
    pypdfUnicode("\u005f"),
    pypdfUnicode("\u0060"),
    pypdfUnicode("\u0061"),
    pypdfUnicode("\u0062"),
    pypdfUnicode("\u0063"),
    pypdfUnicode("\u0064"),
    pypdfUnicode("\u0065"),
    pypdfUnicode("\u0066"),
    pypdfUnicode("\u0067"),
    pypdfUnicode("\u0068"),
    pypdfUnicode("\u0069"),
    pypdfUnicode("\u006a"),
    pypdfUnicode("\u006b"),
    pypdfUnicode("\u006c"),
    pypdfUnicode("\u006d"),
    pypdfUnicode("\u006e"),
    pypdfUnicode("\u006f"),
    pypdfUnicode("\u0070"),
    pypdfUnicode("\u0071"),
    pypdfUnicode("\u0072"),
    pypdfUnicode("\u0073"),
    pypdfUnicode("\u0074"),
    pypdfUnicode("\u0075"),
    pypdfUnicode("\u0076"),
    pypdfUnicode("\u0077"),
    pypdfUnicode("\u0078"),
    pypdfUnicode("\u0079"),
    pypdfUnicode("\u007a"),
    pypdfUnicode("\u007b"),
    pypdfUnicode("\u007c"),
    pypdfUnicode("\u007d"),
    pypdfUnicode("\u007e"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u2022"),
    pypdfUnicode("\u2020"),
    pypdfUnicode("\u2021"),
    pypdfUnicode("\u2026"),
    pypdfUnicode("\u2014"),
    pypdfUnicode("\u2013"),
    pypdfUnicode("\u0192"),
    pypdfUnicode("\u2044"),
    pypdfUnicode("\u2039"),
    pypdfUnicode("\u203a"),
    pypdfUnicode("\u2212"),
    pypdfUnicode("\u2030"),
    pypdfUnicode("\u201e"),
    pypdfUnicode("\u201c"),
    pypdfUnicode("\u201d"),
    pypdfUnicode("\u2018"),
    pypdfUnicode("\u2019"),
    pypdfUnicode("\u201a"),
    pypdfUnicode("\u2122"),
    pypdfUnicode("\ufb01"),
    pypdfUnicode("\ufb02"),
    pypdfUnicode("\u0141"),
    pypdfUnicode("\u0152"),
    pypdfUnicode("\u0160"),
    pypdfUnicode("\u0178"),
    pypdfUnicode("\u017d"),
    pypdfUnicode("\u0131"),
    pypdfUnicode("\u0142"),
    pypdfUnicode("\u0153"),
    pypdfUnicode("\u0161"),
    pypdfUnicode("\u017e"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u20ac"),
    pypdfUnicode("\u00a1"),
    pypdfUnicode("\u00a2"),
    pypdfUnicode("\u00a3"),
    pypdfUnicode("\u00a4"),
    pypdfUnicode("\u00a5"),
    pypdfUnicode("\u00a6"),
    pypdfUnicode("\u00a7"),
    pypdfUnicode("\u00a8"),
    pypdfUnicode("\u00a9"),
    pypdfUnicode("\u00aa"),
    pypdfUnicode("\u00ab"),
    pypdfUnicode("\u00ac"),
    pypdfUnicode("\u0000"),
    pypdfUnicode("\u00ae"),
    pypdfUnicode("\u00af"),
    pypdfUnicode("\u00b0"),
    pypdfUnicode("\u00b1"),
    pypdfUnicode("\u00b2"),
    pypdfUnicode("\u00b3"),
    pypdfUnicode("\u00b4"),
    pypdfUnicode("\u00b5"),
    pypdfUnicode("\u00b6"),
    pypdfUnicode("\u00b7"),
    pypdfUnicode("\u00b8"),
    pypdfUnicode("\u00b9"),
    pypdfUnicode("\u00ba"),
    pypdfUnicode("\u00bb"),
    pypdfUnicode("\u00bc"),
    pypdfUnicode("\u00bd"),
    pypdfUnicode("\u00be"),
    pypdfUnicode("\u00bf"),
    pypdfUnicode("\u00c0"),
    pypdfUnicode("\u00c1"),
    pypdfUnicode("\u00c2"),
    pypdfUnicode("\u00c3"),
    pypdfUnicode("\u00c4"),
    pypdfUnicode("\u00c5"),
    pypdfUnicode("\u00c6"),
    pypdfUnicode("\u00c7"),
    pypdfUnicode("\u00c8"),
    pypdfUnicode("\u00c9"),
    pypdfUnicode("\u00ca"),
    pypdfUnicode("\u00cb"),
    pypdfUnicode("\u00cc"),
    pypdfUnicode("\u00cd"),
    pypdfUnicode("\u00ce"),
    pypdfUnicode("\u00cf"),
    pypdfUnicode("\u00d0"),
    pypdfUnicode("\u00d1"),
    pypdfUnicode("\u00d2"),
    pypdfUnicode("\u00d3"),
    pypdfUnicode("\u00d4"),
    pypdfUnicode("\u00d5"),
    pypdfUnicode("\u00d6"),
    pypdfUnicode("\u00d7"),
    pypdfUnicode("\u00d8"),
    pypdfUnicode("\u00d9"),
    pypdfUnicode("\u00da"),
    pypdfUnicode("\u00db"),
    pypdfUnicode("\u00dc"),
    pypdfUnicode("\u00dd"),
    pypdfUnicode("\u00de"),
    pypdfUnicode("\u00df"),
    pypdfUnicode("\u00e0"),
    pypdfUnicode("\u00e1"),
    pypdfUnicode("\u00e2"),
    pypdfUnicode("\u00e3"),
    pypdfUnicode("\u00e4"),
    pypdfUnicode("\u00e5"),
    pypdfUnicode("\u00e6"),
    pypdfUnicode("\u00e7"),
    pypdfUnicode("\u00e8"),
    pypdfUnicode("\u00e9"),
    pypdfUnicode("\u00ea"),
    pypdfUnicode("\u00eb"),
    pypdfUnicode("\u00ec"),
    pypdfUnicode("\u00ed"),
    pypdfUnicode("\u00ee"),
    pypdfUnicode("\u00ef"),
    pypdfUnicode("\u00f0"),
    pypdfUnicode("\u00f1"),
    pypdfUnicode("\u00f2"),
    pypdfUnicode("\u00f3"),
    pypdfUnicode("\u00f4"),
    pypdfUnicode("\u00f5"),
    pypdfUnicode("\u00f6"),
    pypdfUnicode("\u00f7"),
    pypdfUnicode("\u00f8"),
    pypdfUnicode("\u00f9"),
    pypdfUnicode("\u00fa"),
    pypdfUnicode("\u00fb"),
    pypdfUnicode("\u00fc"),
    pypdfUnicode("\u00fd"),
    pypdfUnicode("\u00fe"),
    pypdfUnicode("\u00ff"),
)

assert len(_pdfDocEncoding) == 256

_pdfDocEncoding_rev = {}

for i in range(256):
    char = _pdfDocEncoding[i]

    if char == pypdfUnicode("\u0000"):
        continue

    assert char not in _pdfDocEncoding_rev

    _pdfDocEncoding_rev[char] = i
