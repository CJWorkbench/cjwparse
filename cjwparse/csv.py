import array
import contextlib
import csv
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Pattern, Tuple

import numpy as np
import pyarrow

from cjwmodule.i18n import I18nMessage
from cjwmodule.util.colnames import gen_unique_clean_colnames_and_warn

from ._util import tempfile_context
from .i18n import _trans_cjwparse
from .postprocess import dictionary_encode_columns
from .settings import DEFAULT_SETTINGS, Settings
from .text import transcode_to_utf8_and_warn


class ErrorPattern(NamedTuple):
    pattern: Pattern
    # `Callable` so each one can call `_trans_cjwparse()` -- which marks strings
    # for translations.
    message: Callable[[Dict[str, Any]], I18nMessage]


class ParseCsvResult(NamedTuple):
    table: pyarrow.Table
    warnings: List[I18nMessage]


_ERROR_PATTERNS = [
    ErrorPattern(
        re.compile(
            r"^skipped (?P<n_rows>\d+) rows \(after row limit of (?P<max_n_rows>\d+)\)$"
        ),
        (
            lambda n_rows, max_n_rows: _trans_cjwparse(
                "warning.skipped_rows",
                "{n_rows, plural, one{Skipped # row} other{Skipped # rows}} (after row limit of {max_n_rows})",
                dict(n_rows=int(n_rows), max_n_rows=int(max_n_rows)),
            )
        ),
    ),
    ErrorPattern(
        re.compile(
            r"^skipped (?P<n_columns>\d+) columns \(after column limit of (?P<max_n_columns>\d+)\)$"
        ),
        (
            lambda n_columns, max_n_columns: _trans_cjwparse(
                "warning.skipped_columns",
                "{n_columns, plural, one{Skipped # column} other{Skipped # columns}} (after column limit of {max_n_columns})",
                dict(n_columns=int(n_columns), max_n_columns=int(max_n_columns)),
            )
        ),
    ),
    ErrorPattern(
        re.compile(
            r"^truncated (?P<n_values>\d+) values \(value byte limit is (?P<max_n_bytes>\d+); see row (?P<row_index>\d+) column (?P<column_index>\d+)\)$"
        ),
        (
            lambda n_values, max_n_bytes, row_index, column_index: _trans_cjwparse(
                "warning.truncated_values",
                "{n_values, plural, one{Truncated # value} other{Truncated # values}} (value byte limit is {max_n_bytes}; see row {row_number} column {column_number})",
                dict(
                    n_values=int(n_values),
                    max_n_bytes=int(max_n_bytes),
                    row_number=int(row_index) + 1,
                    column_number=int(column_index) + 1,
                ),
            )
        ),
    ),
    ErrorPattern(
        re.compile(
            r"^repaired (?P<n_values>\d+) values \(misplaced quotation marks; see row (?P<row_index>\d+) column (?P<column_index>\d+)\)$"
        ),
        (
            lambda n_values, row_index, column_index: _trans_cjwparse(
                "csv.repaired_quotes",
                "{n_values, plural, one{Repaired # value} other{Repaired # values}} (misplaced quotation marks; see row {row_number} column {column_number})",
                dict(
                    n_values=int(n_values),
                    row_number=int(row_index) + 1,
                    column_number=int(column_index) + 1,
                ),
            )
        ),
    ),
    ErrorPattern(
        re.compile(r"^repaired last value \(missing quotation mark\)$"),
        (
            lambda: _trans_cjwparse(
                "csv.repaired_eof", "Repaired last value (missing quotation mark)"
            )
        ),
    ),
]


def _parse_csv_to_arrow_warning(line: str) -> I18nMessage:
    """
    Parse a single line of csv-to-arrow output.

    Raise RuntimeError if a line cannot be parsed. (We can't recover from that
    because we don't know what's happening.)
    """
    for pattern, builder in _ERROR_PATTERNS:
        match = pattern.match(line)
        if match:
            return builder(**match.groupdict())
    raise RuntimeError("Could not parse csv-to-arrow output line: %r" % line)


def _parse_csv_to_arrow_warnings(text: str) -> List[I18nMessage]:
    return [_parse_csv_to_arrow_warning(line) for line in text.split("\n") if line]


def _postprocess_name_columns(
    table: pyarrow.Table, has_header: bool, settings: Settings
) -> Tuple[pyarrow.Table, List[I18nMessage]]:
    """
    Return `table`, with final column names but still String values.
    """
    if has_header and table.num_rows > 0:
        names, warnings = gen_unique_clean_colnames_and_warn(
            list((c[0].as_py() if c[0].is_valid else "") for c in table.columns),
            settings=settings,
        )

        # Remove header (zero-copy: builds new pa.Table with same backing data)
        table = table.slice(1)
    else:
        names = [f"Column {i + 1}" for i in range(len(table.columns))]
        warnings = []

    return (
        pyarrow.table(dict(zip(names, table.columns))),
        warnings,
    )


