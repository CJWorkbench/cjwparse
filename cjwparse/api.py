from pathlib import Path
from typing import List, Optional

from cjwmodule.i18n import I18nMessage

from .csv import parse_csv
from .excel import parse_xls, parse_xlsx
from .i18n import _trans_cjwparse
from .json import parse_json
from .mime import MimeType
from .settings import DEFAULT_SETTINGS, Settings

__all__ = [
    "MimeType",
    "parse_file",
    "parse_csv",
    "parse_json",
    "parse_xls",
    "parse_xlsx",
]


def parse_file(
    path: Path,
    *,
    output_path: Path,
    settings: Settings = DEFAULT_SETTINGS,
    encoding: Optional[str] = None,
    mime_type: Optional[MimeType] = None,
    has_header: bool = True,
) -> List[I18nMessage]:
    """
    Parse the data file at `path` into new Arrow file `output_path`.

    Return a list of warnings as (translatable) I18nMessages.

    This must never fail, cause out-of-memory or any such madness:

    * If `path` points to a file we do not handle, write an empty file to
      `output_path` and return a warning.
    * If `path` points to an invalid file, convert what data we can and
      return a warning.
    """
    if mime_type is None:
        ext = "".join(path.suffixes).lower()
        try:
            mime_type = MimeType.from_extension(ext)
        except KeyError:
            output_path.write_bytes(b"")
            return [
                _trans_cjwparse(
                    "file.unknown_ext",
                    "Unknown file extension {ext}. Please try a different file.",
                    {"ext": ext},
                )
            ]

    if mime_type in {MimeType.CSV, MimeType.TSV, MimeType.TXT}:
        delimiter: Optional[str] = {
            MimeType.CSV: ",",
            MimeType.TSV: "\t",
            MimeType.TXT: None,
        }[mime_type]
        return parse_csv(
            path,
            output_path=output_path,
            encoding=encoding,
            settings=settings,
            delimiter=delimiter,
            has_header=has_header,
            autoconvert_text_to_numbers=True,
        )
    elif mime_type == MimeType.JSON:
        return parse_json(
            path, output_path=output_path, settings=settings, encoding=encoding
        )
    elif mime_type == MimeType.XLS:
        return parse_xls(
            path, output_path=output_path, settings=settings, has_header=has_header
        )
    elif mime_type == MimeType.XLSX:
        return parse_xlsx(
            path, output_path=output_path, settings=settings, has_header=has_header
        )
    else:
        raise RuntimeError("Unhandled MIME type")
