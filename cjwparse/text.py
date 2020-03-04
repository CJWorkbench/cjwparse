import codecs
import io
from pathlib import Path
from typing import List, Optional

import cchardet as chardet

from cjwmodule.i18n import I18nMessage

from .i18n import _trans_cjwparse
from .settings import DEFAULT_SETTINGS, Settings

UNICODE_BOM = "\uFFFE"


def detect_encoding(
    bytesio: io.BytesIO, *, settings: Settings = DEFAULT_SETTINGS
) -> str:
    """
    Detect charset, as Python-friendly encoding string.

    Peculiarities:

    * Reads file by CHARDET_CHUNK_SIZE defined in settings.py
    * Stops seeking when detector.done flag True
    * Seeks back to beginning of file for downstream usage
    * Returns "utf-8" in case of empty file or ASCII -- since the parse
      framework is designed to be UTF-native.
    """
    detector = chardet.UniversalDetector()
    while not detector.done:
        chunk = bytesio.read(settings.CHARDET_CHUNK_SIZE)
        if not chunk:
            break  # EOF
        detector.feed(chunk)

    detector.close()
    bytesio.seek(0)
    encoding = detector.result["encoding"]
    if encoding is None:
        # There isn't enough data for chardet
        return "UTF-8"
    elif encoding == "ASCII":
        return "UTF-8"
    else:
        return encoding


def transcode_to_utf8_and_warn(
    src: Path, dest: Path, encoding: Optional[str], *, settings: Settings
) -> List[I18nMessage]:
    """
    Transcode `dest` to UTF-8 if it has a different encoding.

    Remove a starting U+FFFE Unicode byte-order marker, if it exists.

    Recover from errors by inserting U+FFFD. If a recovery occurs, return a
    I18nMessage.

    Raise LookupError for an `encoding` Python cannot handle.

    Raise UnicodeError upon reaching an unrecoverable error (such as missing
    byte-order marker in "UTF-16").
    """
    BUFFER_SIZE = 1024 * 1024
    warnings = []

    with src.open("rb") as src_f, dest.open("wb") as dest_f:
        if encoding is None:
            encoding = detect_encoding(src_f, settings=settings)

        # Start with a `strict` decoder. Judging by codecs.py's innards,
        # we're allowed to change .errors later if we run into an error.
        decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
        decoder.errors = "strict"
        pos = 0  # to build warnings

        def decode_and_maybe_warn(buf: bytes, final: bool) -> str:
            nonlocal warnings
            try:
                # raise UnicodeError
                return decoder.decode(buf, final)
            except UnicodeDecodeError as err:
                # UnicodeDecodeError we can fix with errors='replace'
                assert decoder.errors == "strict" and len(warnings) == 0
                decoder_state_buf = decoder.getstate()[0]
                warnings.append(
                    _trans_cjwparse(
                        "text.repaired_encoding",
                        "Encoding error: byte {byte} is invalid {encoding} at position {position}. We replaced invalid bytes with “�”.",
                        {
                            "byte": "0x%02X" % (decoder_state_buf + buf)[err.start],
                            "encoding": err.encoding,
                            "position": (pos - len(decoder_state_buf) + err.start),
                        },
                    )
                )
                decoder.errors = "replace"
                return decoder.decode(buf, final)
            # Any other UnicodeError will be raised

        while True:
            buf = src_f.read(BUFFER_SIZE)
            if not len(buf):
                # end of file -- the only way to exit the loop
                s = decode_and_maybe_warn(b"", True)
                dest_f.write(codecs.utf_8_encode(s)[0])
                return warnings

            s = decode_and_maybe_warn(buf, False)

            # Remove Unicode byte-order marker (no matter what input encoding)
            if pos == 0 and s[0] == UNICODE_BOM:
                s = s[1:]

            dest_f.write(codecs.utf_8_encode(s)[0])

            pos += len(buf)
