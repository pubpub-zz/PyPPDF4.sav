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
Implementation of basic generic PDF objects (PdfObject, number, string, NameObject)
cut generic to prevent circular imports issues.
"""

import codecs
import decimal
import re
import warnings

from .utils import (PdfReadError, PdfReadWarning,                 #pylint: disable=relative-beyond-top-level
                    read_until_regex, StringType, BytesType,
                    pypdfUnicode, pypdfBytes as by_,
                    pypdfBytearray, RC4Encrypt, hexEncode, pypdf_str, pypdf_chr, pypdfOrd)

__author__ = "Mathieu Fenniak"
__author_email__ = "biziqe@mathieu.fenniak.net"

class PdfObject(object):                    #pylint: for Py 2.x disable=useless-object-inheritance
    """
    abstracted pdf object
    """
    def get_object(self):
        """Resolves indirect references."""
        return self

    def clone(self, pdf_dest):              #pylint: disable=unused-argument,no-self-use
        """ clone object into pdf_dest """
        raise Exception("clone PdfObject")

    getObject = get_object

# TO-DO Add __repr_() implementations to the *Object classes
class NullObject(PdfObject):
    """
    Null PDF Object
    """
    def writeToStream(self, stream, encryption_key):    #pylint: too hudge change for the moment disable=invalid-name,no-self-use,unused-argument
        """ write to stream/file """
        stream.write(by_("null"))

    def __repr__(self):
        return "Null"

    @staticmethod
    def readFromStream(stream):                         #pylint: too hudge change for the moment disable=invalid-name
        """ read from stream/file """
        null_text = stream.read(4)

        if null_text != by_("null"):
            raise PdfReadError("Could not read Null object")

        return NullObject()

    def __iter__(self):
        """ implement iterator """
        return self

    def __next__(self):
        """ implement (empty) iterator """
        raise StopIteration

    def clone(self, pdf_dest):                           #pylint: disable=unused-argument,no-self-use
        """ clone object into pdf_dest """
        return NullObject()


class BooleanObject(PdfObject):
    """
    boolean pdf object
    """
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return "bTrue" if self.value else "bFalse"

    def clone(self, pdf_dest):                           #pylint: disable=unused-argument,no-self-use
        """ clone object into pdf_dest """
        return BooleanObject(self.value)

    def writeToStream(self, stream, encryption_key):    #pylint: too hudge change for the moment disable=invalid-name,unused-argument
        """ write to stream/file """
        if self.value:
            stream.write(by_("true"))
        else:
            stream.write(by_("false"))

    @staticmethod
    def readFromStream(stream):                         #pylint: too hudge change for the moment disable=invalid-name
        """ read from stream/file """
        word = stream.read(4)

        if word == by_("true"):
            return BooleanObject(True)
        if word == by_("fals"):
            stream.read(1)
            return BooleanObject(False)
        raise PdfReadError("Could not read Boolean object")



class FloatObject(decimal.Decimal, PdfObject):
    """
    pdf float object
    """
    def __new__(cls, value="0", context=None):
        try:
            return decimal.Decimal.__new__(cls, pypdf_str(value), context)
        except:             #pylint: disable=bare-except
            return decimal.Decimal.__new__(cls, str(value))

    def clone(self, pdf_dest):  #PPzz
        """ clone object into pdf_dest """
        return FloatObject(self.as_numeric())

    def __repr__(self):
        if self == self.to_integral():
            return str(self.quantize(decimal.Decimal(1)))
        # Standard formatting adds useless extraneous zeros.
        o__ = "%.5f" % self
        # Remove the zeros.
        while o__ and o__[-1] == "0":
            o__ = o__[:-1]
        return o__

    def as_numeric(self):
        """ convert to float """
        return float(by_(repr(self)))

    def writeToStream(self, stream, encryption_key):                    #pylint: too hudge change for the moment disable=invalid-name,unused-argument
        """ write to stream/file """
        stream.write(by_(repr(self)))


class NumberObject(int, PdfObject):
    """
    pdf number object
    """
    NumberPattern = re.compile(by_("[^+-.0-9]"))
    ByteDot = by_(".")

    def __new__(cls, value):
        val = int(value)
        try:
            return int.__new__(cls, val)
        except OverflowError:
            return int.__new__(cls, 0)

    def clone(self, pdf_dest):                           #pylint: disable=unused-argument
        """ clone object into pdf_dest """
        return NumberObject(self.as_numeric())

    def as_numeric(self):
        """ return as integer(numeric) """
        return int(by_(repr(self)))

    def writeToStream(self, stream, encryption_key):                    #pylint: too hudge change for the moment disable=invalid-name,unused-argument
        """ write to stream/file """
        stream.write(by_(repr(self)))

    @staticmethod
    def readFromStream(stream):                                         #pylint: too hudge change for the moment disable=invalid-name
        """ read from stream/file """
        num = read_until_regex(stream, NumberObject.NumberPattern)

        if num.find(NumberObject.ByteDot) != -1:
            return FloatObject(num)
        return NumberObject(num)

class ByteStringObject(BytesType, PdfObject):
    """
    Represents a string object where the text encoding could not be determined.
    This occurs quite often, as the PDF spec doesn't provide an alternate way
    to represent strings -- for example, the encryption data stored in files
    (like /O) is clearly not text, but is still stored in a ``String`` object).
    """

    # For compatibility with TextStringObject.original_bytes.  This method
    # returns self.
    original_bytes = property(lambda self: self)

    def clone(self, pdf_dest):                                              #pylint: disable=unused-argument
        """ clone object into pdf_dest """
        return ByteStringObject(self)

    def writeToStream(self, stream, encryption_key):                        #pylint: too hudge change for the moment disable=invalid-name
        """ write to stream/file """
        bytearr = self

        if encryption_key:
            bytearr = RC4Encrypt(encryption_key, bytearr)

        stream.write(by_("<"))
        stream.write(by_(hexEncode(bytearr)))
        stream.write(by_(">"))

class TextStringObject(StringType, PdfObject):
    """
    Represents a ``str`` object that has been decoded into a real ``unicode``
    string. If read from a PDF document, this string appeared to match the
    PDFDocEncoding, or contained a UTF-16BE BOM mark to cause UTF-16 decoding
    to occur.
    """

    autodetect_pdfdocencoding = False
    autodetect_utf16 = False

    # It is occasionally possible that a text string object gets created where
    # a byte string object was expected due to the autodetection mechanism --
    # if that occurs, this "original_bytes" property can be used to
    # back-calculate what the original encoded bytes were.
    original_bytes = property(lambda self: self.get_original_bytes())

    def clone(self, pdf_dest):                          #pylint: disable=unused-argument
        """ clone object into pdf_dest """
        return create_string_object(self)

    def get_original_bytes(self):
        """
        We're a text string object, but the library is trying to get our raw
        bytes.  This can happen if we auto-detected this string as text, but
        we were wrong.  It's pretty common.  Return the original bytes that
        would have been used to create this object, based upon the autodetect
        method.
        """
        if self.autodetect_utf16:
            return codecs.BOM_UTF16_BE + self.encode("utf-16be")
        if self.autodetect_pdfdocencoding:
            return encode_pdf_doc_encoding(self)
        raise Exception("no information about original bytes")

    def writeToStream(self, stream, encryption_key):                    #pylint: too hudge change for the moment disable=invalid-name
        """ write to stream/file """
        try:
            """Try to write the string out as a PDFDocEncoding encoded string.  It's
            nicer to look at in the PDF file.  Sadly, we take a performance hit
            here for trying...
            """
            bytearr = encode_pdf_doc_encoding(self)
        except UnicodeEncodeError:
            bytearr = codecs.BOM_UTF16_BE + self.encode("utf-16be")

        if encryption_key:
            bytearr = RC4Encrypt(encryption_key, bytearr)
            obj = ByteStringObject(bytearr)
            obj.writeToStream(stream, None)
        else:
            stream.write(by_("("))

            for c__ in bytearr:
                if not pypdf_chr(c__).isalnum() and pypdf_chr(c__) != " ":
                    stream.write(by_("\\%03o" % pypdfOrd(c__)))
                else:
                    stream.write(by_(pypdf_chr(c__)))

            stream.write(by_(")"))

def create_string_object(string):
    """
    Given a string (either a ``str`` or ``unicode``), create a
    :class:`ByteStringObject<ByteStringObject>` or a
    :class:`TextStringObject<TextStringObject>` to represent the string.
    """
    if isinstance(string, StringType):
        return TextStringObject(string)
    if isinstance(string, BytesType):
        try:
            if string.startswith(codecs.BOM_UTF16_BE):
                retval = TextStringObject(string.decode("utf-16"))
                retval.autodetect_utf16 = True
                return retval
            # This is probably a big performance hit here, but we need to
            # convert string objects into the text/unicode-aware version if
            # possible... and the only way to check if that's possible is
            # to try.  Some strings are strings, some are just byte arrays.
            retval = TextStringObject(decode_pdf_doc_encoding(string))
            retval.autodetect_pdfdocencoding = True
            return retval
        except UnicodeDecodeError:
            return ByteStringObject(string)
    else:
        raise TypeError("create_string_object() should have str or unicode arg")

class NameObject(str, PdfObject):
    """
    pdf name object
    """
    delimiterPattern = re.compile(by_(r"\s+|[\(\)<>\[\]{}/%]"))
    surfix = by_("/")

    def clone(self, pdf_dest):  #PPzz
        """ clone object into pdf_dest """
        return NameObject(self)

    def writeToStream(self, stream, encryption_key):        #pylint: too hudge change for the moment disable=invalid-name,unused-argument
        """ write to stream/file """
        stream.write(by_(self))

    @staticmethod
    def readFromStream(stream, pdf):                        #pylint: too hudge change for the moment disable=invalid-name
        """ read from stream/file """
        debug = False

        if debug:
            print((stream.tell()))

        name = stream.read(1)

        if name != NameObject.surfix:
            raise PdfReadError("name read error")

        name += read_until_regex(stream, NameObject.delimiterPattern, ignore_eof=True)

        if debug:
            print(name)
        try:
            return NameObject(name.decode("utf-8"))
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Name objects should represent irregular characters
            # with a '#' followed by the symbol's hex number
            if not pdf.strict:
                warnings.warn("Illegal character in Name Object", PdfReadWarning)
                return NameObject(name)
            raise PdfReadError("Illegal character in Name Object")


def encode_pdf_doc_encoding(unicode_str):
    """ TODO : documentation """
    retval = by_("")

    for c__ in unicode_str:
        try:
            retval += by_(chr(_pdfDocEncoding_rev[c__]))
        except KeyError:
            raise UnicodeEncodeError(
                "pdfdocencoding", c__, -1, -1, "does not exist in translation table"
            )

    return retval

def decode_pdf_doc_encoding(byte_array):
    """ TODO : documentation """
    retval = pypdfUnicode("")

    for b__ in byte_array:
        c__ = _pdfDocEncoding[pypdfOrd(b__)]

        if c__ == pypdfUnicode("\u0000"):
            raise UnicodeDecodeError(
                "pdfdocencoding",
                pypdfBytearray(b__),
                -1,
                -1,
                "does not exist in translation table",
            )

        retval += c__

    return retval


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
