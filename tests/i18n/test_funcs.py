from cjwmodule.i18n import I18nMessage
from cjwparse.i18n import _trans_cjwparse


def test_trans_cjwparse():
    assert _trans_cjwparse(
        "errors.allNull",
        "The column “{column}” must contain non-null values.",
        {"column": "A"},
    ) == I18nMessage("errors.allNull", {"column": "A"}, "cjwparse")
