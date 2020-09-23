from typing import Any, Dict, Union

import pyarrow


def assert_arrow_table_equals(
    result1: pyarrow.Table, result2: Union[Dict[str, Any], pyarrow.Table]
) -> None:
    if isinstance(result2, dict):
        result2 = pyarrow.table(result2)
    assert result1.shape == result2.shape
    assert result1.column_names == result2.column_names
    for colname, actual_col, expected_col in zip(
        result1.column_names, result1.columns, result2.columns
    ):
        assert actual_col.type == expected_col.type
        assert actual_col.to_pylist() == expected_col.to_pylist()
