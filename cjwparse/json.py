import subprocess
from pathlib import Path
from typing import List, NamedTuple, Optional

import pyarrow

from cjwmodule.i18n import I18nMessage

from ._util import tempfile_context
from .postprocess import dictionary_encode_columns
from .settings import DEFAULT_SETTINGS, Settings
from .text import transcode_to_utf8_and_warn


def _postprocess_table(table: pyarrow.Table, settings: Settings) -> pyarrow.Table:
    """
    Transform `raw_table` to meet our standards:

    * Convert each column dictionary if it agrees with
      `settings.MAX_DICTIONARY_SIZE` and
      `settings.MIN_DICTIONARY_COMPRESSION_RATIO`.
    """
    table = dictionary_encode_columns(table, settings=settings)
    return table


class ParseJsonResult(NamedTuple):
    table: pyarrow.Table
    warnings: List[I18nMessage]


def _parse_json(
    path: Path, *, settings: Settings = DEFAULT_SETTINGS, encoding: Optional[str]
) -> ParseJsonResult:
    """
    Parse JSON text file.

    Raise LookupError for an `encoding` Python cannot handle.

    Raise UnicodeError when the file simply cannot be read as text. (e.g., a
    UTF-16 file that does not start with a byte-order marker.)

    The process:

    1. Convert the file to UTF-8.
    2. Run `json-to-arrow` to parse the JSON into columns.
    3. Dictionary-encode each column if it's helpful.
    4. Write the final Arrow file.
    """
    warnings = []

    with tempfile_context(prefix="utf8-", suffix=".txt") as utf8_path:
        # raises LookupError, UnicodeError
        warnings.extend(
            transcode_to_utf8_and_warn(path, utf8_path, encoding, settings=settings)
        )

        with tempfile_context(suffix=".arrow") as arrow_path:
            # raise subprocess.CalledProcessError on error ... but there is no
            # error json-to-arrow will throw that we can recover from.
            child = subprocess.run(
                [
                    "/usr/bin/json-to-arrow",
                    "--max-rows",
                    str(settings.MAX_ROWS_PER_TABLE),
                    "--max-columns",
                    str(settings.MAX_COLUMNS_PER_TABLE),
                    "--max-bytes-per-value",
                    str(settings.MAX_BYTES_PER_VALUE),
                    "--max-bytes-total",
                    str(settings.MAX_BYTES_TEXT_DATA),
                    "--max-bytes-per-column-name",
                    str(settings.MAX_BYTES_PER_COLUMN_NAME),
                    utf8_path.as_posix(),
                    arrow_path.as_posix(),
                ],
                capture_output=True,
                check=True,
            )
            warnings.extend(
                [
                    I18nMessage("TODO_i18n", {"text": line}, None)
                    for line in child.stdout.decode("utf-8").split("\n")
                    if line
                ]
            )

            reader = pyarrow.ipc.open_file(arrow_path.as_posix())
            raw_table = reader.read_all()  # efficient -- RAM is mmapped

    table = _postprocess_table(raw_table, settings)
    return ParseJsonResult(table, warnings)


def parse_json(
    path: Path,
    *,
    output_path: Path,
    settings: Settings = DEFAULT_SETTINGS,
    encoding: Optional[str]
) -> List[I18nMessage]:
    table, warnings = _parse_json(path, encoding=encoding, settings=settings)
    with pyarrow.ipc.RecordBatchFileWriter(
        output_path.as_posix(), schema=table.schema
    ) as writer:
        writer.write_table(table)

    return warnings
