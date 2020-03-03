import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any, ContextManager, Dict, List, Optional, Union

import pyarrow
from numpy.testing import assert_equal  # [None, "x"] == [None, "x"]


@contextmanager
def arrow_file(
    table: Union[Dict[str, List[Any]], pyarrow.Table], dir: Optional[Path] = None
) -> ContextManager[Path]:
    """
    Yield a path with `table` written to an Arrow file.
    """
    if isinstance(table, dict):
        table = pyarrow.table(table)

    with tempfile.NamedTemporaryFile(dir=dir) as tf:
        writer = pyarrow.RecordBatchFileWriter(tf.name, table.schema)
        writer.write_table(table)
        writer.close()
        yield Path(tf.name)


def assert_arrow_table_equals(
    result1: pyarrow.Table, result2: Union[Dict[str, Any], pyarrow.Table]
) -> None:
    if isinstance(result2, dict):
        result2 = pyarrow.table(result2)
    assertEqual = unittest.TestCase().assertEqual
    assertEqual(result1.shape, result2.shape)
    assertEqual(result1.column_names, result2.column_names)
    for colname, actual_col, expected_col in zip(
        result1.table.column_names, result1.table.columns, result2.table.columns
    ):
        assertEqual(
            actual_col.type, expected_col.type, msg=f"Column {colname} has wrong type"
        )
        assert_equal(
            actual_col.to_pylist(),
            expected_col.to_pylist(),
            err_msg=f"Column {colname} has wrong values",
        )