def _nix_utf8_chunk_empty_strings(chunk: pyarrow.Array) -> pyarrow.Array:
    """
    Return a pa.Array that replaces "" with null.

    Assume `arr` is of type `utf8` or a dictionary of `utf8`.
    """
    # pyarrow's cast() can't handle empty string. Create a new Array with
    # "" changed to null.
    _, offsets_buf, data_buf = chunk.buffers()

    # Build a new validity buffer, based on offsets. Empty string = null.
    # Assume `data` has no padding bytes in the already-null values. That way
    # we can ignore the _original_ validity buffer and assume all original
    # values are not-null. (Null values are stored as "" plus "invalid".)
    #
    # Validity-bitmap spec:
    # https://arrow.apache.org/docs/format/Columnar.html#validity-bitmaps

    # first offset must be 0. Next offsets are used to calculate lengths
    offsets = array.array("i")
    assert offsets.itemsize == 4
    offsets.frombytes(offsets_buf)
    if sys.byteorder != "little":
        offsets.byteswap()  # pyarrow is little-endian

    validity = bytearray()
    null_count = 0
    last_offset = offsets[0]
    assert last_offset == 0
    pos = 1
    while True:
        # Travel offsets in strides of 8: one per char in the validity bitmap.
        # Pad with an extra 1 bit -- [2020-02-20, adamhooper] I think I read
        # this is needed somewhere.
        valid_byte = 0x00
        block = offsets[pos : pos + 8]
        try:
            if block[0] > last_offset:
                valid_byte |= 0x1
            else:
                null_count += 1
            if block[1] > block[0]:
                valid_byte |= 0x2
            else:
                null_count += 1
            if block[2] > block[1]:
                valid_byte |= 0x4
            else:
                null_count += 1
            if block[3] > block[2]:
                valid_byte |= 0x8
            else:
                null_count += 1
            if block[4] > block[3]:
                valid_byte |= 0x10
            else:
                null_count += 1
            if block[5] > block[4]:
                valid_byte |= 0x20
            else:
                null_count += 1
            if block[6] > block[5]:
                valid_byte |= 0x40
            else:
                null_count += 1
            if block[7] > block[6]:
                valid_byte |= 0x80
            else:
                null_count += 1
            validity.append(valid_byte)
            last_offset = block[7]
            pos += 8
        except IndexError:
            validity.append(valid_byte)
            break  # end of offsets

    validity_buf = pyarrow.py_buffer(validity)

    # We may have over-counted in null_count: anything before `chunk.offset`
    # should not count.
    #
    # It's less work to "undo" the counting we did before -- otherwise we'd
    # riddle the above loop with if-statements.
    for i in range(chunk.offset):
        if offsets[i + 1] == offsets[i]:
            null_count -= 1

    return pyarrow.StringArray.from_buffers(
        length=len(chunk),
        value_offsets=offsets_buf,
        data=data_buf,
        null_bitmap=validity_buf,
        null_count=null_count,
        offset=chunk.offset,
    )


SCARY_BYTE_REGEX = re.compile(b"[nainfNAINF]")


def _utf8_chunk_may_contain_inf_or_nan(chunk: pyarrow.Array) -> bool:
    """
    Return true if we should fast-skip converting a pa.Array.

    The _true_ reason for this function is to test whether an Array contains
    "Inf" or "NaN". A number-conversion library will parse those. But _this_
    library is for Workbench, and Workbench doesn't support NaN/Inf. So this
    function helps us decide _not_ to auto-convert a column when the intent
    isn't perfectly clear.

    Assume `arr` is of type `utf8` or a dictionary of `utf8`. Assume there
    are no gaps hidden in null values in the buffer. (It's up to the caller to
    prove this.)
    """
    _, offsets_buf, data_buf = chunk.buffers()

    offsets = array.array("i")
    assert offsets.itemsize == 4
    offsets.frombytes(offsets_buf)
    if sys.byteorder != "little":
        offsets.byteswap()  # pyarrow is little-endian

    offset0 = offsets[chunk.offset]
    offsetN = offsets[chunk.offset + len(chunk)]  # len(offsets) == 1 + len(chunk)

    b = data_buf[offset0:offsetN].to_pybytes()
    return SCARY_BYTE_REGEX.search(b) is not None


