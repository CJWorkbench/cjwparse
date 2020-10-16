import subprocess
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

import pyarrow

from cjwmodule.i18n import I18nMessage
from cjwmodule.util.colnames import gen_unique_clean_colnames_and_warn

from ._util import tempfile_context
from .i18n import _trans_cjwparse
from .postprocess import dictionary_encode_columns
from .settings import DEFAULT_SETTINGS, Settings


class ParseResult(NamedTuple):
    table: pyarrow.Table
    warnings: List[I18nMessage]


def _postprocess_table(
    table: pyarrow.Table, headers_table: Optional[pyarrow.Table], settings: Settings
) -> Tuple[pyarrow.Table, List[I18nMessage]]:
    """
    Transform `raw_table` to meet our standards:

    * Convert each column dictionary if it agrees with
      `settings.MAX_DICTIONARY_SIZE` and
      `settings.MIN_DICTIONARY_COMPRESSION_RATIO`.
    * Rename columns if `headers_table` is provided.
    """
    table = dictionary_encode_columns(table, settings=settings)
    if headers_table is not None:
        colnames = [
            # filter out None and ""
            " - ".join(v for v in column.to_pylist() if v)
            for column in headers_table.itercolumns()
        ]
        colnames, warnings = gen_unique_clean_colnames_and_warn(
            colnames, settings=settings
        )
        table = table.rename_columns(colnames)
    else:
        warnings = []
    return table, warnings


def _stderr_line_to_error(line: str) -> I18nMessage:
    if line.startswith("Invalid XLSX file: "):
        return _trans_cjwparse(
            "excel.invalid_file",
            "This Excel file is invalid. Open it in Microsoft Office and re-save it to correct errors. (Debugging message: “{message}”)",
            {"message": line[len("Invalid XLSX file: ") :]},
        )
    else:
        return I18nMessage("TODO_i18n", {"text": line}, None)


def _parse_excel(
    tool: str, path: Path, *, header_rows: str, settings: Settings = DEFAULT_SETTINGS
) -> ParseResult:
    """
    Parse Excel .xlsx or .xls file.

    The process:

    1. Run `/usr/bin/{tool}` (`xlsx-to-arrow`, say) to parse cells into columns.
    2. Dictionary-encode each column if it's helpful.
    3. Write the final Arrow file.
    """
    with tempfile_context(suffix=".arrow") as arrow_path, tempfile_context(
        suffix="-headers.arrow"
    ) as header_rows_path:
        # raise subprocess.CalledProcessError on error ... but there is no
        # error xls-to-arrow will throw that we can recover from.
        child = subprocess.run(
            [
                "/usr/bin/" + tool,
                "--max-rows",
                str(settings.MAX_ROWS_PER_TABLE),
                "--max-columns",
                str(settings.MAX_COLUMNS_PER_TABLE),
                "--max-bytes-per-value",
                str(settings.MAX_BYTES_PER_VALUE),
                "--max-bytes-total",
                str(settings.MAX_BYTES_TEXT_DATA),
                "--header-rows",
                header_rows,
                "--header-rows-file",
                header_rows_path.as_posix(),
                path.as_posix(),
                arrow_path.as_posix(),
            ],
            capture_output=True,
            check=True,
        )
        parse_warnings = [
            _stderr_line_to_error(line)
            for line in child.stdout.decode("utf-8").split("\n")
            if line
        ]

        with pyarrow.ipc.open_file(arrow_path.as_posix()) as reader:
            raw_table = reader.read_all()  # efficient -- RAM is mmapped
        if header_rows:
            with pyarrow.ipc.open_file(header_rows_path.as_posix()) as reader:
                maybe_headers_table = reader.read_all()
        else:
            maybe_headers_table = None

    table, colname_warnings = _postprocess_table(
        raw_table, maybe_headers_table, settings
    )
    return ParseResult(table, (parse_warnings + colname_warnings))


def _write_table(table: pyarrow.Table, output_path: Path) -> None:
    with pyarrow.ipc.RecordBatchFileWriter(
        output_path.as_posix(), schema=table.schema
    ) as writer:
        writer.write_table(table)


def _parse_excel_and_write_result(
    *,
    tool: str,
    path: Path,
    output_path: Path,
    has_header: bool,
    settings: Settings = DEFAULT_SETTINGS
) -> List[I18nMessage]:
    table, warnings = _parse_excel(
        tool, path, header_rows=("0-1" if has_header else ""), settings=settings
    )
    _write_table(table, output_path)
    return warnings


def parse_xlsx(
    path: Path,
    *,
    output_path: Path,
    settings: Settings = DEFAULT_SETTINGS,
    has_header: bool
) -> List[I18nMessage]:
    return _parse_excel_and_write_result(
        tool="xlsx-to-arrow",
        path=path,
        output_path=output_path,
        settings=settings,
        has_header=has_header,
    )


def parse_xls(
    path: Path,
    *,
    output_path: Path,
    settings: Settings = DEFAULT_SETTINGS,
    has_header: bool
) -> List[I18nMessage]:
    return _parse_excel_and_write_result(
        tool="xls-to-arrow",
        path=path,
        output_path=output_path,
        settings=settings,
        has_header=has_header,
    )
