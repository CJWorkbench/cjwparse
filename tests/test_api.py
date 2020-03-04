import contextlib
import unittest
from pathlib import Path
from typing import ContextManager, List, Tuple

import pyarrow

from cjwmodule.i18n import I18nMessage
from cjwparse._util import tempfile_context
from cjwparse.api import parse_file
from cjwparse.mime import MimeType

from .util import assert_arrow_table_equals

TestDataPath = Path(__file__).parent / "files"


def call_parse_file(path: Path, **kwargs) -> Tuple[pyarrow.Table, List[I18nMessage]]:
    with tempfile_context(suffix=".arrow") as output_path:
        errors = parse_file(path, output_path=output_path, **kwargs)
        if output_path.stat().st_size == 0:
            table = pyarrow.table({})
        else:
            with pyarrow.ipc.open_file(output_path) as reader:
                table = reader.read_all()
    return table, errors


@contextlib.contextmanager
def _data_file(b: bytes, *, suffix: str = "") -> ContextManager[Path]:
    with tempfile_context(".input", suffix=suffix) as data_path:
        data_path.write_bytes(b)
        yield data_path


class ApiTests(unittest.TestCase):
    def test_detect_csv_by_suffix(self):
        with _data_file(b"A,B\nx,y\nz,a", suffix=".csv") as csv_path:
            table, errors = call_parse_file(csv_path)
        assert_arrow_table_equals(table, {"A": ["x", "z"], "B": ["y", "a"]})
        self.assertEqual(errors, [])

    def test_detect_tsv_by_suffix(self):
        with _data_file(b"A\tB\nx\ty\nz\ta", suffix=".tsv") as tsv_path:
            table, errors = call_parse_file(tsv_path)
        assert_arrow_table_equals(table, {"A": ["x", "z"], "B": ["y", "a"]})
        self.assertEqual(errors, [])

    def test_detect_semicolon_csv_by_suffix(self):
        with _data_file(b"A;B\nx;y\nz;a", suffix=".txt") as txt_path:
            table, errors = call_parse_file(txt_path)
        assert_arrow_table_equals(table, {"A": ["x", "z"], "B": ["y", "a"]})
        self.assertEqual(errors, [])

    def test_csv_has_header_false(self):
        with _data_file(b"A\n1.00\n2") as path:
            table, errors = call_parse_file(
                path, mime_type=MimeType.CSV, has_header=False
            )
        assert_arrow_table_equals(table, {"Column 1": ["A", "1.00", "2"]})
        self.assertEqual(errors, [])

    def test_csv_detect_encoding_by_default(self):
        with _data_file("A\ncafé".encode("windows-1252")) as path:
            table, errors = call_parse_file(path, mime_type=MimeType.CSV, encoding=None)
        assert_arrow_table_equals(table, {"A": ["café"]})
        self.assertEqual(errors, [])

    def test_csv_override_encoding_by_argument(self):
        # caller-selected encoding overrides autodetected encoding
        with _data_file("A\ncafé".encode("utf-8")) as path:
            table, errors = call_parse_file(
                path, mime_type=MimeType.CSV, encoding="windows-1252"
            )
        assert_arrow_table_equals(table, {"A": ["cafÃ©"]})
        self.assertEqual(errors, [])

    def test_detect_json_by_suffix(self):
        with _data_file(b'[{"X":"x"}]', suffix=".json") as json_path:
            table, errors = call_parse_file(json_path)
        assert_arrow_table_equals(table, {"X": ["x"]})
        self.assertEqual(errors, [])

    def test_json_detect_encoding_by_default(self):
        with _data_file('[{"A":"café"}]'.encode("windows-1252")) as path:
            table, errors = call_parse_file(
                path, mime_type=MimeType.JSON, encoding=None
            )
        assert_arrow_table_equals(table, {"A": ["café"]})
        self.assertEqual(errors, [])

    def test_json_override_encoding_by_argument(self):
        # caller-selected encoding overrides autodetected encoding
        with _data_file('[{"A":"café"}]'.encode("utf-8")) as path:
            table, errors = call_parse_file(
                path, mime_type=MimeType.JSON, encoding="windows-1252"
            )
        assert_arrow_table_equals(table, {"A": ["cafÃ©"]})
        self.assertEqual(errors, [])

    def test_detect_xlsx_by_suffix(self):
        table, errors = call_parse_file(TestDataPath / "test.xlsx")
        assert_arrow_table_equals(
            table, {"Month": ["Jan", "Feb"], "Amount": [10.0, 20.0]}
        )
        self.assertEqual(errors, [])

    def test_xlsx_has_header_false(self):
        table, errors = call_parse_file(TestDataPath / "test.xlsx", has_header=False)
        assert_arrow_table_equals(
            table, {"A": ["Month", "Jan", "Feb"], "B": ["Amount", "10", "20"]}
        )
        self.assertEqual(
            errors,
            [
                I18nMessage(
                    "TODO_i18n",
                    {"text": "interpreted 2 Numbers as String; see row 0 column B"},
                    None,
                )
            ],
        )

    def test_detect_xls_by_suffix(self):
        table, errors = call_parse_file(TestDataPath / "example.xls")
        assert_arrow_table_equals(table, {"foo": [1.0, 2.0], "bar": [2.0, 3.0]})
        self.assertEqual(errors, [])

    def test_detect_unknown_file_extension(self):
        with _data_file(b"A,B\nx,y", suffix=".bin") as bin_path:
            table, errors = call_parse_file(bin_path)
        assert_arrow_table_equals(table, {})
        self.assertEqual(
            errors, [I18nMessage("file.unknown_ext", {"ext": ".bin"}, "cjwparse")]
        )

    def test_mime_type_overrides_suffix(self):
        # File is ".csv" but we parse as ".json" because mime_type=MimeType.JSON
        with _data_file(b'[{"X":"x"}]', suffix=".csv") as json_path:
            table, errors = call_parse_file(json_path, mime_type=MimeType.JSON)
        assert_arrow_table_equals(table, {"X": ["x"]})
        self.assertEqual(errors, [])