def _autocast_column(data: pyarrow.ChunkedArray) -> pyarrow.ChunkedArray:
    """
    Convert `data` to float64 or int(64|32|16|8); as fallback, return `data`.

    Assume `data` is of type `utf8` or a dictionary of utf8.

    *Implementation wart*: this may choose float64 when integers would seem a
    better choice, because we use Pandas and Pandas does not support nulls
    in integer columns.
    """
    # All-empty (and all-null) columns stay text
    for chunk in data.iterchunks():
        # https://arrow.apache.org/docs/format/Columnar.html#variable-size-binary-layout
        _, offsets_buf, _ = chunk.buffers()
        # If data has an offset, ignore what comes before
        #
        # We don't need to grab the _int_ offset: we can just look at the
        # byte-representation of it.
        offset_0_buf = offsets_buf[chunk.offset * 4 : (chunk.offset + 1) * 4]
        # last offset isn't always the last 4 bytes: there can be padding
        offset_n_buf = offsets_buf[
            (chunk.offset + len(chunk)) * 4 : (chunk.offset + len(chunk) + 1) * 4
        ]
        if offset_0_buf.to_pybytes() != offset_n_buf.to_pybytes():
            # there's at least 1 byte of text. (Assumes the CSV reader doesn't
            # pad the buffer with gibberish.)
            break
    else:
        # there are 0 bytes of text
        return data

    # Convert "" => null, so pyarrow cast() won't balk at it.
    sane = pyarrow.chunked_array(
        [_nix_utf8_chunk_empty_strings(chunk) for chunk in data.iterchunks()]
    )

    for chunk in sane.iterchunks():
        # pyarrow cast() uses double-conversion, so it parses "NaN" and "Inf"
        # as doubles. Workbench doesn't support NaN or Inf, so don't convert to
        # them.
        if _utf8_chunk_may_contain_inf_or_nan(chunk):
            return data

    try:
        numbers = sane.cast(pyarrow.float64())
    except pyarrow.ArrowInvalid:
        # Some string somewhere wasn't a number
        return data

    # Test that there's no infinity. We'll use numpy. .to_numpy() with
    # zero_copy_only=False will convert nulls to NaN. That's fine, since we
    # know `numbers` has no NaN values (because `cast()` would have raised
    # rather than return a NaN.)
    for chunk in numbers.iterchunks():
        npchunk = chunk.to_numpy(zero_copy_only=False)
        if np.inf in npchunk or -np.inf in npchunk:
            # Numbers too large
            return data

    # Downcast integers, when possible.
    #
    # We even downcast float to int. Workbench semantics say a Number is a
    # Number; so we might as well store it efficiently.
    try:
        # Shrink as far as we can, until pyarrow complains.
        #
        # pyarrow will error "Floating point value truncated" if a conversion
        # from float to int would be lossy.
        #
        # We'll return the last _successful_ `numbers` result.
        numbers = numbers.cast(pyarrow.int32())
        numbers = numbers.cast(pyarrow.int16())
        numbers = numbers.cast(pyarrow.int8())
    except pyarrow.ArrowInvalid:
        pass

    return numbers


def _postprocess_autocast_columns(table: pyarrow.Table) -> pyarrow.Table:
    return pyarrow.table(
        {
            name: _autocast_column(column)
            for name, column in zip(table.column_names, table.columns)
        }
    )


def _postprocess_table(
    table: pyarrow.Table,
    has_header: bool,
    autoconvert_text_to_numbers: bool,
    settings: Settings,
) -> Tuple[pyarrow.Table, List[I18nMessage]]:
    """
    Transform `raw_table` to meet our standards:

    * If `has_headers` is True, remove the first row (zero-copy) and use it to
      build column names -- which we guarantee are unique. Otherwise, generate
      unique column names.
    * Auto-convert each column to numeric if every value is represented
      correctly. (`""` becomes `null`. This conversion is lossy for the myriad
      numbers CSV can represent accurately that int/double cannot.
      TODO auto-conversion optional.)
    * Convert each utf8 column to dictionary if it agrees with
      `settings.MAX_DICTIONARY_PYLIST_N_BYTES` and
      `settings.MIN_DICTIONARY_COMPRESSION_RATIO`.
    """
    table, warnings = _postprocess_name_columns(table, has_header, settings)
    if autoconvert_text_to_numbers:
        table = _postprocess_autocast_columns(table)
    table = dictionary_encode_columns(table, settings=settings)
    return table, warnings


