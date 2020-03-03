import unittest
from pathlib import Path

from cjwmodule.i18n import I18nMessage

from cjwparse._util import tempfile_context
from cjwparse.excel import parse_xls, parse_xlsx
from cjwparse.testing.i18n import cjwparse_i18n_message

from .util import assert_arrow_table_equals

TestDataPath = Path(__file__).parent.parent.parent / "test_data"


class ParseExcelTests(unittest.TestCase):
    def test_xlsx(self):
        path = TestDataPath / "test.xlsx"
        with tempfile_context(suffix=".arrow") as output_path:
            result = parse_xlsx(path, output_path=output_path, has_header=True)
        assert_arrow_table_equals(
            result.table, {"Month": ["Jan", "Feb"], "Amount": [10.0, 20.0]}
        )
        self.assertEqual(result.errors, [])

    def test_xls(self):
        path = TestDataPath / "example.xls"
        with tempfile_context(suffix=".arrow") as output_path:
            result = parse_xls(path, output_path=output_path, has_header=True)
        assert_arrow_table_equals(result.table, {"foo": [1.0, 2.0], "bar": [2.0, 3.0]})
        self.assertEqual(result.errors, [])

    def test_xlsx_cast_colnames_to_str(self):
        path = TestDataPath / "all-numeric.xlsx"
        with tempfile_context(suffix=".arrow") as output_path:
            result = parse_xlsx(path, output_path=output_path, has_header=True)
        assert_arrow_table_equals(result.table, {"1": [2.0]})
        self.assertEqual(result.errors, [])

    def test_xlsx_invalid(self):
        with tempfile_context(prefix="invalid", suffix=".xlsx") as path:
            path.write_bytes(b"not an xlsx")
            with tempfile_context(suffix=".arrow") as output_path:
                result = parse_xlsx(path, output_path=output_path, has_header=True)

        assert_arrow_table_equals(result.table, {})
        self.assertEqual(
            result.warnings,
            [
                I18nMessage(
                    "TODO_i18n",
                    {
                        "text": "Invalid XLSX file: xlnt::exception : failed to find zip header"
                    },
                    None,
                )
            ],
        )

    def test_xlsx_nix_control_characters_from_colnames(self):
        path = TestDataPath / "headers-have-control-characters.xlsx"
        with tempfile_context(suffix=".arrow") as output_path:
            result = parse_xlsx(path, output_path=output_path, has_header=True)
        assert_arrow_table_equals(result.table, {"AB": ["a"], "C": ["b"]})
        self.assertEqual(
            result.errors,
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
        with tempfile_context(suffix=".arrow") as output_path:
            result = parse_xlsx(path, output_path=output_path, has_header=True)
        assert_arrow_table_equals(result.table, {"A": ["a"], "A 2": ["b"]})
        self.assertEqual(
            result.errors,
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
        with tempfile_context(suffix=".arrow") as output_path:
            result = parse_xlsx(path, output_path=output_path, has_header=True)
        assert_arrow_table_equals(result.table, {"A": ["a"], "Column 2": ["b"]})
        self.assertEqual(
            result.errors,
            [
                I18nMessage(
                    "util.colnames.warnings.default",
                    {"n_columns": 1, "first_colname": "Column 2"},
                    "cjwmodule",
                )
            ],
        )
