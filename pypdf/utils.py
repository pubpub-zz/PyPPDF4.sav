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
Utility functions for PDF library.
"""
from binascii import hexlify
from sys import version_info

try:
    import __builtin__ as builtins
except ImportError:  # Py3
    import builtins

if version_info < (3, 0):
    from cStringIO import StringIO                                          #pylint: Python 2.x disable=import-error

    BytesIO = StringIO
else:
    from io import StringIO, BytesIO                                        #pylint: used in other modules disable=unused-import

__author__ = "Mathieu Fenniak"
__author_email__ = "biziqe@mathieu.fenniak.net"


xrange_fn = getattr(builtins, "xrange", range)
_basestring = getattr(builtins, "basestring", str)

BytesType = type(bytes())  # Works the same in Python 2.X and 3.X
StringType = getattr(builtins, "unicode", str)
int_types = (int, long) if version_info[0] < 3 else (int,)                  #pylint: python 2.x disable=undefined-variable


# Make basic type tests more consistent
def is_string(s__):
    """Test if arg is a string. Compatible with Python 2 and 3."""
    return isinstance(s__, _basestring)


def is_int(n__):
    """Test if arg is an int. Compatible with Python 2 and 3."""
    return isinstance(n__, int_types)


def is_bytes(b__):
    """Test if arg is a bytes instance. Compatible with Python 2 and 3."""
    return isinstance(b__, BytesType)
isBytes = is_bytes


# custom implementation of warnings.formatwarning
def format_warning(message, category, filename, lineno, line=None):         #pylint: to match warnings API disable=unused-argument
    """ format warning message """
    file = filename.replace("/", "\\").rsplit("\\", 1)[-1]  # find the file name
    return "%s: %s [%s:%s]\n" % (category.__name__, message, file, lineno)
formatWarning = format_warning

def read_until_whitespace(stream, maxchars=None):
    """
    Reads non-whitespace characters and returns them.
    Stops upon encountering whitespace or when maxchars is reached.
    """
    txt = pypdfBytes("")

    while True:
        tok = stream.read(1)

        if tok.isspace() or not tok:
            break

        txt += tok
        if len(txt) == maxchars:
            break

    return txt
readUntilWhitespace = read_until_whitespace


def read_non_whitespace(stream):
    """
    Finds and reads the next non-whitespace character (ignores whitespace).

    :param stream: a file-like object.
    """
    tok = WHITESPACES[0]

    while tok in WHITESPACES:
        tok = stream.read(1)

    return tok


def skip_over_whitespace(stream):
    """
    Similar to ``read_non_whitespace()``, but returns a Boolean if more than
    one whitespace character was read.

    :param stream: a file-like object.
    """
    tok = WHITESPACES[0]
    cnt = 0

    while tok in WHITESPACES:
        tok = stream.read(1)
        cnt += 1

    return cnt > 1


def skip_over_comment(stream):
    """ move stream cursor after comment """
    tok = stream.read(1)
    stream.seek(-1, 1)

    if tok == pypdfBytes("%"):
        while tok not in (pypdfBytes("\n"), pypdfBytes("\r")):
            tok = stream.read(1)


def read_until_regex(stream, regex, ignore_eof=False):
    """
    Reads until the regular expression pattern matched (ignore the match)
    Raise PdfStreamError on premature end-of-file.
    :param bool ignore_eof: If true, ignore end-of-line and return immediately
    """
    name = pypdfBytes("")

    while True:
        tok = stream.read(16)

        if not tok:
            # stream has truncated prematurely
            if ignore_eof:
                return name
            raise PdfStreamError("Stream has ended unexpectedly")
        m__ = regex.search(tok)
        if m__ is not None:
            name += tok[: m__.start()]
            stream.seek(m__.start() - len(tok), 1)
            break
        name += tok

    return name


class ConvertFunctionsToVirtualList(object):                    #pylint: acceptable disable=useless-object-inheritance
    """ COMMENTS TO BE ADDED """
    def __init__(self, lengthFunction, getFunction):
        self.lengthFunction = lengthFunction                    #pylint: too hudge change for the moment disable=invalid-name 
        self.getFunction = getFunction                          #pylint: too hudge change for the moment disable=invalid-name

    def __len__(self):
        return self.lengthFunction()

    def __getitem__(self, index):
        if isinstance(index, slice):
            indices = xrange_fn(*index.indices(len(self)))
            cls = type(self)
            return cls(indices.__len__, lambda idx: self[indices[idx]])
        if not is_int(index):
            raise TypeError("sequence indices must be integers")

        len_self = len(self)

        if index < 0:
            # support negative indexes
            index = len_self + index
        if index < 0 or index >= len_self:
            raise IndexError("sequence index out of range")

        return self.getFunction(index)


def RC4Encrypt(key, plaintext):                                 #pylint: too hudge change for the moment disable=invalid-name
    """ encryption basic call """
    s__ = list(range(256))
    j__ = 0

    for i in range(256):
        j__ = (j__ + s__[i] + pypdfOrd(key[i % len(key)])) % 256
        s__[i], s__[j__] = s__[j__], s__[i]

    i, j__ = 0, 0
    retval = []

    for x__ in range(len(plaintext)):                           #pylint: disable=consider-using-enumerate
        i = (i + 1) % 256
        j__ = (j__ + s__[i]) % 256
        s__[i], s__[j__] = s__[j__], s__[i]
        t__ = s__[(s__[i] + s__[j__]) % 256]
        retval.append(pypdfBytes(chr(pypdfOrd(plaintext[x__]) ^ t__)))

    return pypdfBytes("").join(retval)


def matrix_multiply(a__, b__):
    """ matrix multiplication """
    return [[sum([float(i__) * float(j__) for i__, j__ in zip(row, col)]) for col in zip(*b__)]
            for row in a__]
matrixMultiply = matrix_multiply


class PyPdfError(Exception):
    """ Exception definition """


class PdfReadError(PyPdfError):
    """ Exception definition """


class PageSizeNotDefinedError(PyPdfError):
    """ Exception definition """


class PdfReadWarning(UserWarning):
    """ Exception definition """


class PdfStreamError(PdfReadError):
    """ Exception definition """


def pypdf_bytes(s__):
    """
    :type s__: Union[bytes, str, int, unicode]
    :rtype: bytes
    """
    if version_info[0] < 3:
        if isinstance(s__, int):
            return chr(s__)
        if isinstance(s__, bytes):
            return s__
        return s__.encode("latin-1")
    if isinstance(s__, int):
        return bytes([s__])
    if isinstance(s__, bytes):
        return s__
    return s__.encode("latin-1")
pypdfBytes = pypdf_bytes


def pypdf_unicode(s__):
    """
    :type s__: Union[bytes, str, unicode]
    :returns: ``unicode`` for Python 2, ``str`` for Python 3.
    :rtype: Union[str, unicode]
    """
    if version_info[0] < 3:
        if isinstance(s__, unicode):              #pylint: disable=undefined-variable
            return s__
        return unicode(s__, "unicode_escape")     #pylint: disable=undefined-variable
    if isinstance(s__, str):
        return s__
    return s__.decode("unicode_escape")
pypdfUnicode = pypdf_unicode


def pypdf_str(b__):
    """
    :type b__: Union[bytes, str, unicode]
    :rtype: str
    """
    if version_info[0] < 3:
        if isinstance(b__, unicode):              #pylint: disable=undefined-variable
            return b__.encode("latin-1")
        return b__
    if isinstance(b__, bytes):
        return b__.decode("latin-1")
    return b__


def pypdf_ord(b__):
    """
    :type b__: Union[int, bytes, str, unicode]
    :rtype: int
    """
    if isinstance(b__, int):
        return b__
    return ord(b__)
pypdfOrd = pypdf_ord


def pypdf_chr(c__):
    """
    :type c: Union[int, bytes, str, unicode]
    :rtype: str
    """
    if isinstance(c__, int):
        return chr(c__)
    return chr(ord(c__))


def pypdf_bytearray(b__):
    """
    Abstracts the conversion from a ``bytes`` variable to a ``bytearray`` value
    over versions 2.7.x and 3 of Python.
    """
    if version_info[0] < 3:
        return b__
    return bytearray(b__)
pypdfBytearray = pypdf_bytearray


def hex_encode(s__):
    """
    Abstracts the conversion from a LATIN 1 string to an hex-valued string
    representation of the former over versions 2.7.x and 3 of Python.

    :param str s__: a ``str`` to convert from LATIN 1 to an hexadecimal string
        representation.
    :return: a hex-valued string, e.g. ``hexEncode("$A'") == "244127"``.
    :rtype: str
    """
    if version_info < (3, 0):
        return s__.encode("hex")
    if isinstance(s__, str):
        s__ = s__.encode("LATIN1")

    # The output is in the set of "0123456789ABCDEF" characters. Using the
    # ASCII decoder is a safeguard against anomalies, albeit unlikely
    return hexlify(s__).decode("ASCII")
hexEncode = hex_encode


def hex_str(num):
    """ TO BE COMPLETED """
    return hex(num).replace("L", "")
hexStr = hex_str


WHITESPACES = [pypdfBytes(x) for x in [" ", "\n", "\r", "\t", "\x00"]]


def paeth_predictor(left, up_, up_left):
    """ TO BE COMPLETED """
    p__ = left + up_ - up_left
    dist_left = abs(p__ - left)
    dist_up = abs(p__ - up_)
    dist_up_left = abs(p__ - up_left)

    if dist_left <= dist_up and dist_left <= dist_up_left:
        return left
    if dist_up <= dist_up_left:
        return up_
    return up_left
paethPredictor = paeth_predictor


def pairs(sequence):
    """
    :param sequence: an indexable sequence value with ``__len__()``.
    :return: an iterable of paired values from ``sequence``.
    """
    if (len(sequence) % 2) != 0:
        raise ValueError("sequence must contain an even number of elements")

    for i in range(0, len(sequence) - 1, 2):
        yield (sequence[i], sequence[i + 1])