def detect_delimiter(path: Path, settings: Settings):
    with path.open("r", encoding="utf-8") as textio:
        sample = textio.read(settings.SEP_DETECT_CHUNK_SIZE)

    try:
        dialect = csv.Sniffer().sniff(sample, ",;\t")
    except csv.Error:
        # When in doubt, CSV. (We have no logic to handle an exception.)
        dialect = csv.excel

    return dialect.delimiter


def _parse_csv(
    path: Path,
    *,
    settings: Settings = DEFAULT_SETTINGS,
    encoding: Optional[str],
    delimiter: Optional[str],
    has_header: bool,
    autoconvert_text_to_numbers: bool,
) -> ParseCsvResult:
    """
    Parse CSV, TSV or other delimiter-separated text file.

    Raise LookupError for an `encoding` Python cannot handle.

    Raise UnicodeError when the file simply cannot be read as text. (e.g., a
    UTF-16 file that does not start with a byte-order marker.)

    The process:

    1. Truncate the file to our maximum size. (WARNING This is destructive!)
       (TODO if any caller minds the truncation, fix this logic.)
    2. Convert the file to UTF-8.
    3. Sniff delimiter, if the passed argument is `None`.
    4. Run `csv-to-arrow` to parse the CSV into unnamed columns.
    5. Postprocess each column: remove its header if needed and
       dictionary-encode if it's helpful. (This doesn't cost much RAM per
       column: either dictionary encoding makes it small, or it's a zero-copy
       slice of the csv-to-arrow output file.)
    6. Write the final Arrow file.
    """
    warnings = []

    with contextlib.ExitStack() as ctx:
        n_bytes = path.stat().st_size
        if n_bytes > settings.MAX_CSV_BYTES:
            # We can't simply os.truncate() the input file, because sandboxed code
            # can't modify input files.
            truncated_path = ctx.enter_context(tempfile_context(prefix="truncated-"))
            with path.open("rb") as src, truncated_path.open("wb") as dest:
                os.sendfile(dest.fileno(), src.fileno(), 0, settings.MAX_CSV_BYTES)
            path = truncated_path
            warnings.append(
                _trans_cjwparse(
                    "csv.truncated_file",
                    "{n_bytes_truncated, one{Truncated # byte} other{Truncated # bytes}} from file (maximum is {max_n_bytes} bytes)",
                    dict(
                        n_bytes_truncated=(n_bytes - settings.MAX_CSV_BYTES),
                        max_n_bytes=settings.MAX_CSV_BYTES,
                    ),
                )
            )

        utf8_path = ctx.enter_context(tempfile_context(prefix="utf8-", suffix=".txt"))
        # raises LookupError, UnicodeError
        warnings.extend(
            transcode_to_utf8_and_warn(path, utf8_path, encoding, settings=settings)
        )

        # Sniff delimiter
        if not delimiter:
            delimiter = detect_delimiter(utf8_path, settings)

        with tempfile_context(suffix=".arrow") as arrow_path:
            # raise subprocess.CalledProcessError on error ... but there is no
            # error csv-to-arrow will throw that we can recover from.
            child = subprocess.run(
                [
                    "/usr/bin/csv-to-arrow",
                    "--delimiter",
                    delimiter,
                    "--max-rows",
                    str(settings.MAX_ROWS_PER_TABLE),
                    "--max-columns",
                    str(settings.MAX_COLUMNS_PER_TABLE),
                    "--max-bytes-per-value",
                    str(settings.MAX_BYTES_PER_VALUE),
                    utf8_path.as_posix(),
                    arrow_path.as_posix(),
                ],
                capture_output=True,
                check=True,
            )
            warnings.extend(_parse_csv_to_arrow_warnings(child.stdout.decode("utf-8")))

            reader = pyarrow.ipc.open_file(arrow_path.as_posix())
            raw_table = reader.read_all()  # efficient -- RAM is mmapped

    table, more_warnings = _postprocess_table(
        raw_table, has_header, autoconvert_text_to_numbers, settings
    )
    return ParseCsvResult(table, warnings + more_warnings)


def parse_csv(
    path: Path,
    *,
    output_path: Path,
    settings: Settings = DEFAULT_SETTINGS,
    encoding: Optional[str],
    delimiter: Optional[str],
    has_header: bool,
    autoconvert_text_to_numbers: bool,
) -> List[I18nMessage]:
    result = _parse_csv(
        path,
        encoding=encoding,
        settings=settings,
        delimiter=delimiter,
        has_header=has_header,
        autoconvert_text_to_numbers=autoconvert_text_to_numbers,
    )
    with pyarrow.ipc.RecordBatchFileWriter(
        output_path.as_posix(), schema=result.table.schema
    ) as writer:
        writer.write_table(result.table)

    return result.warnings
