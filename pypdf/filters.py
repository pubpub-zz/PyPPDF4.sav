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
Implementation of stream filters for PDF.
"""

import math
import base64
import struct
from sys import version_info

from .utils import PdfReadError, pypdfOrd, paethPredictor, PdfStreamError, BytesIO  #pylint: disable=relative-beyond-top-level
from .generic import NameObject                                                     #pylint: disable=relative-beyond-top-level

try:
    import zlib

    def decompress(data):
        """ data decompression """
        return zlib.decompress(data)

    def compress(data):
        """ data compression """
        return zlib.compress(data)


except ImportError:
    # Unable to import zlib.  Attempt to use the System.IO.Compression
    # library from the .NET framework. (IronPython only.)
    import System
    from System import IO, Array

    def _string_to_bytearr(buf):
        retval = Array.CreateInstance(System.Byte, len(buf))

        # pylint: disable=consider-using-enumerate
        for i in range(len(buf)):
            retval[i] = ord(buf[i])

        return retval

    def _bytearr_to_string(these_bytes):
        retval = ""

        for i in range(these_bytes.Length):
            retval += chr(these_bytes[i])

        return retval

    def _read_bytes(stream):
        ms_ = IO.MemoryStream()
        buf = Array.CreateInstance(System.Byte, 2048)

        while True:
            these_bytes = stream.Read(buf, 0, buf.Length)

            if these_bytes == 0:
                break
            ms_.Write(buf, 0, these_bytes)

        retval = ms_.ToArray()
        ms_.Close()

        return retval

    def decompress(data):
        """ data decompression """
        these_bytes = _string_to_bytearr(data)
        ms_ = IO.MemoryStream()
        ms_.Write(bytes, 0, these_bytes.Length)
        ms_.Position = 0  # fseek 0
        gz_ = IO.Compression.DeflateStream(ms_, IO.Compression.CompressionMode.Decompress)
        these_bytes = _read_bytes(gz_)
        retval = _bytearr_to_string(these_bytes)
        gz_.Close()

        return retval

    def compress(data):
        """ data compression """
        these_bytes = _string_to_bytearr(data)
        ms_ = IO.MemoryStream()
        gz_ = IO.Compression.DeflateStream(
            ms_, IO.Compression.CompressionMode.Compress, True
        )
        gz_.Write(these_bytes, 0, these_bytes.Length)
        gz_.Close()
        ms_.Position = 0  # fseek 0
        these_bytes = ms_.ToArray()
        retval = _bytearr_to_string(these_bytes)
        ms_.Close()

        return retval


__author__ = "Mathieu Fenniak"
__author_email__ = "biziqe@mathieu.fenniak.net"


class FlateCodec(object):   #pylint: for Py 2.x disable=useless-object-inheritance
    """
    TODO: Documentation
    """
    @staticmethod
    def encode(data, decode_params=None):   #pylint: disable=unused-argument
        """
        data encoding
        """
        return compress(data)

    # pylint: disable=too-many-locals, too-many-branches
    @staticmethod
    def decode(data, decode_params=None):
        """
        :param data: flate-encoded data.
        :param decode_params: a dictionary of parameter values.
        :return: the flate-decoded data.
        :rtype: bytes
        """
        data = decompress(data)
        predictor = 1

        if decode_params:
            try:
                predictor = decode_params.get("/Predictor", 1)
            except AttributeError:
                pass  # Usually an array with a null object was read

        # predictor 1 == no predictor
        if predictor != 1:
            # The /Columns param. has 1 as the default value; see ISO 32000,
            # §7.4.4.3 LZWDecode and FlateDecode Parameters, Table 8
            columns = decode_params.get("/Columns", 1)

            # PNG prediction:
            if 10 <= predictor <= 15:
                output = BytesIO()
                # PNG prediction can vary from row to row
                row_length = columns + 1
                assert len(data) % row_length == 0
                prev_rowdata = (0,) * row_length

                for row in range(len(data) // row_length):
                    rowdata = [
                        pypdfOrd(x)
                        for x in data[(row * row_length) : ((row + 1) * row_length)]
                    ]
                    filter_byte = rowdata[0]

                    if filter_byte == 0:
                        pass
                    elif filter_byte == 1:
                        for i in range(2, row_length):
                            rowdata[i] = (rowdata[i] + rowdata[i - 1]) % 256
                    elif filter_byte == 2:
                        for i in range(1, row_length):
                            rowdata[i] = (rowdata[i] + prev_rowdata[i]) % 256
                    elif filter_byte == 3:
                        for i in range(1, row_length):
                            left = rowdata[i - 1] if i > 1 else 0
                            floor = math.floor(left + prev_rowdata[i]) / 2
                            rowdata[i] = (rowdata[i] + int(floor)) % 256
                    elif filter_byte == 4:
                        for i in range(1, row_length):
                            left = rowdata[i - 1] if i > 1 else 0
                            up_ = prev_rowdata[i]
                            up_left = prev_rowdata[i - 1] if i > 1 else 0
                            paeth = paethPredictor(left, up_, up_left)
                            rowdata[i] = (rowdata[i] + paeth) % 256
                    else:
                        # Unsupported PNG filter
                        raise PdfReadError("Unsupported PNG filter %r" % filter_byte)

                    prev_rowdata = rowdata

                    for d__ in rowdata[1:]: ##ppZZ ???? err in latest version
                        if version_info < (3, 0):
                            output.write(chr(d__))
                        else:
                            output.write(bytes([d__]))

                data = output.getvalue()
            else:
                # unsupported predictor
                raise PdfReadError("Unsupported flatedecode predictor %r" % predictor)

        return data


class ASCIIHexCodec(object):        #pylint: for Py 2.x disable=useless-object-inheritance
    """
        The ASCIIHexCodec filter decodes data that has been encoded in ASCII
        hexadecimal form into a base-7 ASCII format.
    """

    @staticmethod
    def encode(data, decode_params=None):
        """ encode data """
        raise NotImplementedError()

    @staticmethod
    def decode(data, decode_params=None):       #pylint: disable=unused-argument
        """
        :param data: a str sequence of hexadecimal-encoded values to be
            converted into a base-7 ASCII string
        :return: a string conversion in base-7 ASCII, where each of its values
            v is such that 0 <= ord(v) <= 127.
        """
        retval = ""
        hex_pair = ""
        eod_found = False

        for c__ in data:
            if c__ == ">":
                # If the filter encounters the EOD marker after reading an odd
                # number of hexadecimal digits, it shall behave as if a 0
                # (zero) followed the last digit - from ISO 32000 specification
                if len(hex_pair) == 1:
                    hex_pair += "0"
                    retval += chr(int(hex_pair, base=16))
                    hex_pair = ""

                eod_found = True
                break
            if c__.isspace():
                continue

            hex_pair += c__

            if len(hex_pair) == 2:
                retval += chr(int(hex_pair, base=16))
                hex_pair = ""

        if not eod_found:
            raise PdfStreamError("Ending character '>' not found in stream")

        assert hex_pair == ""

        return retval


# pylint: disable=too-few-public-methods
class LZWCodec(object):             #pylint: for Py 2.x disable=useless-object-inheritance
    """
    For a reference of the LZW algorithm consult ISO 32000, section 7.4.4 or
    Section 13 of "TIFF 6.0 Specification" for a more detailed discussion.
    """

    class Encoder(object):          #pylint: for Py 2.x disable=useless-object-inheritance
        """
        ``LZWCodec.Encoder`` is primarily employed for testing purposes and
        its implementation doesn't (yet) cover all the little facets present in
        the ISO standard.
        """

        MAX_ENTRIES = 2 ** 12

        def __init__(self, data):
            """
            :param data: a ``str`` or ``bytes`` string to encode with LZW.
            """
            if isinstance(data, str) and version_info > (3, 0):
                self.data = data.encode("UTF-8")
            elif isinstance(data, bytes):  # bytes is str in Python 2
                self.data = data
            else:
                raise TypeError(
                    "data must be of type {str, bytes}, found %s" % type(data)
                )
            self.bitspercode = None
            # self.table maps buffer values to their progressive indices
            self.table = None
            # self.result stores the contiguous stream of bits in form of ints
            self.output = None
            # The location of the next bit we are going to write to
            self.bitpos = 0

            self._reset_table()

        def encode(self):
            """
            Encodes the data passed in to ``__init__()`` according to the LZW
            specification.
            """
            self.output = list()
            buffer = bytes()
            self._write_code(256)

            for b__ in self.data:
                # If we iterate on a bytes instance under Python 3, we get int
                # rather than bytes values, which we need to convert
                if version_info > (3, 0):
                    b__ = bytes([b__])

                if buffer + b__ in self.table:
                    buffer += b__
                else:
                    # Write the code of buffer to the codetext
                    self._write_code(self.table[buffer])
                    self._add_code_to_table(buffer + b__)

                    buffer = b__

            self._write_code(self.table[buffer])
            self._write_code(257)

            # This results in an automatic assertion of the values of
            # self.result, since for each v one of them, 0 <= v <= 255
            return bytearray(self.output).decode("LATIN1")

        def _reset_table(self):
            """
            Brings the pattern-to-code-value table to default values.
            """
            self.bitspercode = 9

            if version_info < (3, 0):
                self.table = {chr(b): b for b in range(256)}
            else:
                self.table = {bytes([b]): b for b in range(256)}
            # self.table is actually a bytes-to-integers mapping, but we are
            # doing a little inoffensive misuse here!
            self.table[256] = len(self.table)
            self.table[257] = len(self.table)

        def _write_code(self, code):
            """
            Tricky implementation method that serves in the conversion from
            usually higher-than-eight-bit values (input in ``code`` as
            integers) to a stream of bits. The serialization is performed by
            writing into a list of integer values.

            :param code: an integer value whose bit stream will be serialized
                inside ``self.result``.
            """
            bytes_alloc = int(
                math.ceil(float(self.bitpos + self.bitspercode) / 8)
            ) - len(self.output)
            self.output.extend([0] * bytes_alloc)
            bits_written = 0
            relbitpos = self.bitpos % 8
            bytepos = int(math.floor(self.bitpos / 8))

            while (self.bitspercode - bits_written) > 0:
                self.output[bytepos] |= (
                    ((code << bits_written) >> (self.bitspercode - 8)) & 0xFF
                ) >> relbitpos

                bits_written += min(8 - relbitpos, self.bitspercode - bits_written)
                relbitpos = (self.bitpos + bits_written) % 8
                bytepos = int(math.floor((self.bitpos + bits_written) / 8))

            self.bitpos += self.bitspercode

        def _add_code_to_table(self, value):
            if len(self.table) >= self.MAX_ENTRIES:
                self._write_code(256)
                self._reset_table()
            elif len(self.table) >= 2 ** self.bitspercode:
                self.bitspercode += 1

            self.table[value] = len(self.table)

    # pylint: disable=too-many-instance-attributes
    class Decoder(object):      #pylint: disable=useless-object-inheritance
        """
        TODO : documentation to be added
        """
        MAX_ENTRIES = 2 ** 12

        CLEARDICT = 256
        STOP = 257

        def __init__(self, data):
            """
            Decodes a stream of data encoded according to LZW.

            :param data: a string or byte string.
            """
            self.data = data
            self.bytepos = 0
            self.bitpos = 0
            self.dict = [b""] * self.MAX_ENTRIES
            self.dictindex = None
            self.bitspercode = None

            for i in range(256):
                if version_info < (3, 0):
                    self.dict[i] = chr(i)
                else:
                    self.dict[i] = bytes([i])

            self._reset_dict()

        def decode(self):
            """
            TIFF 6.0 specification explains in sufficient details the steps to
            implement the LZW encode() and decode() algorithms.

            :rtype: bytes
            """
            # TO-DO Make return value type bytes, as instructed by ISO 32000
            c_w = self.CLEARDICT
            output = b""

            while True:
                p_w = c_w
                c_w = self._read_code()

                if c_w == -1:
                    raise PdfReadError("Missed the stop code in during LZW decoding")
                if c_w == self.STOP:
                    break
                if c_w == self.CLEARDICT:
                    self._reset_dict()
                elif p_w == self.CLEARDICT:
                    output += self.dict[c_w]
                else:
                    if c_w < self.dictindex:
                        output += self.dict[c_w]

                        if version_info > (3, 0):
                            p__ = self.dict[p_w] + bytes([self.dict[c_w][0]])
                        else:
                            p__ = self.dict[p_w] + self.dict[c_w][0]

                        self._add_code_to_table(p__)
                    else:
                        if version_info > (3, 0):
                            p__ = self.dict[p_w] + bytes([self.dict[p_w][0]])
                        else:
                            p__ = self.dict[p_w] + self.dict[p_w][0]

                        output += p__
                        self._add_code_to_table(p__)

            return output

        def _reset_dict(self):
            self.dictindex = 258
            self.bitspercode = 9

        def _read_code(self):
            toread = self.bitspercode
            value = 0

            while toread > 0:
                if self.bytepos >= len(self.data):
                    return -1

                nextbits = pypdfOrd(self.data[self.bytepos])
                bitsfromhere = 8 - self.bitpos

                if bitsfromhere > toread:
                    bitsfromhere = toread

                value |= (
                    (nextbits >> (8 - self.bitpos - bitsfromhere))
                    & (0xFF >> (8 - bitsfromhere))
                ) << (toread - bitsfromhere)
                toread -= bitsfromhere
                self.bitpos += bitsfromhere

                if self.bitpos >= 8:
                    self.bitpos = 0
                    self.bytepos = self.bytepos + 1

            return value

        def _add_code_to_table(self, data):
            self.dict[self.dictindex] = data
            self.dictindex += 1

            if self.dictindex >= (2 ** self.bitspercode) and self.bitspercode < 12:
                self.bitspercode += 1

    @staticmethod
    def encode(data, decode_params=None):                   #pylint: disable=unused-argument
        """
        :param data: ``str`` or ``bytes`` input to encode.
        :param decode_params:
        :return: encoded LZW text.
        """
        return LZWCodec.Encoder(data).encode()

    @staticmethod
    def decode(data, decode_params=None):                   #pylint: disable=unused-argument
        """
        :param data: ``bytes`` or ``str`` text to decode.
        :param decode_params: a dictionary of parameter values.
        :return: decoded data.
        :rtype: bytes
        """
        return LZWCodec.Decoder(data).decode()


# pylint: disable=too-few-public-methods
class ASCII85Codec(object):                     #pylint: for Py 2.x disable=useless-object-inheritance
    """
    Decodes string ASCII85-encoded data into a byte format.
    """

    # pylint: disable=too-many-branches, too-many-statements, too-many-locals
    @staticmethod
    def encode(data, decode_params=None):       #pylint: disable=unused-argument
        """
        Encodes chunks of 4-byte sequences of textual or bytes data according
        to the base-85 ASCII encoding algorithm.

        :param data: a str or byte sequence of values.
        :return: ASCII85-encoded data in bytes format (equal to str in Python
            2).
        """
        if version_info[0] < 3:
            result = str()
            filler = "\x00" if isinstance(data, str) else b"\x00"

            #used to be :if type(data) not in (str, bytes):
            if not isinstance(data, (str, bytes)):
                raise TypeError(
                    "Expected str or bytes type for data, got %s instead" % type(data)
                )

            for group in range(int(math.ceil(len(data) / 4.0))):
                decimal_repr = 0
                ascii85 = str()
                group_width = min(4, len(data) - 4 * group)

                if group_width < 4:
                    data = data + (4 - group_width) * filler

                for byte in range(4):
                    decimal_repr += pypdfOrd(data[4 * group + byte]) << 8 * (4 - byte - 1)

                # If all bytes are 0, we turn them into a single 'z' character
                if decimal_repr == 0 and group_width == 4:
                    ascii85 = "z"
                else:
                    for i__ in range(5):                    #pylint:   disable=unused-variable
                        ascii85 = chr(decimal_repr % 85 + 33) + ascii85
                        decimal_repr = int(decimal_repr / 85.0)

                # In case of a partial group of four bytes, the standard says:
                # «Finally, it shall write only the first n + 1 characters of the
                # resulting group of 5.» - ISO 32000 (2008), sec. 7.4.3
                result += ascii85[: min(5, group_width + 1)]

            return ("<~" + result + "~>").encode("LATIN1")
        return base64.a85encode(data, adobe=True)   # else Python version 3.x

    @staticmethod
    def decode(data, decode_params=None):           #pylint: disable=unused-argument
        """
        Decodes binary (bytes or str) data previously encoded in ASCII85.

        :param data: a str or bytes sequence of ASCII85-encoded characters.
        :return: bytes for Python 3, str for Python 2.
        """
        if version_info[0] < 3:
            group_index = b__ = 0
            out = bytearray()

            if isinstance(data, unicode):       #pylint: disable=undefined-variable
                try:
                    data = data.encode("ascii")
                except UnicodeEncodeError:
                    raise ValueError(
                        "unicode argument should contain only ASCII characters"
                    )

            if isinstance(data, bytes):
                data = data.decode("LATIN1")
            elif not isinstance(data, str):
                raise TypeError(
                    "data is of %s type, expected str or bytes"
                    % data.__class__.__name__
                )

            # Strip leading '<~' characters, if present.
            if data.startswith("<~"):
                data = data[2:]

            # Ensure that the data ends with '~>' characters.
            if not data.endswith("~>"):
                raise ValueError("Ascii85 encoded byte sequences must end with '~>'")

            for index, c__ in enumerate(data):
                # Ignore whitespace characters.
                if not c__.strip(" \n\r\t\v"):
                    continue
                byte = ord(c__)

                # 33 == ord('!') and 117 == ord('u')
                if 33 <= byte <= 117:
                    group_index += 1
                    b__ = b__ * 85 + (byte - 33)

                    if group_index == 5:
                        out += struct.pack(b">L", b__)
                        group_index = b__ = 0
                # 122 == ord('z')
                elif byte == 122:
                    if group_index:
                        raise ValueError("z inside Ascii85 5-tuple")
                    out.extend(b"\x00\x00\x00\x00")
                # 126 == ord('~') and 62 == ord('>')
                elif byte == 126 and data[index + 1] == ">":
                    if group_index:
                        for _ in range(5 - group_index):
                            b__ = b__ * 85 + 84
                        out += struct.pack(b">L", b__)[: group_index - 1]

                    break
                else:
                    raise ValueError("Value '%c' not recognized" % c__)

            return bytes(out)
        return base64.a85decode(data, adobe=True) #else if python version 3.x


# pylint: disable=too-few-public-methods
class DCTCodec(object):     #pylint: for Py 2.x disable=useless-object-inheritance
    """
    TODO: documentation
    """
    @staticmethod
    def encode(data, decode_params=None):
        """
        encode data
        """
        raise NotImplementedError()

    @staticmethod
    def decode(data, decode_params=None):      #pylint: disable=unused-argument
        """
        TO-DO Implement this filter.
        """
        return data


class JPXCodec(object):  #pylint: for Py 2.x disable=useless-object-inheritance disable=too-few-public-methods
    """
    TODO : documentation
    """
    @staticmethod
    def encode(data, decode_params=None):       #pylint: disable=unused-argument
        """
        not implemented
        """
        raise NotImplementedError()

    @staticmethod
    def decode(data, decode_params=None):       #pylint: disable=unused-argument
        """
        TO-DO Implement this filter.
        """
        return data


class CCITTFaxCodec(object):  #pylint: for Py 2.x disable=useless-object-inheritance disable=too-few-public-methods
    """
    TODO : documentation
    """
    @staticmethod
    def encode(data, decode_params=None):
        """
        not implememented
        """
        raise NotImplementedError()

    @staticmethod
    def decode(data, decode_params=None, height=0):
        """
        decode data
        """
        if decode_params:
            if decode_params.get("/K", 1) == -1:
                ccitt_group = 4
            else:
                ccitt_group = 3

        width = decode_params["/Columns"]
        img_size = len(data)
        tiff_header_struct = "<" + "2s" + "h" + "l" + "h" + "hhll" * 8 + "h"
        tiff_header = struct.pack(
            tiff_header_struct,
            b"II",  # Byte order indication: Little endian
            42,  # Version number (always 42)
            8,  # Offset to first IFD
            8,  # Number of tags in IFD
            256,
            4,
            1,
            width,  # ImageWidth, LONG, 1, width
            257,
            4,
            1,
            height,  # ImageLength, LONG, 1, length
            258,
            3,
            1,
            1,  # BitsPerSample, SHORT, 1, 1
            # Compression, SHORT, 1, 4 = CCITT Group 4 fax encoding
            259,
            3,
            1,
            ccitt_group,
            262,
            3,
            1,
            0,  # Thresholding, SHORT, 1, 0 = WhiteIsZero
            # StripOffsets, LONG, 1, length of header
            273,
            4,
            1,
            struct.calcsize(tiff_header_struct),
            278,
            4,
            1,
            height,  # RowsPerStrip, LONG, 1, length
            279,
            4,
            1,
            img_size,  # StripByteCounts, LONG, 1, size of image
            0,  # last IFD
        )

        # TO-DO Finish implementing (the code above only adds header infos.)

        return tiff_header + data


# pylint: disable=too-many-branches
def decode_stream_data(stream):
    """
    :param stream: ``EncodedStreamObject`` instance.
    :return: decoded data from the encoded stream.
    """
    filters = stream.get("/Filter", ())

    if filters and not isinstance(filters[0], NameObject):
        # we have a single filter instance
        filters = (filters,)

    data = stream._data

    # If there is not data to decode we should not try to decode the data.
    if data:
        for filter_type in filters:
            if filter_type in ["/FlateDecode", "/Fl"]:
                data = FlateCodec.decode(data, stream.get("/DecodeParms"))
            elif filter_type in ["/ASCIIHexDecode", "/AHx"]:
                data = ASCIIHexCodec.decode(data)
            elif filter_type in ["/LZWDecode", "/LZW"]:
                data = LZWCodec.decode(data, stream.get("/DecodeParms"))
            elif filter_type in ["/ASCII85Decode", "/A85"]:
                data = ASCII85Codec.decode(data, stream.get("/DecodeParms"))
            elif filter_type == "/DCTDecode":
                data = DCTCodec.decode(data)
            elif filter_type == "/JPXDecode":
                data = JPXCodec.decode(data)
            elif filter_type == "/CCITTFaxDecode":
                height = stream.get("/Height", ())
                data = CCITTFaxCodec.decode(data, stream.get("/DecodeParms"), height)
            elif filter_type == "/Crypt":
                decode_params = stream.get("/DecodeParams", {})

                if "/Name" not in decode_params and "/Type" not in decode_params:
                    pass
                else:
                    raise NotImplementedError(
                        "/Crypt filter with /Name or /Type not supported yet"
                    )
            else:
                # Unsupported filter
                raise NotImplementedError("unsupported filter %s" % filter_type)

    return data
