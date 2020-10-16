import unittest
from pathlib import Path
from typing import List, Tuple

import pyarrow

from cjwmodule.i18n import I18nMessage
from cjwparse._util import tempfile_context
from cjwparse.excel import parse_xls, parse_xlsx
from cjwparse.settings import DEFAULT_SETTINGS, Settings

from .util import assert_arrow_table_equals

TestDataPath = Path(__file__).parent / "files"


def call_parse_xlsx(
    path: Path, *, has_header: bool, settings: Settings = DEFAULT_SETTINGS
) -> Tuple[pyarrow.Table, List[I18nMessage]]:
    with tempfile_context(suffix=".arrow") as output_path:
        warnings = parse_xlsx(
            path, output_path=output_path, has_header=True, settings=settings
        )
        with pyarrow.ipc.open_file(output_path) as reader:
            table = reader.read_all()
    return table, warnings


def call_parse_xls(
    path: Path, *, has_header: bool, settings: Settings = DEFAULT_SETTINGS
) -> Tuple[pyarrow.Table, List[I18nMessage]]:
    with tempfile_context(suffix=".arrow") as output_path:
        warnings = parse_xls(
            path, output_path=output_path, has_header=True, settings=settings
        )
        with pyarrow.ipc.open_file(output_path) as reader:
            table = reader.read_all()
    return table, warnings


class ParseExcelTests(unittest.TestCase):
    def test_xlsx(self):
        path = TestDataPath / "test.xlsx"
        table, errors = call_parse_xlsx(path, has_header=True)
        assert_arrow_table_equals(
            table, {"Month": ["Jan", "Feb"], "Amount": [10.0, 20.0]}
        )
        self.assertEqual(errors, [])

    def test_xls(self):
        path = TestDataPath / "example.xls"
        table, errors = call_parse_xls(path, has_header=True)
        assert_arrow_table_equals(table, {"foo": [1.0, 2.0], "bar": [2.0, 3.0]})
        self.assertEqual(errors, [])

    def test_xlsx_cast_colnames_to_str(self):
        path = TestDataPath / "all-numeric.xlsx"
        table, errors = call_parse_xlsx(path, has_header=True)
        assert_arrow_table_equals(table, {"1": [2.0]})
        self.assertEqual(errors, [])

    def test_xlsx_invalid(self):
        with tempfile_context(prefix="invalid", suffix=".xlsx") as path:
            path.write_bytes(b"not an xlsx")
            table, errors = call_parse_xlsx(path, has_header=True)

        assert_arrow_table_equals(table, {})
        self.assertEqual(
            errors,
            [
                I18nMessage(
                    "excel.invalid_file",
                    {"message": "xlnt::exception : failed to find zip header"},
                    "cjwparse",
                )
            ],
        )

    def test_xlsx_nix_control_characters_from_colnames(self):
        path = TestDataPath / "headers-have-control-characters.xlsx"
        table, errors = call_parse_xlsx(path, has_header=True)
        assert_arrow_table_equals(table, {"AB": ["a"], "C": ["b"]})
        self.assertEqual(
            errors,
            [
                I18nMessage(
                    "util.colnames.warnings.ascii_cleaned",
                    {"n_columns": 1, "first_colname": "AB"},
                    "cjwmodule",
                )
            ],
        )

    def test_xlsx_uniquify_colnames(self):
        path = TestDataPath / "headers-have-duplicate-colnames.xlsx"
        table, errors = call_parse_xlsx(path, has_header=True)
        assert_arrow_table_equals(table, {"A": ["a"], "A 2": ["b"]})
        self.assertEqual(
            errors,
            [
                I18nMessage(
                    "util.colnames.warnings.numbered",
                    {"n_columns": 1, "first_colname": "A 2"},
                    "cjwmodule",
                )
            ],
        )

    def test_xlsx_replace_empty_colnames(self):
        path = TestDataPath / "headers-empty.xlsx"
        table, errors = call_parse_xlsx(path, has_header=True)
        assert_arrow_table_equals(table, {"A": ["a"], "Column 2": ["b"]})
        self.assertEqual(
            errors,
            [
                I18nMessage(
                    "util.colnames.warnings.default",
                    {"n_columns": 1, "first_colname": "Column 2"},
                    "cjwmodule",
                )
            ],
        )

    def test_xlsx_invalid_but_excel_can_repair_it(self):
        path = TestDataPath / "excel-can-repair-this.xlsx"
        table, errors = call_parse_xlsx(path, has_header=True)
        assert_arrow_table_equals(table, {})
        self.assertEqual(
            errors,
            [
                I18nMessage(
                    "excel.invalid_file",
                    {
                        "message": "xl/_rels/workbook.xml.rels:2:84: error: attribute 'Target' expected"
                    },
                    "cjwparse",
                )
            ],
        )
